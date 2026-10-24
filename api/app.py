"""Production FastAPI application for UDYAM-TWIN.

Provides:
- Bidirectional WebSocket /ws/telemetry with schema v1.0 validation
- REST endpoints for faults, work orders, onboarding, parameters, and economics
- Static serving of web/ dashboard and /operator mobile view
- SQLite persistence for events, work orders, and calibration logs
"""

import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from api.db import (
    create_work_order,
    get_economics,
    get_events,
    get_parameter_history,
    init_db,
    list_work_orders,
    log_event,
    log_parameter_change,
    update_economics,
    update_work_order_status,
)
from sim.factory import FactoryEngine, TICK_S

ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = ROOT / "web"
DOCS_DIR = ROOT / "docs"

# Shared factory engine instance
factory_engine = FactoryEngine(seed=42, auto_demo=True, machines=4)
connected_clients: set = set()


class FaultInjectRequest(BaseModel):
    machine_id: str
    fault: str


class FaultClearRequest(BaseModel):
    machine_id: Optional[str] = None


class DerateRequest(BaseModel):
    machine_id: str
    pct: float


class AddMachineRequest(BaseModel):
    template: str
    name: Optional[str] = None
    x: Optional[float] = None
    y: Optional[float] = None
    nameplate: Optional[Dict[str, Any]] = None


class WorkOrderCreateRequest(BaseModel):
    machine_id: str
    title: str
    priority: Optional[str] = "Medium"
    notes: Optional[str] = ""


class WorkOrderUpdateRequest(BaseModel):
    status: str
    notes: Optional[str] = None
    tool_wear_measured: Optional[float] = None


class ToolWearEntryRequest(BaseModel):
    machine_id: str
    measured_wear_min: float
    wo_id: Optional[str] = None


class EconomicsUpdateRequest(BaseModel):
    inr_per_part: Optional[float] = None
    downtime_cost_per_hr: Optional[float] = None
    electricity_tariff_per_kwh: Optional[float] = None
    cea_co2_factor: Optional[float] = None
    sensor_node_cost_inr: Optional[float] = None


async def broadcast_messages(messages: List[Dict[str, Any]]) -> None:
    """Broadcast JSON payloads to all connected WebSocket clients and log events to SQLite."""
    if not messages:
        return

    # Persist events and parameter records to SQLite
    for m in messages:
        if m.get("type") == "event":
            log_event(m)
            if m.get("kind") == "CALIBRATION" and m.get("data"):
                data = m["data"]
                log_parameter_change(
                    machine_id=m.get("machine_id", "VMC-01"),
                    param=data.get("param", "h_cool"),
                    from_val=data.get("from", 1.0),
                    to_val=data.get("to", 1.0),
                    version=data.get("version", "v1.0"),
                    residual_ewma=data.get("residual_ewma", 0.0),
                    ts=m.get("ts"),
                )

    payloads = [json.dumps(m, ensure_ascii=False) for m in messages]
    dead_clients = set()
    for ws in list(connected_clients):
        try:
            for p in payloads:
                await ws.send_text(p)
        except Exception:
            dead_clients.add(ws)
    connected_clients.difference_update(dead_clients)


async def engine_ticker_loop() -> None:
    """Background ticker advancing simulation and broadcasting state every TICK_S."""
    while True:
        try:
            msgs = factory_engine.step()
            await broadcast_messages(msgs)
        except Exception as err:
            print(f"[ticker error]: {err}")
        await asyncio.sleep(TICK_S)


@asynccontextmanager
async def app_lifespan(app: FastAPI):
    # Startup: initialize database and launch ticker task
    init_db()
    task = asyncio.create_task(engine_ticker_loop())
    yield
    # Shutdown: cancel background ticker
    task.cancel()


