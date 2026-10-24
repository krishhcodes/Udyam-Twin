"""Production line model simulating material buffers and inter-machine dependencies.

Computes line throughput, bottleneck identification, starvation/blocking states,
and financial line loss estimates.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sim.plant import PlantMachine

SCHEMA_VERSION = "1.0"
TICK_S = 0.5
TIME_SCALE = 30
LINE_FLOW = [("SAW-01", 20.0), ("LATHE-01", 25.0), ("VMC-01", 30.0)]
BUFFER_CAP = 10
INR_PER_PART = 450.0


class ProductionLine:
    """Simulates inter-machine buffer queues, cycle progression and line throughput."""

    def __init__(self, inr_per_part: float = INR_PER_PART):
        self.inr_per_part = inr_per_part
        self.buffers: dict[str, int] = {mid: 4 for mid, _ in LINE_FLOW[1:]}
        self.progress: dict[str, float] = {mid: 0.0 for mid, _ in LINE_FLOW}
        self.nominal_rate = 3600.0 / LINE_FLOW[-1][1] / TIME_SCALE
        self.rate_ewma = self.nominal_rate

    def reset(self) -> None:
        self.buffers = {mid: 4 for mid, _ in LINE_FLOW[1:]}
        self.progress = {mid: 0.0 for mid, _ in LINE_FLOW}
        self.rate_ewma = self.nominal_rate

    def step(self, machines: dict[str, PlantMachine], air_ok: bool, ts_str: str) -> dict:
        """Step the production line forward by one tick and generate 'line' message."""
        stations = []
        mill_rate_factor = 0.0

        for i, (mid, cycle) in enumerate(LINE_FLOW):
            m = machines.get(mid)
            if not m:
                continue

            has_input = i == 0 or self.buffers.get(mid, 0) > 0
            nxt = LINE_FLOW[i + 1][0] if i + 1 < len(LINE_FLOW) else None
            has_space = nxt is None or self.buffers.get(nxt, 0) < BUFFER_CAP

            derate = m.derate_pct if m.template != "cnc_lathe" else 0.0
            if m.template in ("cnc_mill", "cnc_lathe") and not air_ok:
                derate = max(derate, 25.0)

            if m.plc.state.value == "TRIP":
                state, speed = "DOWN", 0.0
            elif not has_input:
                state, speed = "STARVED", 0.0
            elif not has_space:
                state, speed = "BLOCKED", 0.0
            elif derate > 0:
                state, speed = "DERATED", max(0.0, 1.0 - derate / 100.0)
            else:
                state, speed = "RUNNING", 1.0

            self.progress[mid] += speed * TICK_S / cycle
            if self.progress[mid] >= 1.0:
                self.progress[mid] = 0.0
                if i > 0 and mid in self.buffers:
                    self.buffers[mid] -= 1
                if nxt and nxt in self.buffers:
                    self.buffers[nxt] += 1
                m.parts_done += 1

            if nxt is None:
                mill_rate_factor = speed

            stations.append({
                "machine_id": mid,
                "state": state,
                "buffer_in": 0 if i == 0 else self.buffers.get(mid, 0),
                "buffer_cap": BUFFER_CAP,
            })

        self.rate_ewma = 0.97 * self.rate_ewma + 0.03 * self.nominal_rate * mill_rate_factor
        effective = {s["machine_id"]: (0.0 if s["state"] == "DOWN" else 1.0) for s in stations}
        bottleneck = min(LINE_FLOW, key=lambda mc: effective.get(mc[0], 0.0) / mc[1])[0]
        line_loss = round(max(0.0, self.nominal_rate - self.rate_ewma) * self.inr_per_part, 0)

        return {
            "type": "line",
            "schema_version": SCHEMA_VERSION,
            "ts": ts_str,
            "throughput_parts_per_hr": round(self.rate_ewma, 2),
            "line_loss_inr_per_hr": line_loss,
            "bottleneck": bottleneck,
            "air_supply_ok": air_ok,
            "stations": stations,
        }
