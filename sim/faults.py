"""Fault definitions and management for the plant simulator.

Conforms strictly to docs/schema.json fault enum.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class FaultType(str, Enum):
    COOLANT_DEGRADATION = "coolant_degradation"
    BEARING_DEFECT = "bearing_defect"
    OVERLOAD = "overload"
    TOOL_WEAR_ACCEL = "tool_wear_accel"
    SENSOR_STUCK = "sensor_stuck"
    SENSOR_DROPOUT = "sensor_dropout"
    ORDER_SURGE = "order_surge"
    PRESSURE_DROP = "pressure_drop"
    BLADE_WEAR = "blade_wear"


@dataclass
class FaultManager:
    """Tracks active faults and the simulation timestamp when each was injected."""

    active_faults: set[str] = field(default_factory=set)
    injection_timestamps: dict[str, float] = field(default_factory=dict)

    def inject(self, fault: str, t: float) -> bool:
        """Inject a fault at time t. Returns True if newly added."""
        if fault not in [f.value for f in FaultType]:
            raise ValueError(f"Unknown fault: {fault}")
        is_new = fault not in self.active_faults
        self.active_faults.add(fault)
        self.injection_timestamps[fault] = t
        return is_new

    def clear(self, fault: str | None = None) -> None:
        """Clear a specific fault or all faults if None."""
        if fault is None:
            self.active_faults.clear()
            self.injection_timestamps.clear()
        else:
            self.active_faults.discard(fault)
            self.injection_timestamps.pop(fault, None)

    def is_active(self, fault: str) -> bool:
        return fault in self.active_faults

    def primary_fault(self) -> str | None:
        """Return the deterministically sorted first active fault, or None."""
        if not self.active_faults:
            return None
        return next(iter(sorted(self.active_faults)))

    def time_since(self, fault: str, current_t: float) -> float:
        """Elapsed simulation seconds since the fault was injected, or 0.0."""
        t0 = self.injection_timestamps.get(fault)
        return max(0.0, current_t - t0) if t0 is not None else 0.0
