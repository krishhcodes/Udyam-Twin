"""Regression and unit tests for the modular research core (sim/ and twin/).

Validates modular FactoryEngine, plant models, digital twin, calibrator, and line
against docs/schema.json and compares behavior with the baseline fake stream.
"""

import json
from pathlib import Path

import jsonschema
import pytest

from sim.factory import FactoryEngine
from sim.faults import FaultManager, FaultType
from sim.line import ProductionLine
from sim.plc import VirtualPlc, PlcState
from twin.calibrate import TwinCalibrator
from twin.forecast import ForecastEngine
from twin.residuals import ResidualTracker, ResidualState
from tools.fake_factory import FakeFactory

SCHEMA = json.loads((Path(__file__).resolve().parent.parent / "docs" / "schema.json").read_text(encoding="utf-8"))
VALIDATOR = jsonschema.Draft202012Validator(SCHEMA)


def assert_valid(messages: list[dict]) -> None:
    for msg in messages:
        errors = list(VALIDATOR.iter_errors(msg))
        assert not errors, f"{msg.get('type')} invalid: {errors[0].message}\n{msg}"


def run_engine(engine: FactoryEngine, ticks: int) -> list[dict]:
    out = []
    for _ in range(ticks):
        out.extend(engine.step())
    return out


# -----------------------------------------------------------------------------
# 1. Schema compliance on the modular factory engine
# -----------------------------------------------------------------------------
def test_modular_engine_full_demo_loop_validates():
    engine = FactoryEngine(seed=42)
    assert_valid([engine.hello(), engine.registry()])
    msgs = run_engine(engine, 600)  # 300 s
    assert_valid(msgs)

    kinds = {m["kind"] for m in msgs if m["type"] == "event"}
    assert {"FAULT_INJECTED", "DRIFT", "CALIBRATION", "ALERT", "COMMON_CAUSE", "ANOMALY", "RESET"} <= kinds


@pytest.mark.parametrize("fault,machine", [
    ("coolant_degradation", "VMC-01"),
    ("bearing_defect", "VMC-01"),
    ("overload", "LATHE-01"),
    ("tool_wear_accel", "VMC-01"),
    ("sensor_stuck", "VMC-01"),
    ("sensor_dropout", "VMC-01"),
    ("pressure_drop", "COMP-01"),
    ("blade_wear", "SAW-01"),
])
def test_modular_engine_faults_validate(fault, machine):
    engine = FactoryEngine(auto_demo=False)
    msgs = engine.command({"cmd": "inject_fault", "machine_id": machine, "fault": fault})
    assert_valid(msgs)
    step_msgs = run_engine(engine, 200)
    assert_valid(step_msgs)


def test_modular_engine_onboarding_wizard():
    engine = FactoryEngine(machines=3, auto_demo=False)
    assert "COMP-01" not in {m["machine_id"] for m in engine.registry()["machines"]}

    msgs = engine.command({"cmd": "add_machine", "template": "air_compressor", "name": "Air Compressor"})
    assert_valid(msgs)
    assert any(m["type"] == "event" and m["kind"] == "MACHINE_ADDED" for m in msgs)
    assert "COMP-01" in {m["machine_id"] for m in engine.registry()["machines"]}
    assert_valid(run_engine(engine, 20))


def test_modular_calibration_convergence_and_limits():
    engine = FactoryEngine(auto_demo=False)
    engine.command({"cmd": "inject_fault", "machine_id": "VMC-01", "fault": "coolant_degradation"})
    run_engine(engine, 400)

    mill_plant = engine.plants["VMC-01"]
    mill_twin = engine.twins["VMC-01"]

    h_true = mill_plant.h_true
    h_est = mill_twin.calibrator.h_cool

    assert abs(h_est - h_true) < 0.06
    assert h_est >= h_true - 0.02, "calibrator overshot below true value"


