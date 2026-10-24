"""Factory Engine orchestrating physical plant simulators, digital twins, and line flow.

Serves as the research core engine for the digital twin platform.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from sim.line import ProductionLine
from sim.plant import PlantMachine, TEMPLATE_PREFIX, NAMEPLATE_DEFAULTS, PRESSURE_MIN_BAR
from twin.model import DigitalTwin

SCHEMA_VERSION = "1.0"
TICK_S = 0.5


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


class FactoryEngine:
    """Orchestrates multi-machine plant instances, twin models, and production line flow."""

    def __init__(
        self,
        seed: int = 42,
        start: datetime | None = None,
        auto_demo: bool = True,
        machines: int = 4,
    ):
        self.seed = seed
        self.auto_demo = auto_demo
        self.n_machines = machines
        self.start = start or datetime(2026, 10, 26, 10, 0, 0, tzinfo=timezone.utc)
        self.t = 0.0
        self.demo_t = 0.0
        self.event_seq = 0
        self.pending_events: list[dict] = []
        self.registry_dirty = False
        self.common_cause_announced = False

        self.plants: dict[str, PlantMachine] = {}
        self.twins: dict[str, DigitalTwin] = {}
        self.line = ProductionLine()
        self.rng = random.Random(self.seed)

        self.reset(announce=False)

    def reset(self, announce: bool = True) -> list[dict]:
        self.rng = random.Random(self.seed)
        self.demo_t = 0.0
        self.plants.clear()
        self.twins.clear()
        self.line.reset()
        self.common_cause_announced = False
        self.pending_events.clear()

        # Add initial machines
        self._add_machine("cnc_mill", "CNC Mill (VMC)", hero=True, x=8.0, y=0.0, order=2)
        self._add_machine("cnc_lathe", "CNC Lathe", hero=False, x=4.0, y=0.0, order=1)
        self._add_machine("bar_saw", "Bar Saw", hero=False, x=0.0, y=0.0, order=0)
        if self.n_machines >= 4:
            self._add_machine("air_compressor", "Air Compressor", hero=False, x=4.0, y=-4.0, order=-1)

        self.registry_dirty = announce
        if announce:
            self._emit_event(None, "RESET", "INFO", "Simulation reset")
        return self.flush_events()

    def _add_machine(
        self,
        template: str,
        name: str,
        hero: bool = False,
        x: float = 0.0,
        y: float = 0.0,
        order: int | None = None,
        nameplate: dict | None = None,
    ) -> PlantMachine:
        prefix = TEMPLATE_PREFIX[template]
        count = 1 + sum(1 for m in self.plants.values() if m.template == template)
        mid = f"{prefix}-{count:02d}"
        if order is None:
            order = -1 if template == "air_compressor" else len(self.plants)

        plant = PlantMachine(
            machine_id=mid,
            template=template,
            name=name,
            hero=hero,
            x=x,
            y=y,
            order=order,
            nameplate=dict(NAMEPLATE_DEFAULTS.get(template, {}) | (nameplate or {})),
        )
        twin = DigitalTwin(machine_id=mid, template=template, hero=hero)

        self.plants[mid] = plant
        self.twins[mid] = twin
        return plant

    def hello(self) -> dict:
        return {
            "type": "hello",
            "schema_version": SCHEMA_VERSION,
            "generator": "udyam_core",
            "tick_ms": int(TICK_S * 1000),
        }

    def registry(self) -> dict:
        return {
            "type": "registry",
            "schema_version": SCHEMA_VERSION,
            "machines": [p.registry_entry() for p in self.plants.values()],
        }

    def command(self, cmd: dict) -> list[dict]:
        """Process incoming client command frame."""
        kind = cmd.get("cmd")
        out: list[dict] = []

        if kind == "inject_fault":
            mid = cmd.get("machine_id", "")
            plant = self.plants.get(mid)
            if plant:
                fault = cmd["fault"]
                plant.faults.inject(fault, self.t)
                self._emit_event(
                    plant.machine_id,
                    "FAULT_INJECTED",
                    "INFO",
                    f"Injected '{fault}' on {plant.name} (plant only; the twin is not told)",
                    data={"fault": fault},
                )
        elif kind == "clear_faults":
            targets = [self.plants[cmd["machine_id"]]] if cmd.get("machine_id") in self.plants else self.plants.values()
            for plant in targets:
                plant.faults.clear()
        elif kind == "reset":
            events = self.reset()
            self.registry_dirty = False
            return [self.registry()] + events
        elif kind == "auto_demo":
            self.auto_demo = bool(cmd.get("on", True))
        elif kind == "set_derate":
            plant = self.plants.get(cmd.get("machine_id", ""))
            if plant:
                plant.derate_pct = max(0.0, min(100.0, float(cmd.get("pct", 0))))
        elif kind == "add_machine":
            tpl = cmd.get("template", "air_compressor")
            if tpl in TEMPLATE_PREFIX:
                plant = self._add_machine(
                    tpl,
                    cmd.get("name") or tpl.replace("_", " ").title(),
                    x=float(cmd.get("x", 4.0 * len(self.plants))),
                    y=float(cmd.get("y", -4.0)),
                    nameplate=cmd.get("nameplate"),
                )
                self._emit_event(
                    plant.machine_id,
                    "MACHINE_ADDED",
                    "INFO",
                    f"{plant.name} onboarded from '{tpl}' template",
                    data={"template": tpl, "calibration": "starting from template defaults"},
                )
                out.append(self.registry())

        return out + self.flush_events()

    def _emit_event(
        self,
        machine_id: str | None,
        kind: str,
        severity: str,
        title: str,
        measured: str | None = None,
        inferred: str | None = None,
        suggested: str | None = None,
        data: dict | None = None,
    ) -> None:
        self.event_seq += 1
        ev: dict = {
            "type": "event",
            "schema_version": SCHEMA_VERSION,
            "ts": self._ts(),
            "event_id": f"E{self.event_seq:05d}",
            "machine_id": machine_id,
            "kind": kind,
            "severity": severity,
            "title": title,
        }
        if measured is not None:
            ev["measured"] = measured
        if inferred is not None:
            ev["inferred"] = inferred
        if suggested is not None:
            ev["suggested"] = suggested
        if data is not None:
            ev["data"] = data
        self.pending_events.append(ev)

    def flush_events(self) -> list[dict]:
        flushed = list(self.pending_events)
        self.pending_events.clear()
        return flushed

    def _ts(self) -> str:
        return _iso(self.start + timedelta(seconds=self.t))

    def step(self) -> list[dict]:
        """Advance the factory simulation by one 500ms tick."""
        self.t += TICK_S
        if self.auto_demo:
            self._handle_auto_demo()

        comp = next((p for p in self.plants.values() if p.template == "air_compressor"), None)
        air_ok = comp.pressure_bar >= PRESSURE_MIN_BAR if comp else True

        out: list[dict] = []
        if self.registry_dirty:
            self.registry_dirty = False
            out.append(self.registry())

        ts_str = self._ts()

        # Step compressor
        if comp:
            obs = comp.step_compressor(self.rng, ts_str)
            twin = self.twins[comp.machine_id]
            out.extend([obs, twin.step_simple(obs)])

        # Common cause detection
        self._check_common_cause(air_ok)

        # Step CNC machines and saws
        for mid, plant in self.plants.items():
            twin = self.twins[mid]
            if plant.template in ("cnc_mill", "cnc_lathe"):
                obs, plant_events = plant.step_cnc(self.t, self.rng, air_ok, ts_str)
                self.pending_events.extend(plant_events)
                is_bearing = plant.faults.is_active("bearing_defect")
                twin_msg, twin_events, proposed_derate = twin.step_cnc(obs, is_bearing)
                self.pending_events.extend(twin_events)
                if proposed_derate is not None:
                    plant.derate_pct = proposed_derate
                out.extend([obs, twin_msg])
            elif plant.template == "bar_saw":
                obs = plant.step_saw(self.rng, ts_str)
                out.extend([obs, twin.step_simple(obs)])

        # Step production line
        line_msg = self.line.step(self.plants, air_ok, ts_str)
        out.append(line_msg)

        return out + self.flush_events()

    def _check_common_cause(self, air_ok: bool) -> None:
        if not air_ok and not self.common_cause_announced:
            self.common_cause_announced = True
            affected = [p.machine_id for p in self.plants.values() if p.template in ("cnc_mill", "cnc_lathe")]
            self._emit_event(
                "COMP-01",
                "COMMON_CAUSE",
                "WARN",
                "Common cause: compressed-air supply low",
                measured=f"Pressure below {PRESSURE_MIN_BAR} bar; {', '.join(affected)} derated together",
                inferred="Root cause is the shared compressor, not the individual machines",
                suggested="Inspect compressor intake filter and leaks; do not service the CNCs",
                data={"affected": affected},
            )
        elif air_ok:
            self.common_cause_announced = False

    def _handle_auto_demo(self) -> None:
        """Execute the scripted 150-second demonstration cycle."""
        self.demo_t += TICK_S
        t = round(self.demo_t, 1)
        mill = self.plants.get("VMC-01")
        comp = self.plants.get("COMP-01")

        if t == 5.0 and mill:
            mill.faults.inject("coolant_degradation", self.t)
            self._emit_event(
                mill.machine_id,
                "FAULT_INJECTED",
                "INFO",
                f"Injected 'coolant_degradation' on {mill.name} (plant only; the twin is not told)",
                data={"fault": "coolant_degradation"},
            )
        elif t == 105.0 and comp:
            comp.faults.inject("pressure_drop", self.t)
            self._emit_event(
                comp.machine_id,
                "FAULT_INJECTED",
                "INFO",
                f"Injected 'pressure_drop' on {comp.name} (plant only; the twin is not told)",
                data={"fault": "pressure_drop"},
            )
        elif t == 118.0 and comp:
            comp.faults.clear("pressure_drop")
            self._emit_event(
                comp.machine_id,
                "WORK_ORDER",
                "INFO",
                "Compressor filter replaced (work order closed)",
                data={"status": "Closed"},
            )
        elif t == 125.0 and mill:
            mill.faults.inject("bearing_defect", self.t)
            self._emit_event(
                mill.machine_id,
                "FAULT_INJECTED",
                "INFO",
                f"Injected 'bearing_defect' on {mill.name} (plant only; the twin is not told)",
                data={"fault": "bearing_defect"},
            )
        elif t >= 145.0:
            reset_events = self.reset()
            self.pending_events.extend(reset_events)
            self.demo_t = 0.0
