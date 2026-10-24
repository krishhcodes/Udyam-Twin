"""Virtual PLC state machine and safety interlocks.

Evaluates scan-cycle states: IDLE -> RUN -> DERATE -> TRIP.
"""

from __future__ import annotations

from enum import Enum


class PlcState(str, Enum):
    IDLE = "IDLE"
    RUN = "RUN"
    DERATE = "DERATE"
    TRIP = "TRIP"


class VirtualPlc:
    """Software virtual PLC with interlocks and scan-cycle evaluation."""

    def __init__(self, vib_trip_threshold: float = 9.94):
        self.state: PlcState = PlcState.RUN
        self.vib_trip_threshold = vib_trip_threshold

    def evaluate(
        self,
        *,
        has_critical_trip: bool = False,
        vibration_rms: float = 0.0,
        derate_pct: float = 0.0,
        is_idle: bool = False,
    ) -> PlcState:
        """Scan cycle: evaluate interlocks and return current PLC state."""
        if has_critical_trip or (vibration_rms > self.vib_trip_threshold):
            self.state = PlcState.TRIP
        elif is_idle:
            self.state = PlcState.IDLE
        elif derate_pct > 0.0:
            self.state = PlcState.DERATE
        else:
            self.state = PlcState.RUN
        return self.state

    @property
    def is_running(self) -> bool:
        return self.state in (PlcState.RUN, PlcState.DERATE)

    def speed_factor(self, derate_pct: float = 0.0) -> float:
        if self.state == PlcState.TRIP or self.state == PlcState.IDLE:
            return 0.0
        if self.state == PlcState.DERATE:
            return max(0.0, 1.0 - derate_pct / 100.0)
        return 1.0
