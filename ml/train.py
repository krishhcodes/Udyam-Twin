"""Model training, evaluation, and serialization for AI4I 2020 predictive maintenance.

Features:
- Air temperature [K]
- Process temperature [K]
- Rotational speed [rpm]
- Torque [Nm]
- Tool wear [min]
- Engineered power [kW]
- Engineered delta_t [K]

CRITICAL CONSTRAINT: Vibration and current are NEVER fed to this model
(they feed the physical rule engine only, matching the dataset schema).
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    average_precision_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split

from ml.rules import evaluate_ai4i_rules

ML_DIR = Path(__file__).resolve().parent
MODEL_PATH = ML_DIR / "model.joblib"
METRICS_PATH = ML_DIR / "metrics.json"
DATA_DIR = ML_DIR / "data"


def generate_or_load_ai4i_data(n_samples: int = 10000, seed: int = 42) -> pd.DataFrame:
    """Load AI4I dataset from csv if present, or generate identical statistical distribution."""
    csv_path = DATA_DIR / "ai4i2020.csv"
    if csv_path.exists():
        df = pd.read_csv(csv_path)
        # Standardize column names
        col_map = {
            "Air temperature [K]": "air_temp_k",
            "Process temperature [K]": "process_temp_k",
            "Rotational speed [rpm]": "rpm",
            "Torque [Nm]": "torque_nm",
            "Tool wear [min]": "tool_wear_min",
            "Machine failure": "failure",
            "Type": "variant_type",
        }
        df = df.rename(columns=col_map)
        return df

    # Generate synthetic dataset matching UCI AI4I 2020 distributions
    rng = np.random.default_rng(seed)

    # Variant types: L (50%), M (30%), H (20%)
    variants = rng.choice(["L", "M", "H"], size=n_samples, p=[0.5, 0.3, 0.2])

    air_temp = rng.normal(loc=300.0, scale=2.0, size=n_samples)
    delta_t_base = rng.normal(loc=10.0, scale=1.0, size=n_samples)
    process_temp = air_temp + delta_t_base

    rpm = rng.normal(loc=1538.0, scale=179.0, size=n_samples)
    rpm = np.clip(rpm, 1168.0, 2886.0)

    torque = rng.normal(loc=39.98, scale=9.96, size=n_samples)
    torque = np.clip(torque, 3.8, 76.6)

    tool_wear = rng.uniform(low=0.0, high=253.0, size=n_samples)

    failures = []
    twf_list, hdf_list, pwf_list, osf_list = [], [], [], []

    for i in range(n_samples):
        res = evaluate_ai4i_rules(
            air_temp_k=air_temp[i],
            process_temp_k=process_temp[i],
            rpm=rpm[i],
            torque_nm=torque[i],
            tool_wear_min=tool_wear[i],
            variant_type=variants[i],
        )
        # Natural failure label
        is_fail = 1 if (res.hdf or res.pwf or res.osf or res.twf or (rng.random() < 0.001)) else 0
        failures.append(is_fail)
        twf_list.append(1 if res.twf else 0)
        hdf_list.append(1 if res.hdf else 0)
        pwf_list.append(1 if res.pwf else 0)
        osf_list.append(1 if res.osf else 0)

    df = pd.DataFrame({
        "variant_type": variants,
        "air_temp_k": np.round(air_temp, 2),
        "process_temp_k": np.round(process_temp, 2),
        "rpm": np.round(rpm, 1),
        "torque_nm": np.round(torque, 2),
        "tool_wear_min": np.round(tool_wear, 1),
        "TWF": twf_list,
        "HDF": hdf_list,
        "PWF": pwf_list,
        "OSF": osf_list,
        "failure": failures,
    })
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(csv_path, index=False)
    return df


def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    """Compute power [kW] and delta_t [K] without using vibration/current."""
    feats = pd.DataFrame()
    feats["air_temp_k"] = df["air_temp_k"]
    feats["process_temp_k"] = df["process_temp_k"]
    feats["rpm"] = df["rpm"]
    feats["torque_nm"] = df["torque_nm"]
    feats["tool_wear_min"] = df["tool_wear_min"]
    feats["power_kw"] = (df["torque_nm"] * df["rpm"] * 2.0 * math.pi / 60.0 / 1000.0).round(3)
    feats["delta_t"] = (df["process_temp_k"] - df["air_temp_k"]).round(2)
    return feats


def train_and_evaluate(seed: int = 42) -> dict[str, Any]:
    """Train Random Forest classifier, evaluate against rule baseline, save artifacts."""
    df = generate_or_load_ai4i_data(n_samples=10000, seed=seed)
    X = engineer_features(df)
    y = df["failure"].to_numpy()

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.20, random_state=seed, stratify=y
    )

    # 1. Rule Engine Baseline Evaluation
    rule_preds = []
    for _, row in X_test.iterrows():
        r = evaluate_ai4i_rules(
            air_temp_k=row["air_temp_k"],
            process_temp_k=row["process_temp_k"],
            rpm=row["rpm"],
            torque_nm=row["torque_nm"],
            tool_wear_min=row["tool_wear_min"],
        )
        rule_preds.append(1 if (r.hdf or r.pwf or r.osf or r.twf) else 0)
    rule_preds = np.array(rule_preds)

    rule_tn, rule_fp, rule_fn, rule_tp = confusion_matrix(y_test, rule_preds).ravel()
    rule_metrics = {
        "precision": round(float(precision_score(y_test, rule_preds, zero_division=0)), 4),
        "recall": round(float(recall_score(y_test, rule_preds, zero_division=0)), 4),
        "f1": round(float(f1_score(y_test, rule_preds, zero_division=0)), 4),
        "confusion_matrix": {
            "true_negatives": int(rule_tn),
            "false_positives": int(rule_fp),
            "false_negatives": int(rule_fn),
            "true_positives": int(rule_tp),
        },
    }

    # 2. Random Forest Model
    clf = RandomForestClassifier(
        n_estimators=100,
        class_weight="balanced",
        random_state=seed,
        max_depth=12,
        min_samples_split=4,
    )
    clf.fit(X_train, y_train)

    rf_preds = clf.predict(X_test)
    rf_probs = clf.predict_proba(X_test)[:, 1]

    rf_tn, rf_fp, rf_fn, rf_tp = confusion_matrix(y_test, rf_preds).ravel()
    rf_fpr = round(float(rf_fp / (rf_fp + rf_tn)), 4) if (rf_fp + rf_tn) > 0 else 0.0

    feature_importances = {
        feat: round(float(imp), 4)
        for feat, imp in zip(X.columns, clf.feature_importances_)
    }

    rf_metrics = {
        "precision": round(float(precision_score(y_test, rf_preds, zero_division=0)), 4),
        "recall": round(float(recall_score(y_test, rf_preds, zero_division=0)), 4),
        "f1": round(float(f1_score(y_test, rf_preds, zero_division=0)), 4),
        "roc_auc": round(float(roc_auc_score(y_test, rf_probs)), 4),
        "pr_auc": round(float(average_precision_score(y_test, rf_probs)), 4),
        "false_positive_rate": rf_fpr,
        "confusion_matrix": {
            "true_negatives": int(rf_tn),
            "false_positives": int(rf_fp),
            "false_negatives": int(rf_fn),
            "true_positives": int(rf_tp),
        },
        "feature_importances": feature_importances,
    }

    report = {
        "dataset": "AI4I 2020 Predictive Maintenance Dataset (UCI / Synthetic standard)",
        "samples_total": len(df),
        "train_samples": len(X_train),
        "test_samples": len(X_test),
        "failure_rate": round(float(np.mean(y)), 4),
        "features": list(X.columns),
        "vibration_and_current_excluded_from_ml": True,
        "rule_baseline": rule_metrics,
        "random_forest": rf_metrics,
        "honest_disclaimer": (
            "AI4I labels are synthetically generated from rules; high evaluation scores "
            "are expected and demonstrate algorithmic reproducibility rather than real-world validation. "
            "Real-world MSME validation occurs in subsequent pilot stages."
        ),
    }

    # Save artifacts
    joblib.dump(clf, MODEL_PATH)
    METRICS_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


class MLPredictor:
    """Thread-safe predictor loading model.joblib."""

    def __init__(self, model_path: Path = MODEL_PATH):
        if not model_path.exists():
            train_and_evaluate()
        self.model = joblib.load(model_path)

    def predict_p(
        self,
        air_temp_k: float,
        process_temp_k: float,
        rpm: float,
        torque_nm: float,
        tool_wear_min: float,
    ) -> float:
        power_kw = round(torque_nm * rpm * 2.0 * math.pi / 60.0 / 1000.0, 3)
        delta_t = round(process_temp_k - air_temp_k, 2)
        feats = pd.DataFrame([{
            "air_temp_k": air_temp_k,
            "process_temp_k": process_temp_k,
            "rpm": rpm,
            "torque_nm": torque_nm,
            "tool_wear_min": tool_wear_min,
            "power_kw": power_kw,
            "delta_t": delta_t,
        }])
        prob = self.model.predict_proba(feats)[0, 1]
        return round(float(prob), 3)


if __name__ == "__main__":
    rep = train_and_evaluate()
    print("Training complete:")
    print(f"Rule F1: {rep['rule_baseline']['f1']}, RF F1: {rep['random_forest']['f1']}, PR-AUC: {rep['random_forest']['pr_auc']}")
