"""Rule-based failure definitions mirroring the AI4I 2020 predictive maintenance dataset.

Rules:
- HDF (Heat Dissipation Failure): delta_t < 8.6 K and rpm < 1380
  Note: AI4I's HDF defines failure as a small temperature gap at low RPM.
  Coolant loss causes the gap to widen, so coolant monitoring uses the physics
  OVERTEMP rule (process temp > threshold), never AI4I's HDF.
- PWF (Power Failure): power < 3.5 kW or power > 9.0 kW
- OSF (Overstrain Failure): tool_wear * torque > threshold (11,000 for L, 12,000 for M, 13,000 for H)
- TWF (Tool Wear Failure): tool_wear between 200 and 240 minutes
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


@dataclass
class RuleEvaluationResult:
    hdf: bool
    pwf: bool
    osf: bool
    twf: bool
    overtemp: bool
    vibration_high: bool
    any_failure: bool
    risk_level: str  # LOW, MEDIUM, HIGH
    top_signals: list[str]


def evaluate_ai4i_rules(
    *,
    air_temp_k: float,
    process_temp_k: float | None,
    rpm: float,
    torque_nm: float,
    tool_wear_min: float,
    vibration_rms_mm_s: float = 2.2,
    variant_type: str = "L",
    temp_limit_k: float = 315.5,
) -> RuleEvaluationResult:
    """Evaluate physical and AI4I rule baselines."""
    top_signals: list[str] = []

    # 1. AI4I Heat Dissipation Failure (HDF)
    delta_t = (process_temp_k - air_temp_k) if process_temp_k is not None else 0.0
    hdf = delta_t < 8.6 and rpm < 1380.0
    if hdf:
        top_signals.append("delta_t")
        top_signals.append("rpm")

    # 2. AI4I Power Failure (PWF)
    power_kw = torque_nm * rpm * 2.0 * math.pi / 60.0 / 1000.0
    pwf = (power_kw < 3.5 or power_kw > 9.0) if rpm > 0 else False
    if pwf:
        top_signals.append("power_kw")

    # 3. AI4I Overstrain Failure (OSF)
    osf_thresholds = {"L": 11000.0, "M": 12000.0, "H": 13000.0}
    osf_limit = osf_thresholds.get(variant_type, 11000.0)
    osf = (tool_wear_min * torque_nm) > osf_limit
    if osf:
        top_signals.append("tool_wear_min")
        top_signals.append("torque_nm")

    # 4. AI4I Tool Wear Failure (TWF)
    twf = 200.0 <= tool_wear_min <= 240.0
    if twf:
        top_signals.append("tool_wear_min")

    # 5. Physics Rules (Not part of AI4I dataset, used for physical shop safety)
    overtemp = (process_temp_k is not None) and (process_temp_k > temp_limit_k)
    if overtemp and "process_temp_k" not in top_signals:
        top_signals.append("process_temp_k")

    # Vibration rule: ISO 20816 Zone C/D
    vibration_high = vibration_rms_mm_s > 4.5
    if vibration_high and "vibration_rms_mm_s" not in top_signals:
        top_signals.append("vibration_rms_mm_s")

    any_failure = hdf or pwf or osf or twf or overtemp or vibration_rms_mm_s > 7.1

    if any_failure:
        risk_level = "HIGH"
    elif vibration_high or tool_wear_min > 180.0:
        risk_level = "MEDIUM"
    else:
        risk_level = "LOW"

    return RuleEvaluationResult(
        hdf=hdf,
        pwf=pwf,
        osf=osf,
        twf=twf,
        overtemp=overtemp,
        vibration_high=vibration_high,
        any_failure=any_failure,
        risk_level=risk_level,
        top_signals=list(dict.fromkeys(top_signals)),  # Deduplicate preserving order
    )
