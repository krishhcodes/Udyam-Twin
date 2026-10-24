"""Self-calibration engine for physical twin parameters.

Implements bounded, rate-limited recalibration of physical coefficients (theta)
with versioning, rollback, and safety freezes.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CalibrationRecord:
    param: str
    from_val: float
    to_val: float
    version: str
    residual_ewma: float


@dataclass
class TwinCalibrator:
    """Manages physical parameter estimation and versioning."""

    h_cool: float = 1.0
    k_heat: float = 1.0
    k_wear: float = 1.0

    major_version: int = 1
    minor_version: int = 0
    h_at_version: float = 1.0
    param_history: list[CalibrationRecord] = field(default_factory=list)

    @property
    def version(self) -> str:
        return f"v{self.major_version}.{self.minor_version}"

    @property
    def values(self) -> dict[str, float]:
        return {
            "h_cool": round(self.h_cool, 3),
            "k_heat": round(self.k_heat, 3),
            "k_wear": round(self.k_wear, 3),
        }

    def step_thermal_calibration(
        self,
        *,
        power_kw: float,
        air_temp_k: float,
        y_filt: float | None,
        dy_filt: float,
        residual_ewma: float,
        is_frozen: bool,
    ) -> CalibrationRecord | None:
        """Perform bounded, rate-limited calibration of h_cool."""
        if is_frozen or y_filt is None or power_kw <= 0.5:
            return None

        # Project steady-state to avoid thermal lag overshoot
        y_ss = y_filt + 20.0 * dy_filt
        temp_diff = max(0.5, y_ss - air_temp_k - 8.0)
        h_target = 0.7 * power_kw / temp_diff

        step = max(-0.015, min(0.015, 0.08 * (h_target - self.h_cool)))
        self.h_cool = max(0.4, min(1.2, self.h_cool + step))

        # Check if version threshold reached
        if abs(self.h_cool - self.h_at_version) >= 0.05:
            old_h = self.h_at_version
            self.minor_version += 1
            new_version = self.version
            record = CalibrationRecord(
                param="h_cool",
                from_val=round(old_h, 3),
                to_val=round(self.h_cool, 3),
                version=new_version,
                residual_ewma=round(residual_ewma, 3),
            )
            self.h_at_version = self.h_cool
            self.param_history.append(record)
            return record

        return None

    def update_tool_wear_operator(self, measured_wear_min: float, predicted_wear_min: float) -> CalibrationRecord | None:
        """Human-in-the-loop tool wear update from operator measurements."""
        if predicted_wear_min <= 0:
            return None
        ratio = measured_wear_min / predicted_wear_min
        self.k_wear = max(0.5, min(2.0, self.k_wear * ratio))
        self.minor_version += 1
        record = CalibrationRecord(
            param="k_wear",
            from_val=1.0,
            to_val=round(self.k_wear, 3),
            version=self.version,
            residual_ewma=0.0,
        )
        self.param_history.append(record)
        return record

    def reset(self) -> None:
        self.h_cool = 1.0
        self.k_heat = 1.0
        self.k_wear = 1.0
        self.major_version = 1
        self.minor_version = 0
        self.h_at_version = 1.0
        self.param_history.clear()
