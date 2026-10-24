"""Analytical forecasting for impending warnings and remaining life.

Projects current operating conditions forward in time using the calibrated
reduced-order model parameters.
"""

from __future__ import annotations

import math

TEMP_LIMIT_K = 315.5
TOOL_WEAR_LIMIT_MIN = 235.0
PRESSURE_MIN_BAR = 6.0
TICK_S = 0.5
TIME_SCALE = 30


class ForecastEngine:
    """Computes time-to-warning and failure risk horizons."""

    @staticmethod
    def forecast_cnc(
        *,
        air_temp_k: float,
        power_kw: float,
        h_est: float,
        current_temp_k: float,
        tool_wear_min: float,
    ) -> tuple[float | None, str | None]:
        """Calculate minutes to temperature or tool-wear warning at current operating conditions."""
        steady_state_temp = air_temp_k + 8.0 + 0.7 * power_kw / h_est
        minutes: float | None = None
        warning: str | None = None

        if current_temp_k >= TEMP_LIMIT_K:
            minutes, warning = 0.0, "OVERTEMP"
        elif steady_state_temp > TEMP_LIMIT_K and (steady_state_temp - current_temp_k) > 0.01:
            ratio = (steady_state_temp - TEMP_LIMIT_K) / (steady_state_temp - current_temp_k)
            if 0.0 < ratio < 1.0:
                secs = -20.0 * math.log(ratio)
                minutes = round(secs * TIME_SCALE / 60.0, 1)
                warning = "OVERTEMP"
        elif tool_wear_min > 200.0:
            remaining_min = max(0.0, TOOL_WEAR_LIMIT_MIN - tool_wear_min)
            minutes = round(remaining_min / 0.05 * TICK_S * TIME_SCALE / 60.0, 1)
            warning = "TWF_RISK"

        return minutes, warning

    @staticmethod
    def forecast_compressor(pressure_bar: float) -> tuple[float | None, str | None]:
        """Forecast low pressure condition."""
        if pressure_bar < PRESSURE_MIN_BAR:
            return 0.0, "PRESSURE_LOW"
        return None, None
