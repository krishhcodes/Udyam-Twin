"""Digital Twin model for machine assets.

Calculates model predictions, evaluates residuals, performs self-calibration,
generates forecasts, and assesses failure risk.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from twin.calibrate import TwinCalibrator
from twin.forecast import ForecastEngine, TEMP_LIMIT_K
from twin.residuals import ResidualState, ResidualTracker

SCHEMA_VERSION = "1.0"
TICK_S = 0.5
VIB_ZONE_C = 4.5
VIB_ZONE_D = 7.1


@dataclass
class DigitalTwin:
    """Twin model maintaining parameter estimates and running predictive physics."""

    machine_id: str
    template: str
    hero: bool = False

    calibrator: TwinCalibrator = field(default_factory=TwinCalibrator)
    residual: ResidualTracker = field(default_factory=ResidualTracker)
    pred_temp: float | None = None
    pred_wear: float = 118.0
    alert_announced: bool = False

    def __post_init__(self):
        if self.template == "air_compressor":
            self.residual.signal = "pressure_bar"
            self.residual.band = 0.5
        elif self.template == "bar_saw":
            self.residual.signal = "power_kw"
            self.residual.band = 0.5
        elif self.template == "cnc_lathe":
            self.pred_temp = 310.8
            self.pred_wear = 64.0
        elif self.template == "cnc_mill":
            self.pred_temp = 311.5
            self.pred_wear = 118.0

    def step_cnc(
        self,
        obs: dict[str, Any],
        is_bearing_defect: bool,
    ) -> tuple[dict, list[dict], float | None]:
        """Step the CNC twin model forward given an observation frame.

        Returns:
            (twin_message, list_of_events, proposed_derate_pct_or_none)
        """
        events: list[dict] = []
        proposed_derate: float | None = None

        power = float(obs.get("power_kw") or 0.0)
        air_temp = float(obs.get("air_temp_k") or 300.0)
        h_est = self.calibrator.h_cool

        # Physics prediction: process temperature
        pred_target = air_temp + 8.0 + 0.7 * power / h_est
        if self.pred_temp is None:
            self.pred_temp = float(obs.get("process_temp_k") or 311.5)
        self.pred_temp += (pred_target - self.pred_temp) * TICK_S / 20.0

        # Residual evaluation
        obs_temp = obs.get("process_temp_k")
        vib_rms = float(obs.get("vibration_rms_mm_s") or 0.0)
        dq_flag = str(obs.get("dq_flag") or "OK")

        e, state, is_new_drift, is_new_anomaly = self.residual.update(
            obs_val=obs_temp,
            pred_val=self.pred_temp,
            vibration_rms=vib_rms,
            dq_flag=dq_flag,
            is_bearing_defect=is_bearing_defect,
            tick_s=TICK_S,
        )

        ts_str = obs["ts"]

        # Handle events from residual states
        if state == ResidualState.ANOMALY and is_new_anomaly:
            if self.residual.frozen_reason == "anomaly":
                events.append({
                    "type": "event",
                    "schema_version": SCHEMA_VERSION,
                    "ts": ts_str,
                    "event_id": f"EV_ANOMALY_{self.machine_id}",
                    "machine_id": self.machine_id,
                    "kind": "ANOMALY",
                    "severity": "CRITICAL",
                    "title": "Abrupt vibration change: calibration frozen",
                    "measured": f"Vibration {vib_rms} mm/s RMS (was ~{self.residual.vib_ewma:.1f})",
                    "inferred": "Sudden change, not gradual drift: possible bearing defect or sensor fault",
                    "suggested": "Stop at next safe point; inspect spindle bearing; verify accelerometer mounting",
                    "data": {"freeze_reason": "anomaly"},
                })
            elif dq_flag != "OK" and self.residual.frozen_reason == "data_quality":
                events.append({
                    "type": "event",
                    "schema_version": SCHEMA_VERSION,
                    "ts": ts_str,
                    "event_id": f"EV_DQ_{self.machine_id}",
                    "machine_id": self.machine_id,
                    "kind": "ANOMALY",
                    "severity": "WARN",
                    "title": f"Temperature sensor {dq_flag.lower()}: calibration frozen",
                    "measured": f"dq_flag={dq_flag}",
                    "inferred": "Sensor data not trustworthy",
                    "suggested": "Check sensor wiring and mounting",
                    "data": {"freeze_reason": "data_quality"},
                })

        if state == ResidualState.DRIFT and is_new_drift:
            obs_disp = f"{obs_temp:.1f} K" if obs_temp is not None else "N/A"
            events.append({
                "type": "event",
                "schema_version": SCHEMA_VERSION,
                "ts": ts_str,
                "event_id": f"EV_DRIFT_{self.machine_id}",
                "machine_id": self.machine_id,
                "kind": "DRIFT",
                "severity": "WARN",
                "title": f"Model mismatch: sustained {self.residual.ewma:+.1f} K on process temperature",
                "measured": f"Observed {obs_disp} vs predicted {self.pred_temp:.1f} K",
                "inferred": "Machine behaviour has changed gradually; twin will recalibrate",
            })

        # Bounded parameter calibration if in DRIFT and not frozen
        if state == ResidualState.DRIFT:
            cal_rec = self.calibrator.step_thermal_calibration(
                power_kw=power,
                air_temp_k=air_temp,
                y_filt=self.residual.y_filt,
                dy_filt=self.residual.dy_filt,
                residual_ewma=self.residual.ewma,
                is_frozen=self.residual.frozen_reason is not None,
            )
            if cal_rec:
                events.append({
                    "type": "event",
                    "schema_version": SCHEMA_VERSION,
                    "ts": ts_str,
                    "event_id": f"EV_CAL_{self.machine_id}",
                    "machine_id": self.machine_id,
                    "kind": "CALIBRATION",
                    "severity": "INFO",
                    "title": f"Recalibrated h_cool {cal_rec.from_val:.2f} → {cal_rec.to_val:.2f}",
                    "inferred": f"Cooling capacity estimated {100 * (1 - self.calibrator.h_cool):.0f}% below nominal",
                    "suggested": "Check coolant level, pump and filter",
                    "data": {
                        "param": cal_rec.param,
                        "from": cal_rec.from_val,
                        "to": cal_rec.to_val,
                        "version": cal_rec.version,
                        "residual_ewma": cal_rec.residual_ewma,
                    },
                })

        # Forecast horizon
        tool_wear = float(obs.get("tool_wear_min") or 0.0)
        now_temp = obs_temp if obs_temp is not None else self.pred_temp
        minutes, warning = ForecastEngine.forecast_cnc(
            air_temp_k=air_temp,
            power_kw=power,
            h_est=self.calibrator.h_cool,
            current_temp_k=now_temp,
            tool_wear_min=tool_wear,
        )

        # Supervised self-healing in SIM mode
        current_derate = float(obs.get("derate_pct") or 0.0)
        if self.hero and warning == "OVERTEMP" and minutes is not None and minutes < 10.0 and current_derate == 0.0:
            proposed_derate = 20.0
            events.append({
                "type": "event",
                "schema_version": SCHEMA_VERSION,
                "ts": ts_str,
                "event_id": f"EV_DERATE_{self.machine_id}",
                "machine_id": self.machine_id,
                "kind": "ALERT",
                "severity": "WARN",
                "title": "Over-temperature forecast: auto-derated 20% (SIM only)",
                "measured": f"Process temp {now_temp:.1f} K, rising; RPM {obs.get('rpm', 0):.0f}",
                "inferred": f"Calibrated twin forecasts {TEMP_LIMIT_K:.0f} K in ~{minutes:.0f} min at current settings",
                "suggested": "Check coolant flow and filter. On a LIVE machine this derate needs operator approval.",
                "data": {"derate_pct": 20, "mode": "SIM_AUTO", "work_order_draft": True},
            })

        # Risk assessment
        plc_state = str(obs.get("plc_state") or "RUN")
        if (now_temp or 0) > TEMP_LIMIT_K or vib_rms > VIB_ZONE_D or plc_state == "TRIP":
            rules_risk = "HIGH"
        elif warning or vib_rms > VIB_ZONE_C:
            rules_risk = "MEDIUM"
        else:
            rules_risk = "LOW"

        if rules_risk == "HIGH" and not self.alert_announced and self.residual.frozen_reason != "anomaly":
            self.alert_announced = True
            events.append({
                "type": "event",
                "schema_version": SCHEMA_VERSION,
                "ts": ts_str,
                "event_id": f"EV_ALERTHIGH_{self.machine_id}",
                "machine_id": self.machine_id,
                "kind": "ALERT",
                "severity": "CRITICAL",
                "title": "Process temperature above limit",
                "measured": f"{now_temp:.1f} K > {TEMP_LIMIT_K} K",
                "inferred": "Cooling insufficient for current load",
                "suggested": "Reduce load; inspect coolant system",
            })

        top_signals = []
        if warning == "OVERTEMP" or e > self.residual.band:
            top_signals.append("process_temp_k")
        if vib_rms > VIB_ZONE_C:
            top_signals.append("vibration_rms_mm_s")
        if tool_wear > 180.0:
            top_signals.append("tool_wear_min")

        torque = float(obs.get("torque_nm") or 0.0)
        # Score failure risk using trained Random Forest (or closed-form approximation fallback)
        model_p = None
        if obs.get("process_temp_k") is not None:
            try:
                from ml.train import MLPredictor
                predictor = getattr(self, "_ml_predictor", None)
                if predictor is None:
                    predictor = MLPredictor()
                    self._ml_predictor = predictor
                model_p = predictor.predict_p(
                    air_temp_k=air_temp,
                    process_temp_k=float(obs["process_temp_k"]),
                    rpm=float(obs.get("rpm", 1540.0)),
                    torque_nm=torque,
                    tool_wear_min=tool_wear,
                )
            except Exception:
                model_p = None

        if model_p is None:
            z = -6.0 + 0.012 * tool_wear + 0.04 * max(0.0, torque - 40.0) + (2.5 if warning else 0.0)
            model_p = round(1.0 / (1.0 + math.exp(-z)), 3)

        twin_msg = {
            "type": "twin",
            "schema_version": SCHEMA_VERSION,
            "ts": ts_str,
            "machine_id": self.machine_id,
            "predicted": {
                "process_temp_k": round(self.pred_temp, 2),
                "tool_wear_min": round(tool_wear, 1),
            },
            "residual": {
                "signal": self.residual.signal,
                "value": round(e, 3),
                "ewma": round(self.residual.ewma, 3),
                "cusum": round(self.residual.cusum, 3),
                "band": self.residual.band,
                "state": state.value,
            },
            "params": {
                "version": self.calibrator.version,
                "values": self.calibrator.values,
                "frozen": self.residual.frozen_reason is not None,
                "freeze_reason": self.residual.frozen_reason,
            },
            "forecast": {
                "minutes_to_warning": minutes,
                "warning": warning,
            },
            "risk": {
                "rules": rules_risk,
                "model": model_p,
                "top_signals": top_signals,
            },
        }
        return twin_msg, events, proposed_derate

    def step_simple(self, obs: dict[str, Any]) -> dict:
        """Step twin model for bar saw or air compressor."""
        ts_str = obs["ts"]
        if self.template == "air_compressor":
            signal = "pressure_bar"
            value = float(obs.get("pressure_bar") or 7.0)
            predicted = 7.0
            low = value < 6.0
            rules = "HIGH" if low else ("MEDIUM" if value < 6.5 else "LOW")
            forecast = {
                "minutes_to_warning": 0.0 if low else None,
                "warning": "PRESSURE_LOW" if low else None,
            }
            top = ["pressure_bar", "duty_pct"] if rules != "LOW" else []
        else:
            signal = "power_kw"
            value = float(obs.get("power_kw") or 1.4)
            predicted = 1.4 + 0.006 * 35.0
            blade_wear = float(obs.get("blade_wear_pct") or 0.0)
            rules = "HIGH" if blade_wear > 90.0 else ("MEDIUM" if blade_wear > 75.0 else "LOW")
            forecast = {
                "minutes_to_warning": None,
                "warning": "BLADE_WEAR" if rules != "LOW" else None,
            }
            top = ["blade_wear_pct"] if rules != "LOW" else []

        e = value - predicted
        state = ResidualState.DRIFT if abs(e) > 0.5 else ResidualState.IN_BAND

        return {
            "type": "twin",
            "schema_version": SCHEMA_VERSION,
            "ts": ts_str,
            "machine_id": self.machine_id,
            "predicted": {signal: round(predicted, 3)},
            "residual": {
                "signal": signal,
                "value": round(e, 3),
                "ewma": round(e, 3),
                "cusum": 0.0,
                "band": 0.5,
                "state": state.value,
            },
            "params": {
                "version": "v1.0",
                "values": {},
                "frozen": False,
                "freeze_reason": None,
            },
            "forecast": forecast,
            "risk": {
                "rules": rules,
                "model": None,
                "top_signals": top,
            },
        }

    def reset(self) -> None:
        self.calibrator.reset()
        self.residual.reset()
        self.alert_announced = False
        if self.template == "cnc_lathe":
            self.pred_temp = 310.8
        elif self.template == "cnc_mill":
            self.pred_temp = 311.5
        else:
            self.pred_temp = None
