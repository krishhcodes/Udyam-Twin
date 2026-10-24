"""Plant simulator for physical machine assets (hidden 'true' machine).

Produces schema-compliant 'observed' messages under SIM mode.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Any

from sim.faults import FaultManager
from sim.plc import PlcState, VirtualPlc

SCHEMA_VERSION = "1.0"
TICK_S = 0.5
TEMP_LIMIT_K = 315.5
VIB_ZONE_C = 4.5
VIB_ZONE_D = 7.1
PRESSURE_MIN_BAR = 6.0

TEMPLATE_PREFIX = {
    "cnc_mill": "VMC",
    "cnc_lathe": "LATHE",
    "bar_saw": "SAW",
    "air_compressor": "COMP",
}

NAMEPLATE_DEFAULTS = {
    "cnc_mill": {"rated_kw": 11.0, "max_rpm": 3000, "make": "Representative VMC (geometry: TseNC)", "year": 2012},
    "cnc_lathe": {"rated_kw": 7.5, "max_rpm": 3500, "make": "Generic CNC lathe", "year": 2010},
    "bar_saw": {"rated_kw": 2.2, "max_rpm": 1400, "make": "Generic bar saw", "year": 2008},
    "air_compressor": {"rated_kw": 7.5, "rated_pressure_bar": 8.0, "make": "Generic screw compressor", "year": 2015},
}


@dataclass
class PlantMachine:
    """Represents the physical plant of a machine with true hidden state."""

    machine_id: str
    template: str
    name: str
    hero: bool = False
    x: float = 0.0
    y: float = 0.0
    order: int = 0
    nameplate: dict = field(default_factory=dict)

    # Faults and PLC
    faults: FaultManager = field(default_factory=FaultManager)
    plc: VirtualPlc = field(default_factory=VirtualPlc)
    derate_pct: float = 0.0

    # CNC physical state
    air_temp_k: float = 300.0
    process_temp_k: float = 311.5
    tool_wear_min: float = 118.0
    h_true: float = 1.0  # true cooling capacity multiplier (hidden ground truth)
    vibration: float = 2.2
    parts_done: int = 0
    last_temp_readings: list[float] = field(default_factory=list)

    # Saw & Compressor state
    blade_wear_pct: float = 35.0
    pressure_bar: float = 7.0
    discharge_temp_c: float = 82.0

    def __post_init__(self):
        if not self.nameplate:
            self.nameplate = dict(NAMEPLATE_DEFAULTS.get(self.template, {}))
        if self.template == "cnc_lathe":
            self.tool_wear_min = 64.0
            self.process_temp_k = 310.8

    def registry_entry(self) -> dict:
        return {
            "machine_id": self.machine_id,
            "template": self.template,
            "name": self.name,
            "hero": self.hero,
            "layout": {"x": self.x, "y": self.y, "order": self.order},
            "nameplate": self.nameplate,
        }

    def step_cnc(self, t: float, rng: random.Random, air_ok: bool, ts_str: str) -> tuple[dict, list[dict]]:
        """Advance CNC mill or lathe plant dynamics by one tick."""
        is_mill = self.template == "cnc_mill"
        events: list[dict] = []

        # Air-pressure interlock derates CNCs by 25% if air pressure is insufficient
        air_derate = 0.0 if air_ok else 25.0
        effective_derate = max(self.derate_pct, air_derate)

        # Critical trip condition for bearing defect
        has_trip = self.faults.is_active("bearing_defect") and self.vibration > VIB_ZONE_D * 1.4
        plc_state = self.plc.evaluate(
            has_critical_trip=has_trip,
            vibration_rms=self.vibration,
            derate_pct=effective_derate,
        )
        running = self.plc.is_running

        # Spindle mechanics
        rpm_nominal = 1540.0 if is_mill else 1800.0
        rpm_set = rpm_nominal * (1.0 - effective_derate / 100.0)
        torque_nominal = 40.0 if is_mill else 30.0
        torque = torque_nominal + rng.gauss(0.0, 1.2)
        if self.faults.is_active("overload"):
            torque += 22.0

        rpm = (rpm_set + rng.gauss(0.0, 8.0)) if running else 0.0
        torque = torque if running else 0.0
        power_kw = torque * rpm * 2.0 * math.pi / 60.0 / 1000.0

        # Ambient and cooling dynamics
        self.air_temp_k = 300.0 + 0.4 * math.sin(t / 60.0) + rng.gauss(0.0, 0.05)
        if self.faults.is_active("coolant_degradation"):
            self.h_true = max(0.55, self.h_true - 0.005 * TICK_S)

        thermal_target = self.air_temp_k + 8.0 + 0.7 * power_kw / self.h_true
        self.process_temp_k += (thermal_target - self.process_temp_k) * TICK_S / 20.0

        # Tool wear progression
        wear_rate = 0.05 * (rpm / 1540.0) * (4.0 if self.faults.is_active("tool_wear_accel") else 1.0)
        self.tool_wear_min += wear_rate
        if self.tool_wear_min > 235.0:
            self.tool_wear_min = 0.0
            events.append({
                "type": "event",
                "schema_version": SCHEMA_VERSION,
                "ts": ts_str,
                "machine_id": self.machine_id,
                "kind": "WORK_ORDER",
                "severity": "INFO",
                "title": "Tool changed at end of life (wear reset)",
            })

        # Vibration dynamics
        if self.faults.is_active("bearing_defect"):
            dt = self.faults.time_since("bearing_defect", t)
            base_vib = 6.5 + 0.08 * dt
        else:
            base_vib = 2.0 + 0.25 * (rpm / 1540.0) ** 2
        self.vibration = max(0.0, base_vib + rng.gauss(0.0, 0.12)) if running else 0.3

        # Sensor readings and Data Quality (DQ) simulation
        temp_reading: float | None = self.process_temp_k + rng.gauss(0.0, 0.15)
        dq = "OK"
        if self.faults.is_active("sensor_stuck"):
            temp_reading = self.last_temp_readings[-1] if self.last_temp_readings else temp_reading
        if self.faults.is_active("sensor_dropout"):
            temp_reading, dq = None, "MISSING"

        if temp_reading is not None:
            self.last_temp_readings = (self.last_temp_readings + [round(temp_reading, 2)])[-8:]
            if len(self.last_temp_readings) == 8 and len(set(self.last_temp_readings)) == 1:
                dq = "STUCK"

        current_a = round(1.2 + power_kw * 1.6 + rng.gauss(0.0, 0.1), 2)
        observed = {
            "type": "observed",
            "schema_version": SCHEMA_VERSION,
            "ts": ts_str,
            "machine_id": self.machine_id,
            "template": self.template,
            "source_mode": "SIM",
            "plc_state": plc_state.value,
            "dq_flag": dq,
            "power_kw": round(power_kw, 3),
            "current_a": current_a,
            "vibration_rms_mm_s": round(self.vibration, 2),
            "derate_pct": effective_derate,
            "active_fault": self.faults.primary_fault(),
            "parts_done": self.parts_done,
            "air_temp_k": round(self.air_temp_k, 2),
            "process_temp_k": None if temp_reading is None else round(temp_reading, 2),
            "rpm": round(rpm, 1),
            "torque_nm": round(torque, 2),
            "tool_wear_min": round(self.tool_wear_min, 1),
        }
        return observed, events

    def step_saw(self, rng: random.Random, ts_str: str) -> dict:
        """Advance bar saw plant dynamics by one tick."""
        if self.faults.is_active("blade_wear"):
            self.blade_wear_pct = min(100.0, self.blade_wear_pct + 0.3)
        else:
            self.blade_wear_pct = min(100.0, self.blade_wear_pct + 0.005)

        has_trip = self.blade_wear_pct >= 95.0
        plc_state = self.plc.evaluate(has_critical_trip=has_trip, derate_pct=self.derate_pct)
        running = self.plc.is_running

        rpm = (900.0 * (1.0 - self.derate_pct / 100.0) + rng.gauss(0.0, 5.0)) if running else 0.0
        power = (1.4 + 0.006 * self.blade_wear_pct + rng.gauss(0.0, 0.03)) if running else 0.05
        self.vibration = (1.6 + 0.02 * self.blade_wear_pct + rng.gauss(0.0, 0.08)) if running else 0.2

        return {
            "type": "observed",
            "schema_version": SCHEMA_VERSION,
            "ts": ts_str,
            "machine_id": self.machine_id,
            "template": self.template,
            "source_mode": "SIM",
            "plc_state": plc_state.value,
            "dq_flag": "OK",
            "power_kw": round(power, 3),
            "current_a": round(power * 1.9, 2),
            "vibration_rms_mm_s": round(self.vibration, 2),
            "derate_pct": self.derate_pct,
            "active_fault": self.faults.primary_fault(),
            "parts_done": self.parts_done,
            "rpm": round(rpm, 1),
            "blade_wear_pct": round(self.blade_wear_pct, 1),
        }

    def step_compressor(self, rng: random.Random, ts_str: str) -> dict:
        """Advance air compressor dynamics by one tick."""
        target_p = 5.2 if self.faults.is_active("pressure_drop") else 7.0
        self.pressure_bar += (target_p - self.pressure_bar) * TICK_S / 6.0 + rng.gauss(0.0, 0.03)

        duty = 100.0 if self.faults.is_active("pressure_drop") else 55.0 + rng.gauss(0.0, 2.0)
        temp_target = 95.0 if duty > 90.0 else 82.0
        self.discharge_temp_c += (temp_target - self.discharge_temp_c) * TICK_S / 15.0

        rated_kw = float(self.nameplate.get("rated_kw", 7.5))
        power = rated_kw * (0.35 + 0.65 * duty / 100.0)
        self.vibration = 2.8 + rng.gauss(0.0, 0.1)
        self.plc.state = PlcState.RUN

        return {
            "type": "observed",
            "schema_version": SCHEMA_VERSION,
            "ts": ts_str,
            "machine_id": self.machine_id,
            "template": self.template,
            "source_mode": "SIM",
            "plc_state": "RUN",
            "dq_flag": "OK",
            "power_kw": round(power, 3),
            "current_a": round(power * 1.8, 2),
            "vibration_rms_mm_s": round(self.vibration, 2),
            "derate_pct": 0.0,
            "active_fault": self.faults.primary_fault(),
            "parts_done": None,
            "pressure_bar": round(self.pressure_bar, 2),
            "discharge_temp_c": round(self.discharge_temp_c, 1),
            "duty_pct": round(duty, 1),
        }
