"""Residual computation, CUSUM drift detection, and anomaly detection.

Monitors the prediction error e = y_observed - y_predicted and classifies
system health into IN_BAND, DRIFT, or ANOMALY.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ResidualState(str, Enum):
    IN_BAND = "IN_BAND"
    DRIFT = "DRIFT"
    ANOMALY = "ANOMALY"


@dataclass
class ResidualTracker:
    """Tracks prediction error, EWMA smoothing, CUSUM statistics and anomaly spikes."""

    signal: str = "process_temp_k"
    band: float = 0.6
    k_cusum: float = 0.2
    h_cusum: float = 2.5

    ewma: float = 0.0
    cusum: float = 0.0
    vib_ewma: float = 2.2
    y_filt: float | None = None
    dy_filt: float = 0.0

    frozen_reason: str | None = None
    drift_announced: bool = False
    anomaly_announced: bool = False

    def update(
        self,
        *,
        obs_val: float | None,
        pred_val: float,
        vibration_rms: float,
        dq_flag: str,
        is_bearing_defect: bool = False,
        tick_s: float = 0.5,
    ) -> tuple[float, ResidualState, bool, bool]:
        """Update residual statistics.

        Returns:
            (residual_value, residual_state, is_new_drift, is_new_anomaly)
        """
        if obs_val is None:
            e = 0.0
        else:
            e = obs_val - pred_val

        # Low-pass filter for steady-state projection
        if obs_val is not None and dq_flag == "OK":
            prev = self.y_filt if self.y_filt is not None else obs_val
            self.y_filt = 0.9 * prev + 0.1 * obs_val
            self.dy_filt = 0.9 * self.dy_filt + 0.1 * (self.y_filt - prev) / tick_s

        self.ewma = 0.9 * self.ewma + 0.1 * e
        self.cusum = max(0.0, self.cusum + abs(e) - self.k_cusum)

        # Vibration anomaly spike detection
        z_spike = abs(vibration_rms - self.vib_ewma) > 2.5
        self.vib_ewma = 0.95 * self.vib_ewma + 0.05 * vibration_rms

        # Freeze conditions: bad data quality or physical abrupt anomaly
        if dq_flag != "OK":
            self.frozen_reason = "data_quality"
        elif z_spike or is_bearing_defect:
            self.frozen_reason = "anomaly"
        elif self.frozen_reason and not is_bearing_defect and dq_flag == "OK":
            self.frozen_reason = None

        # Residual state classification
        new_anomaly = False
        new_drift = False

        if self.frozen_reason == "anomaly":
            state = ResidualState.ANOMALY
            if not self.anomaly_announced:
                self.anomaly_announced = True
                new_anomaly = True
        elif self.cusum > self.h_cusum and abs(self.ewma) > self.band / 2.0:
            state = ResidualState.DRIFT
            if not self.drift_announced:
                self.drift_announced = True
                new_drift = True
        else:
            state = ResidualState.IN_BAND

        return e, state, new_drift, new_anomaly

    def reset(self) -> None:
        self.ewma = 0.0
        self.cusum = 0.0
        self.vib_ewma = 2.2
        self.y_filt = None
        self.dy_filt = 0.0
        self.frozen_reason = None
        self.drift_announced = False
        self.anomaly_announced = False