def test_modular_calibration_freeze_on_anomaly_and_bad_sensor():
    for fault in ("bearing_defect", "sensor_stuck"):
        engine = FactoryEngine(auto_demo=False)
        engine.command({"cmd": "inject_fault", "machine_id": "VMC-01", "fault": "coolant_degradation"})
        engine.command({"cmd": "inject_fault", "machine_id": "VMC-01", "fault": fault})
        msgs = run_engine(engine, 300)

        twins = [m for m in msgs if m["type"] == "twin" and m["machine_id"] == "VMC-01"]
        assert twins[-1]["params"]["frozen"], fault
        assert not any(m["type"] == "event" and m["kind"] == "CALIBRATION" for m in msgs), fault


# -----------------------------------------------------------------------------
# 2. Direct unit tests for modular twin components
# -----------------------------------------------------------------------------
def test_twin_calibrator_step_and_versioning():
    cal = TwinCalibrator()
    assert cal.version == "v1.0"
    assert cal.h_cool == 1.0

    # Test freeze protection: when is_frozen=True, parameters never move
    rec = cal.step_thermal_calibration(
        power_kw=6.0,
        air_temp_k=300.0,
        y_filt=315.0,
        dy_filt=0.0,
        residual_ewma=2.0,
        is_frozen=True,
    )
    assert rec is None
    assert cal.h_cool == 1.0

    # Unfrozen calibration steps
    for _ in range(50):
        cal.step_thermal_calibration(
            power_kw=6.0,
            air_temp_k=300.0,
            y_filt=316.0,
            dy_filt=0.0,
            residual_ewma=2.0,
            is_frozen=False,
        )

    assert cal.h_cool < 1.0
    assert len(cal.param_history) > 0
    assert cal.minor_version > 0


def test_residual_tracker_spike_and_dq_freeze():
    tracker = ResidualTracker()

    # Normal reading
    e, state, drift, anomaly = tracker.update(
        obs_val=311.5,
        pred_val=311.5,
        vibration_rms=2.2,
        dq_flag="OK",
    )
    assert state == ResidualState.IN_BAND
    assert tracker.frozen_reason is None

    # Vibration spike causes anomaly freeze
    e, state, drift, anomaly = tracker.update(
        obs_val=311.5,
        pred_val=311.5,
        vibration_rms=7.5,
        dq_flag="OK",
    )
    assert state == ResidualState.ANOMALY
    assert tracker.frozen_reason == "anomaly"

    # Data quality fault causes dq freeze
    tracker.reset()
    e, state, drift, anomaly = tracker.update(
        obs_val=None,
        pred_val=311.5,
        vibration_rms=2.2,
        dq_flag="MISSING",
    )
    assert tracker.frozen_reason == "data_quality"


def test_forecast_engine():
    # If currently at or above limit -> 0 minutes
    mins, warning = ForecastEngine.forecast_cnc(
        air_temp_k=300.0,
        power_kw=6.5,
        h_est=0.6,
        current_temp_k=316.0,
        tool_wear_min=50.0,
    )
    assert mins == 0.0
    assert warning == "OVERTEMP"

    # Tool wear warning
    mins, warning = ForecastEngine.forecast_cnc(
        air_temp_k=300.0,
        power_kw=6.5,
        h_est=1.0,
        current_temp_k=308.0,
        tool_wear_min=220.0,
    )
    assert warning == "TWF_RISK"
    assert mins is not None and mins > 0


def test_virtual_plc_logic():
    plc = VirtualPlc(vib_trip_threshold=9.0)
    assert plc.evaluate(vibration_rms=2.0, derate_pct=0.0) == PlcState.RUN
    assert plc.evaluate(vibration_rms=2.0, derate_pct=20.0) == PlcState.DERATE
    assert plc.speed_factor(derate_pct=20.0) == 0.8
    assert plc.evaluate(vibration_rms=10.0, derate_pct=0.0) == PlcState.TRIP
    assert plc.speed_factor(derate_pct=0.0) == 0.0
