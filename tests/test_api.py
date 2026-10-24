"""Integration tests for the production FastAPI application and REST endpoints."""

import pytest
from fastapi.testclient import TestClient

from api.app import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_api_health(client):
    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert data["mode"] == "SIMULATION"


def test_schema_endpoint(client):
    res = client.get("/schema.json")
    assert res.status_code == 200
    data = res.json()
    assert data["title"] == "UDYAM-TWIN stream message (v1.0)"


def test_api_registry(client):
    res = client.get("/api/registry")
    assert res.status_code == 200
    data = res.json()
    assert data["type"] == "registry"
    assert len(data["machines"]) >= 3


def test_fault_injection_and_clear(client):
    # Inject fault
    res = client.post("/api/faults/inject", json={"machine_id": "VMC-01", "fault": "coolant_degradation"})
    assert res.status_code == 200
    assert res.json()["status"] == "injected"

    # Clear faults
    res2 = client.post("/api/faults/clear", json={"machine_id": "VMC-01"})
    assert res2.status_code == 200
    assert res2.json()["status"] == "cleared"


def test_derate_endpoint(client):
    res = client.post("/api/derate", json={"machine_id": "VMC-01", "pct": 25.0})
    assert res.status_code == 200
    assert res.json()["pct"] == 25.0


def test_onboarding_wizard_endpoint(client):
    res = client.post("/api/machines", json={
        "template": "air_compressor",
        "name": "Custom Screw Compressor",
        "nameplate": {"rated_kw": 11.0, "rated_pressure_bar": 8.5},
    })
    assert res.status_code == 200
    assert res.json()["status"] == "machine_onboarded"


def test_work_order_crud_flow(client):
    # 1. Create work order
    res = client.post("/api/work-orders", json={
        "machine_id": "VMC-01",
        "title": "Check spindle coolant filter",
        "priority": "High",
        "notes": "Triggered by temperature drift warning",
    })
    assert res.status_code == 200
    wo = res.json()
    wo_id = wo["wo_id"]
    assert wo["status"] == "Open"

    # 2. List work orders
    res_list = client.get("/api/work-orders")
    assert res_list.status_code == 200
    orders = res_list.json()
    assert any(o["wo_id"] == wo_id for o in orders)

    # 3. Update work order
    res_up = client.patch(f"/api/work-orders/{wo_id}", json={
        "status": "In Progress",
        "notes": "Technician dispatched to inspect pump",
    })
    assert res_up.status_code == 200
    assert res_up.json()["status"] == "In Progress"


def test_tool_wear_human_in_the_loop_calibration(client):
    res = client.post("/api/tool-wear", json={
        "machine_id": "VMC-01",
        "measured_wear_min": 140.0,
    })
    assert res.status_code == 200
    assert res.json()["status"] == "calibrated"
    assert "k_wear" in res.json()


def test_economics_endpoints(client):
    # Get assumptions
    res = client.get("/api/economics")
    assert res.status_code == 200
    data = res.json()
    assert "assumptions" in data
    assert "formulas" in data
    assert data["assumptions"]["inr_per_part"] > 0

    # Update editable assumption
    res_up = client.post("/api/economics", json={"inr_per_part": 520.0})
    assert res_up.status_code == 200
    assert res_up.json()["assumptions"]["inr_per_part"] == 520.0

    # Restore default for test isolation
    res_restore = client.post("/api/economics", json={"inr_per_part": 450.0})
    assert res_restore.status_code == 200
    assert res_restore.json()["assumptions"]["inr_per_part"] == 450.0


def test_websocket_telemetry_flow(client):
    with client.websocket_connect("/ws/telemetry") as ws:
        hello = ws.receive_json()
        assert hello["type"] == "hello"

        registry = ws.receive_json()
        assert registry["type"] == "registry"

        # Send command over websocket
        ws.send_json({"cmd": "inject_fault", "machine_id": "VMC-01", "fault": "bearing_defect"})

        received_events = []
        for _ in range(50):
            msg = ws.receive_json()
            if msg.get("type") == "event":
                received_events.append(msg)
                if msg.get("kind") == "FAULT_INJECTED":
                    break

        assert any(e.get("kind") == "FAULT_INJECTED" for e in received_events)


def test_metrics_endpoint(client):
    res = client.get("/api/metrics")
    assert res.status_code == 200
    data = res.json()
    assert "rule_baseline" in data
    assert "random_forest" in data
    assert "honest_disclaimer" in data
    assert data["vibration_and_current_excluded_from_ml"] is True


def test_static_3d_assets_served(client):
    """Verify that all Blender-exported 3D GLB assets are served over HTTP."""
    from pathlib import Path
    assets_dir = Path(__file__).resolve().parent.parent / "assets" / "3d"
    assert (assets_dir / "udyam_factory.blend").exists()

    expected_assets = [
        ("saw_01.glb", 50000),
        ("lathe_01.glb", 50000),
        ("vmc_01.glb", 50000),
        ("comp_01.glb", 50000),
        ("factory_scene.glb", 200000),
    ]

    for filename, min_bytes in expected_assets:
        res = client.get(f"/assets/3d/{filename}")
        assert res.status_code == 200, f"Failed to fetch /assets/3d/{filename}"
        assert len(res.content) >= min_bytes, f"Asset {filename} size too small: {len(res.content)} bytes"