app = FastAPI(
    title="UDYAM-TWIN Industrial Digital Twin API",
    description="Zero-licence self-calibrating digital twin backend for MSME machine shops",
    version="1.0.0",
    lifespan=app_lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# -----------------------------------------------------------------------------
# REST Endpoints
# -----------------------------------------------------------------------------
@app.get("/api/health")
def get_health():
    return {
        "status": "ok",
        "service": "udyam_twin_core",
        "mode": "SIMULATION",
        "schema_version": "1.0",
        "clients_connected": len(connected_clients),
    }


@app.get("/schema.json")
def get_schema():
    schema_path = DOCS_DIR / "schema.json"
    if schema_path.exists():
        return FileResponse(schema_path, media_type="application/json")
    raise HTTPException(status_code=404, detail="schema.json not found")


@app.get("/api/registry")
def get_registry():
    return factory_engine.registry()


@app.post("/api/faults/inject")
async def post_inject_fault(req: FaultInjectRequest):
    msgs = factory_engine.command({
        "cmd": "inject_fault",
        "machine_id": req.machine_id,
        "fault": req.fault,
    })
    await broadcast_messages(msgs)
    return {"status": "injected", "machine_id": req.machine_id, "fault": req.fault}


@app.post("/api/faults/clear")
async def post_clear_faults(req: FaultClearRequest):
    msgs = factory_engine.command({
        "cmd": "clear_faults",
        "machine_id": req.machine_id,
    })
    await broadcast_messages(msgs)
    return {"status": "cleared", "machine_id": req.machine_id}


@app.post("/api/derate")
async def post_set_derate(req: DerateRequest):
    msgs = factory_engine.command({
        "cmd": "set_derate",
        "machine_id": req.machine_id,
        "pct": req.pct,
    })
    await broadcast_messages(msgs)
    return {"status": "derate_applied", "machine_id": req.machine_id, "pct": req.pct}


@app.post("/api/machines")
async def post_add_machine(req: AddMachineRequest):
    """Onboard a new machine class into the digital twin floor."""
    cmd: Dict[str, Any] = {
        "cmd": "add_machine",
        "template": req.template,
        "name": req.name,
    }
    if req.x is not None:
        cmd["x"] = req.x
    if req.y is not None:
        cmd["y"] = req.y
    if req.nameplate is not None:
        cmd["nameplate"] = req.nameplate

    msgs = factory_engine.command(cmd)
    await broadcast_messages(msgs)
    return {"status": "machine_onboarded", "template": req.template, "name": req.name}


@app.post("/api/reset")
async def post_reset(auto_demo: Optional[bool] = None):
    msgs = factory_engine.command({"cmd": "reset"})
    if auto_demo is not None:
        factory_engine.auto_demo = auto_demo
    await broadcast_messages(msgs)
    return {"status": "reset", "auto_demo": factory_engine.auto_demo}


@app.post("/api/auto_demo")
def post_auto_demo(on: bool):
    factory_engine.auto_demo = on
    return {"auto_demo": factory_engine.auto_demo}


@app.get("/api/events")
def api_get_events(limit: int = 50):
    return get_events(limit=limit)


@app.get("/api/work-orders")
def api_get_work_orders():
    return list_work_orders()


@app.post("/api/work-orders")
async def api_create_work_order(req: WorkOrderCreateRequest):
    wo = create_work_order(
        machine_id=req.machine_id,
        title=req.title,
        priority=req.priority or "Medium",
        notes=req.notes or "",
    )
    # Broadcast work order event
    ev = {
        "type": "event",
        "schema_version": "1.0",
        "ts": wo["created_at"],
        "event_id": f"EV_{wo['wo_id']}",
        "machine_id": req.machine_id,
        "kind": "WORK_ORDER",
        "severity": "INFO",
        "title": f"Work order {wo['wo_id']} created: {req.title}",
        "data": wo,
    }
    await broadcast_messages([ev])
    return wo


@app.patch("/api/work-orders/{wo_id}")
async def api_update_work_order(wo_id: str, req: WorkOrderUpdateRequest):
    wo = update_work_order_status(
        wo_id=wo_id,
        status=req.status,
        notes=req.notes,
        tool_wear_measured=req.tool_wear_measured,
    )
    if not wo:
        raise HTTPException(status_code=404, detail="Work order not found")
    return wo


@app.post("/api/tool-wear")
async def post_tool_wear_entry(req: ToolWearEntryRequest):
    """Human-in-the-loop tool wear update: operator measures edge wear at tool change."""
    twin = factory_engine.twins.get(req.machine_id)
    if not twin:
        raise HTTPException(status_code=404, detail=f"Machine {req.machine_id} not found")

    cal_rec = twin.calibrator.update_tool_wear_operator(
        measured_wear_min=req.measured_wear_min,
        predicted_wear_min=twin.pred_wear,
    )

    ev = {
        "type": "event",
        "schema_version": "1.0",
        "ts": factory_engine._ts(),
        "event_id": f"EV_WEAR_UPDATE_{req.machine_id}",
        "machine_id": req.machine_id,
        "kind": "CALIBRATION",
        "severity": "INFO",
        "title": f"Operator feedback: tool-wear rate k_wear recalibrated to {twin.calibrator.k_wear:.2f}",
        "inferred": f"Measured wear {req.measured_wear_min:.1f} min vs predicted {twin.pred_wear:.1f} min",
        "suggested": "Calibration updated based on verified operator measurement",
        "data": {
            "param": "k_wear",
            "k_wear": round(twin.calibrator.k_wear, 3),
            "measured_wear_min": req.measured_wear_min,
        },
    }
    await broadcast_messages([ev])
    return {"status": "calibrated", "k_wear": twin.calibrator.k_wear}


@app.get("/api/parameters/history")
def api_get_parameter_history(machine_id: Optional[str] = None):
    return get_parameter_history(machine_id=machine_id)


@app.get("/api/economics")
def api_get_economics():
    """Retrieve MSME economics parameters, calculated metrics, and editable assumptions."""
    config = get_economics()
    return {
        "assumptions": config,
        "formulas": {
            "downtime_loss_inr": "breakdown_hours * downtime_cost_per_hr",
            "line_loss_inr_per_hr": "max(0, nominal_rate - current_rate) * inr_per_part",
            "energy_cost_inr": "sum(power_kw * hours) * electricity_tariff_per_kwh",
            "co2_emissions_kg": "kwh_consumed * cea_co2_factor (CEA Baseline v20 2024-25)",
            "payback_months": "(total_sensor_nodes * sensor_node_cost_inr) / monthly_avoided_breakdown_value",
        },
    }


@app.post("/api/economics")
def api_update_economics(req: EconomicsUpdateRequest):
    updates = {}
    for k, v in req.model_dump(exclude_unset=True).items():
        if v is not None:
            updates[k] = v
    new_config = update_economics(updates)
    return {"status": "updated", "assumptions": new_config}


@app.get("/api/metrics")
def api_get_metrics():
    """Return AI4I model training metrics and evaluation comparison against rule baseline."""
    metrics_file = ROOT / "ml" / "metrics.json"
    if metrics_file.exists():
        return json.loads(metrics_file.read_text(encoding="utf-8"))
    raise HTTPException(status_code=404, detail="Metrics not found")


# -----------------------------------------------------------------------------
# WebSocket Telemetry Channel
# -----------------------------------------------------------------------------
@app.websocket("/ws/telemetry")
async def websocket_telemetry_endpoint(ws: WebSocket):
    await ws.accept()
    # Initial connection handshakes per docs/SCHEMA.md
    await ws.send_text(json.dumps(factory_engine.hello()))
    await ws.send_text(json.dumps(factory_engine.registry(), ensure_ascii=False))
    connected_clients.add(ws)

    try:
        while True:
            text = await ws.receive_text()
            try:
                cmd = json.loads(text)
            except json.JSONDecodeError:
                continue
            # Process command on factory engine and broadcast output events
            out_msgs = factory_engine.command(cmd)
            await broadcast_messages(out_msgs)
    except WebSocketDisconnect:
        connected_clients.discard(ws)
    except Exception:
        connected_clients.discard(ws)


# -----------------------------------------------------------------------------
# Static UI Mounts
# -----------------------------------------------------------------------------
if WEB_DIR.exists():
    @app.get("/")
    def serve_index():
        index_file = WEB_DIR / "index.html"
        if index_file.exists():
            return FileResponse(index_file)
        # Fallback to stream viewer if web/index.html is not yet created
        return FileResponse(ROOT / "tools" / "stream_viewer.html")

    @app.get("/operator")
    def serve_operator():
        op_file = WEB_DIR / "operator.html"
        if op_file.exists():
            return FileResponse(op_file)
        return FileResponse(WEB_DIR / "index.html" if (WEB_DIR / "index.html").exists() else ROOT / "tools" / "stream_viewer.html")

    app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")
