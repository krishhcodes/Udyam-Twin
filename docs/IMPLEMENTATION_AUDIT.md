# UDYAM-TWIN: Architecture & Implementation Audit

**Audit Date:** 22 October 2026  
**Auditor:** Senior Software Architect  
**Repository:** `krishhcodes/Udyam-Twin`  
**Current Git Branch:** `feature/integration-audit` (base commit: `eaa42ee`)  
**Target Milestone:** INAE Youth Conclave 2026 (YEISS-2026), Hackathon Theme HT14  

---

## 1. Executive Summary

A comprehensive architectural audit of the **UDYAM-TWIN** repository was conducted to assess the gap between the planned system ([docs/MASTER_PLAN.md](file:///c:/Udyam-Twin/docs/MASTER_PLAN.md)) and the current implementation.

### Key Findings
1. **Repository Stage:** The repository is currently at the **Day 1 checkpoint** (`eaa42ee` — "Day 1 (R1): freeze schema v1.0, scaffold repo, add fake stream").
2. **Contract Stability:** The message schema contract ([docs/schema.json](file:///c:/Udyam-Twin/docs/schema.json) and [docs/SCHEMA.md](file:///c:/Udyam-Twin/docs/SCHEMA.md)) is **frozen at v1.0**, well-documented, and strictly validated.
3. **Working Core Prototype:** A monolithic simulation engine and stream server is fully operational in [tools/fake_factory.py](file:///c:/Udyam-Twin/tools/fake_factory.py) and [tools/fake_stream.py](file:///c:/Udyam-Twin/tools/fake_stream.py). It successfully simulates 4 machines, calculates reduced-order thermal dynamics, computes residuals, triggers calibration events, handles WebSocket commands, and serves a developer test viewer ([tools/stream_viewer.html](file:///c:/Udyam-Twin/tools/stream_viewer.html)) on port `8765`.
4. **Target Subsystem Folders are Stubs:** The designated modular production folders — [`api/`](file:///c:/Udyam-Twin/api), [`sim/`](file:///c:/Udyam-Twin/sim), [`twin/`](file:///c:/Udyam-Twin/twin), [`ml/`](file:///c:/Udyam-Twin/ml), [`web/`](file:///c:/Udyam-Twin/web), [`assets/`](file:///c:/Udyam-Twin/assets), and [`edge/`](file:///c:/Udyam-Twin/edge) — contain **only README markdown placeholders**. No production application code has been placed in those directories yet.
5. **Test Status:** The test suite ([tests/test_fake_stream.py](file:///c:/Udyam-Twin/tests/test_fake_stream.py)) contains **14 tests**, all of which **pass (100%)** against the frozen schema.
6. **No Breaking Rewrite Needed:** Because the fake factory already conforms to the message schema and implements the core state transitions, the repository has a solid baseline. Future work must extract and modularize these verified behaviors into the target directories without modifying the message contract.

---

## 2. Feature Implementation Status Matrix

The audit evaluated each planned architectural feature against the codebase:

| Feature / Subsystem | Planned Location | Actual Current Location | Status | Verification & Evidence |
|---|---|---|---|---|
| **Message Schema (v1.0)** | `docs/schema.json` | [docs/schema.json](file:///c:/Udyam-Twin/docs/schema.json) | **Implemented** | 218 lines JSON Schema (Draft 2020-12); validated by `jsonschema` in all 14 unit tests. |
| **Fake Telemetry Stream** | `tools/fake_stream.py` | [tools/fake_stream.py](file:///c:/Udyam-Twin/tools/fake_stream.py) | **Implemented** | FastAPI WebSocket server ticking at 500ms; verified live on `ws://localhost:8765/ws/telemetry`. |
| **Monolithic Plant/Twin Sim** | `sim/`, `twin/` | [tools/fake_factory.py](file:///c:/Udyam-Twin/tools/fake_factory.py) | **Implemented (Harness)** | 564 lines of pure Python logic simulating thermal dynamics, vibration, wear, line buffers, and parameter calibration. |
| **Fault Injection** | `sim/faults.py` | [tools/fake_factory.py](file:///c:/Udyam-Twin/tools/fake_factory.py#L144-L179) | **Implemented (Harness)** | Supports all 8 fault types via WebSocket command `{"cmd": "inject_fault", ...}` and auto-demo script. |
| **Machine Registry & Onboarding** | `api/`, `sim/` | [tools/fake_factory.py](file:///c:/Udyam-Twin/tools/fake_factory.py#L163-L173) | **Implemented (Harness)** | Can start with 3 machines and dynamically add compressor via `{"cmd": "add_machine", ...}`. |
| **Dev Stream Viewer (2D UI)** | `tools/` | [tools/stream_viewer.html](file:///c:/Udyam-Twin/tools/stream_viewer.html) | **Implemented** | Functional developer HTML/JS dashboard displaying telemetry cards, line status, and live event log on `http://localhost:8765/`. |
| **Modular Plant Simulator** | `sim/plant.py`, `sim/plc.py`, `sim/line.py` | [`sim/README.md`](file:///c:/Udyam-Twin/sim/README.md) | **Only Planned** | Folder contains only README stub. Core physics logic exists only inside `tools/fake_factory.py`. |
| **Modular Twin Core** | `twin/model.py`, `twin/residuals.py` | [`twin/README.md`](file:///c:/Udyam-Twin/twin/README.md) | **Only Planned** | Folder contains only README stub. Heuristic residual & parameter versioning exists only inside `tools/fake_factory.py`. |
| **Formal RLS Calibration** | `twin/calibrate.py` | [`twin/README.md`](file:///c:/Udyam-Twin/twin/README.md) | **Partial / Stand-in** | `fake_factory.py` uses steady-state thermal model inversion with rate limits; full Recursive Least Squares (RLS) across $h_{cool}$, $k_{heat}$, $k_{wear}$ is planned. |
| **Forecast Engine** | `twin/forecast.py` | [tools/fake_factory.py](file:///c:/Udyam-Twin/tools/fake_factory.py#L391-L402) | **Partial / Stand-in** | Analytical logarithmic time-to-overtemp estimate implemented in `fake_factory.py`; modular module planned. |
| **Production FastAPI API (Port 8000)** | `api/main.py`, `api/routes/` | [`api/README.md`](file:///c:/Udyam-Twin/api/README.md) | **Only Planned** | No REST routes for faults, work orders, tool-wear entry, or static serving of `web/` exist yet. |
| **SQLite Persistence** | `api/db.py` | [`api/README.md`](file:///c:/Udyam-Twin/api/README.md) | **Only Planned** | No database file, schema definitions, or ORM tables for events, work orders, or $\theta$-history exist. |
| **ML Failure Classifier (AI4I)** | `ml/train.py`, `ml/model.joblib` | [`ml/README.md`](file:///c:/Udyam-Twin/ml/README.md) | **Mocked / Stand-in** | `fake_factory.py` computes risk using an inline logistic approximation $P = \frac{1}{1 + e^{-z}}$. Real trained RandomForest is missing. |
| **Rule Baseline** | `ml/rules.py` | [`ml/README.md`](file:///c:/Udyam-Twin/ml/README.md) | **Partial / Inline** | Inline rules for overtemp, vibration zones C/D, and pressure in `fake_factory.py`; formal `rules.py` for AI4I modes (HDF/PWF/OSF/TWF) missing. |
| **Metrics Verification** | `ml/metrics.json` | [`ml/README.md`](file:///c:/Udyam-Twin/ml/README.md) | **Only Planned** | File not present. |
| **3D Three.js Scene** | `web/` | [`web/README.md`](file:///c:/Udyam-Twin/web/README.md) | **Only Planned** | Folder contains only README stub. |
| **3D Assets (.glb)** | `assets/machine.glb` | [`assets/README.md`](file:///c:/Udyam-Twin/assets/README.md) | **Only Planned** | Folder contains only README stub; no TseNC or primitive glb models present. |
| **Production Dashboard (R4)** | `web/index.html` | [`web/README.md`](file:///c:/Udyam-Twin/web/README.md) | **Only Planned** | Only the dev viewer in `tools/` exists. |
| **Edge Node (ESP32)** | `edge/` | [`edge/README.md`](file:///c:/Udyam-Twin/edge/README.md) | **Only Planned (Stretch)** | Intentionally deferred to Stage D/stretch goal after feature freeze. |

---

## 3. Working Entry Points & Exact Execution Commands

### 3.1 Prerequisites & Environment Setup
The project uses Python 3.11–3.13. Dependencies are installed in `.venv`.

**Windows (PowerShell):**
```powershell
# 1. Activate existing virtual environment
.\.venv\Scripts\Activate.ps1

# 2. Verify dependencies
pip install -r requirements-dev.txt
```

**Linux / macOS (Bash):**
```bash
source .venv/bin/activate
pip install -r requirements-dev.txt
```

### 3.2 Running Existing Tests
The test runner is configured via [pytest.ini](file:///c:/Udyam-Twin/pytest.ini) with `pythonpath = .` and `testpaths = tests`.

```powershell
python -m pytest -v
```

### 3.3 Running the Working Fake Stream Server
The primary active entry point is [tools/fake_stream.py](file:///c:/Udyam-Twin/tools/fake_stream.py).

```powershell
# Default: 4 machines, scripted 150-second auto-demo loop, host 0.0.0.0, port 8765
python -m tools.fake_stream

# Test Onboarding Wizard: starts with 3 machines (without COMP-01)
python -m tools.fake_stream --machines 3

# Manual Mode: disables auto-demo script; faults triggered manually via UI or WebSocket
python -m tools.fake_stream --no-auto

# Offline Data Export: record N ticks directly to JSONL without opening a port
python -m tools.fake_stream --record 600 --out samples/demo_stream.jsonl
```

### 3.4 Accessing the Interfaces
- **Dev Stream Viewer:** [http://localhost:8765/](http://localhost:8765/)
- **Frozen JSON Schema:** [http://localhost:8765/schema.json](http://localhost:8765/schema.json)
- **Live WebSocket:** `ws://localhost:8765/ws/telemetry`
- **Offline Sample Stream:** [samples/demo_stream.jsonl](file:///c:/Udyam-Twin/samples/demo_stream.jsonl) (2,723 lines, pre-recorded full demo cycle)

---

## 4. Endpoints & WebSocket Message Protocol

### 4.1 HTTP REST Endpoints

#### Currently Active (in `tools/fake_stream.py` on port 8765):
| Method | Path | Response | Description |
|---|---|---|---|
| `GET` | `/` | `text/html` | Serves [tools/stream_viewer.html](file:///c:/Udyam-Twin/tools/stream_viewer.html). |
| `GET` | `/schema.json` | `application/json` | Serves [docs/schema.json](file:///c:/Udyam-Twin/docs/schema.json). |

#### Planned / Missing (in `api/` on port 8000):
| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Serves `web/index.html` (operator/engineer dashboard). |
| `GET` | `/operator` | Mobile-optimized operator view. |
| `POST` | `/api/faults/inject` | Trigger fault injection on a machine. |
| `POST` | `/api/faults/clear` | Clear active faults. |
| `POST` | `/api/derate` | Apply or propose machine derate. |
| `POST` | `/api/machines` | Onboard new machine (wizard submit). |
| `GET` | `/api/work-orders` | Fetch work orders from SQLite. |
| `POST` | `/api/work-orders` | Create or update work order status. |
| `POST` | `/api/tool-wear` | Human-in-the-loop tool wear entry to update $k_{wear}$. |
| `GET` | `/api/metrics` | Return AI4I model metrics vs rule baseline. |

---

### 4.2 WebSocket Message Protocol (`/ws/telemetry`)

#### Outbound Frames (Server $\rightarrow$ Client)
All messages are JSON objects validated against [docs/schema.json](file:///c:/Udyam-Twin/docs/schema.json):

1. **`hello`** (Sent immediately upon connection):
   ```json
   {
     "type": "hello",
     "schema_version": "1.0",
     "generator": "fake_stream",
     "tick_ms": 500
   }
   ```
2. **`registry`** (Sent after `hello`, on reset, and upon adding a machine):
   ```json
   {
     "type": "registry",
     "schema_version": "1.0",
     "machines": [
       {
         "machine_id": "VMC-01",
         "template": "cnc_mill",
         "name": "CNC Mill (VMC)",
         "hero": true,
         "layout": { "x": 8.0, "y": 0.0, "order": 2 },
         "nameplate": { "rated_kw": 11.0, "max_rpm": 3000, "make": "Representative VMC (geometry: TseNC)", "year": 2012 }
       }
     ]
   }
   ```
3. **`observed`** (Emitted every 500ms per machine):
   ```json
   {
     "type": "observed",
     "schema_version": "1.0",
     "ts": "2026-10-22T13:40:00.500Z",
     "machine_id": "VMC-01",
     "template": "cnc_mill",
     "source_mode": "SIM",
     "plc_state": "RUN",
     "dq_flag": "OK",
     "power_kw": 6.582,
     "current_a": 11.71,
     "vibration_rms_mm_s": 2.29,
     "derate_pct": 0.0,
     "active_fault": null,
     "parts_done": 12,
     "air_temp_k": 299.93,
     "process_temp_k": 311.49,
     "rpm": 1539.0,
     "torque_nm": 40.84,
     "tool_wear_min": 118.0
   }
   ```
4. **`twin`** (Emitted every 500ms per machine alongside `observed`):
   ```json
   {
     "type": "twin",
     "schema_version": "1.0",
     "ts": "2026-10-22T13:40:00.500Z",
     "machine_id": "VMC-01",
     "predicted": { "process_temp_k": 311.55, "tool_wear_min": 118.0 },
     "residual": {
       "signal": "process_temp_k",
       "value": -0.061,
       "ewma": -0.006,
       "cusum": 0.0,
       "band": 0.6,
       "state": "IN_BAND"
     },
     "params": {
       "version": "v1.0",
       "values": { "h_cool": 1.0, "k_heat": 1.0, "k_wear": 1.0 },
       "frozen": false,
       "freeze_reason": null
     },
     "forecast": { "minutes_to_warning": null, "warning": null },
     "risk": { "rules": "LOW", "model": 0.01, "top_signals": [] }
   }
   ```
5. **`line`** (Emitted every 500ms once for the full line):
   ```json
   {
     "type": "line",
     "schema_version": "1.0",
     "ts": "2026-10-22T13:40:00.500Z",
     "throughput_parts_per_hr": 3.98,
     "line_loss_inr_per_hr": 9.0,
     "bottleneck": "VMC-01",
     "air_supply_ok": true,
     "stations": [
       { "machine_id": "SAW-01", "state": "RUNNING", "buffer_in": 0, "buffer_cap": 10 },
       { "machine_id": "LATHE-01", "state": "RUNNING", "buffer_in": 4, "buffer_cap": 10 },
       { "machine_id": "VMC-01", "state": "RUNNING", "buffer_in": 4, "buffer_cap": 10 }
     ]
   }
   ```
6. **`event`** (Emitted asynchronously when state changes or alerts fire):
   ```json
   {
     "type": "event",
     "schema_version": "1.0",
     "ts": "2026-10-22T13:40:05.000Z",
     "event_id": "E00001",
     "machine_id": "VMC-01",
     "kind": "FAULT_INJECTED",
     "severity": "INFO",
     "title": "Injected 'coolant_degradation' on CNC Mill (VMC) (plant only; the twin is not told)",
     "measured": null,
     "inferred": null,
     "suggested": null,
     "data": { "fault": "coolant_degradation" }
   }
   ```

#### Inbound Commands (Client $\rightarrow$ Server)
The WebSocket accepts JSON text frames from the UI:
```json
{"cmd": "inject_fault", "machine_id": "VMC-01", "fault": "coolant_degradation"}
{"cmd": "clear_faults", "machine_id": "VMC-01"}
{"cmd": "set_derate", "machine_id": "VMC-01", "pct": 20}
{"cmd": "add_machine", "template": "air_compressor", "name": "Air Compressor", "nameplate": {"rated_kw": 7.5}}
{"cmd": "auto_demo", "on": false}
{"cmd": "reset"}
```

---

## 5. Current Test Results & Validation

The test suite was executed in the workspace `.venv`:

```
Command: python -m pytest -v
Platform: Windows (Python 3.13.12, pytest-8.3.3)
Root Directory: C:\Udyam-Twin
Configuration: pytest.ini
Plugins: anyio-4.12.1
Status: 14 PASSED in 12.63 seconds (100% pass rate)
```

### Detailed Test Breakdown
| Test Identifier | Duration | Verified Functionality |
|---|---|---|
| `test_full_demo_loop_validates` | ~3.8s | Simulates 600 ticks (300 seconds); verifies every emitted message matches `docs/schema.json` and verifies that all key event kinds fire (`FAULT_INJECTED`, `DRIFT`, `CALIBRATION`, `ALERT`, `COMMON_CAUSE`, `ANOMALY`, `RESET`). |
| `test_every_fault_validates[coolant_degradation-VMC-01]` | ~0.7s | Verifies coolant degradation dynamics and message schema compliance. |
| `test_every_fault_validates[bearing_defect-VMC-01]` | ~0.7s | Verifies bearing vibration defect and schema compliance. |
| `test_every_fault_validates[overload-LATHE-01]` | ~0.7s | Verifies lathe torque overload fault and schema compliance. |
| `test_every_fault_validates[tool_wear_accel-VMC-01]` | ~0.7s | Verifies accelerated tool wear fault and schema compliance. |
| `test_every_fault_validates[sensor_stuck-VMC-01]` | ~0.7s | Verifies `dq_flag: "STUCK"` data quality flag and schema compliance. |
| `test_every_fault_validates[sensor_dropout-VMC-01]` | ~0.7s | Verifies `dq_flag: "MISSING"` with `process_temp_k: null` and schema compliance. |
| `test_every_fault_validates[pressure_drop-COMP-01]` | ~0.7s | Verifies compressor pressure drop and schema compliance. |
| `test_every_fault_validates[blade_wear-SAW-01]` | ~0.7s | Verifies saw blade wear progression and schema compliance. |
| `test_onboarding_adds_machine` | ~0.2s | Starts factory with 3 machines, issues `add_machine` command, confirms `MACHINE_ADDED` event and new registry. |
| `test_deterministic_for_seed` | ~0.3s | Verifies that two factories initialized with identical seed generate identical message streams. |
| `test_calibration_converges_without_overshoot` | ~0.8s | Verifies that after coolant degradation, $h_{est}$ converges to $h_{true}$ within $|h_{est} - h_{true}| < 0.06$ with no negative overshoot ($h_{est} \ge h_{true} - 0.02$). |
| `test_calibration_freezes_on_anomaly_and_bad_sensor` | ~1.4s | Verifies that when an anomaly (`bearing_defect`) or bad sensor (`sensor_stuck`) occurs, `params.frozen` becomes `true` and zero `CALIBRATION` events fire. |
| `test_websocket_server_handshake_and_command` | ~0.5s | Connects FastAPI `TestClient` to `/ws/telemetry`, checks `hello` and `registry` handshake, sends `add_machine` command, and validates received streaming frames. |

---

## 6. End-to-End Telemetry Message Trace

To verify the message lifecycle, here is the complete trace of a telemetry frame during a simulated coolant degradation event on the hero machine `VMC-01`:

```mermaid
sequenceDiagram
    autonumber
    participant UI as Browser (stream_viewer.html)
    participant WS as FastAPI WebSocket (/ws/telemetry)
    participant FF as FakeFactory / Ticker Loop
    participant Plant as Plant Simulator (VMC-01)
    participant Twin as Twin Model & Calibrator

    UI->>WS: Send {"cmd": "inject_fault", "machine_id": "VMC-01", "fault": "coolant_degradation"}
    WS->>FF: command(cmd)
    FF->>Plant: _inject(m, "coolant_degradation") -> m.faults.add("coolant_degradation")
    FF-->>WS: Broadcast event: FAULT_INJECTED
    WS-->>UI: WebSocket JSON frame: event (FAULT_INJECTED)
    UI->>UI: logEvent(m) prepends to Event Log

    Note over FF,Twin: Next 500ms Tick (step)
    FF->>Plant: _step_cnc(m)
    Note over Plant: h_true decays: max(0.55, h_true - 0.005*0.5)<br/>Process temp rises: dT = (T_target - T) * dt / 20.0
    Plant-->>FF: returns observed dict (type: "observed", process_temp_k: 312.4, ...)
    FF-->>WS: Broadcast observed message
    WS-->>UI: WebSocket JSON frame: observed (VMC-01)
    UI->>UI: state.obs["VMC-01"] = m; render()

    FF->>Twin: _twin_cnc(m, obs)
    Note over Twin: Predicts T_pred with nominal h_est (1.0)<br/>Residual e = 312.4 - 310.2 = +2.2 K<br/>EWMA = 0.9*EWMA + 0.1*e; CUSUM increases<br/>CUSUM > 2.5 -> State becomes DRIFT
    Twin-->>FF: Calibration triggers! h_est updated 1.00 -> 0.95 (v1.0 -> v1.1)
    FF-->>WS: Broadcast event: CALIBRATION + twin message
    WS-->>UI: WebSocket JSON frames: event (CALIBRATION) & twin
    UI->>UI: state.twin["VMC-01"] = m; render() updates Card (Params: v1.1, Residual: DRIFT)
```

### Trace Step Details:
1. **Physical Plant Step ([tools/fake_factory.py:L280-L284](file:///c:/Udyam-Twin/tools/fake_factory.py#L280-L284)):**  
   The plant degrades the hidden true heat transfer multiplier $h_{true}$ by $0.005$ each second. Target temperature $T_{target} = T_{air} + 8.0 + 0.7 \cdot P / h_{true}$ increases. The physical spindle temperature $T_{proc}$ integrates toward $T_{target}$.
2. **Observation Packaging ([tools/fake_factory.py:L310-L319](file:///c:/Udyam-Twin/tools/fake_factory.py#L310-L319)):**  
   Measurement noise ($\sigma = 0.15$) is added to synthesize sensor reading `process_temp_k`. Combined with electrical signals, this forms the `observed` frame.
3. **Twin Prediction & Residual ([tools/fake_factory.py:L323-L336](file:///c:/Udyam-Twin/tools/fake_factory.py#L323-L336)):**  
   The twin computes expected steady-state temperature using its current estimate $h_{est} = 1.0$. The residual $e = y_{obs} - \hat{y}_{pred}$ deviates positive. EWMA and CUSUM accumulators track sustained drift.
4. **Calibration Event ([tools/fake_factory.py:L374-L390](file:///c:/Udyam-Twin/tools/fake_factory.py#L374-L390)):**  
   Because `dq_flag == "OK"` and `frozen_reason is None`, the calibrator inverts the thermal equation at projected steady state, stepping $h_{est}$ downwards toward $h_{true}$. Once $\Delta h \ge 0.05$, parameter version increments from `v1.0` to `v1.1` and a `CALIBRATION` event is emitted.
5. **WebSocket Broadcast ([tools/fake_stream.py:L50-L58](file:///c:/Udyam-Twin/tools/fake_stream.py#L50-L58)):**  
   FastAPI's async ticker calls `broadcast()`, serializing the `observed`, `twin`, `line`, and `event` dictionaries and pushing them over the active WebSocket channel.
6. **Frontend Reception & DOM Update ([tools/stream_viewer.html:L77-L111](file:///c:/Udyam-Twin/tools/stream_viewer.html#L77-L111)):**  
   In the browser, `ws.onmessage` receives the frame, parses JSON, routes it by `type`, updates `state.obs` and `state.twin`, and re-renders the machine card with updated temperature, parameter version, residual badge, and forecast alert.

---

## 7. Gaps, Missing Dependencies & Disconnected Components

### 7.1 Architecture & Code Structure Gaps
1. **Monolithic Prototype vs. Target Architecture:**  
   The entire working implementation currently lives inside `tools/fake_factory.py` (564 lines). The actual architecture specified in the master plan requires distinct layers:
   - `sim/` for plant simulation, virtual PLC, and line models.
   - `twin/` for twin models, residual tracking, and RLS calibration.
   - `api/` for the production FastAPI service on port 8000.
2. **Missing Production Web Server (Port 8000):**  
   The master plan specifies that `api/` will serve the application on port 8000 with REST routes. Currently, only port 8765 is supported via `tools/fake_stream.py`.
3. **Missing Machine Learning Pipeline (`ml/`):**  
   - [ml/rules.py](file:///c:/Udyam-Twin/ml/README.md) is unwritten.
   - [ml/train.py](file:///c:/Udyam-Twin/ml/README.md) is unwritten.
   - The AI4I 2020 dataset has not been downloaded to `ml/data/`.
   - The trained model `ml/model.joblib` and `ml/metrics.json` do not exist.
   - Risk probability is currently simulated via a hard-coded sigmoid formula.
4. **Missing 3D Assets & Three.js Frontend (`assets/`, `web/`):**  
   - There are no `.glb` files in `assets/` (no `machine.glb`, no primitive models).
   - `web/` contains no HTML, CSS, or Three.js scene graphs.
   - The only visual output is the 2D dev viewer `tools/stream_viewer.html`.
5. **Missing SQLite Persistence:**  
   - Work orders, historical events, and parameter versions are kept only in in-memory Python lists and lost on server restart.

### 7.2 Dependency Analysis
Inspecting [requirements.txt](file:///c:/Udyam-Twin/requirements.txt) vs. the environment:
- **Declared in `requirements.txt`:**
  - `fastapi>=0.110`
  - `uvicorn[standard]>=0.29`
- **Declared in `requirements-dev.txt`:**
  - `pytest>=8`
  - `jsonschema>=4.20`
  - `httpx>=0.27`
- **Undeclared Packages Required by Plan (`ml/`):**  
  `scikit-learn`, `numpy`, `pandas`, and `joblib` are installed in the developer's local environment, but are **not declared** in `requirements.txt`. If deployed on another system or an offline presentation laptop without these in `requirements.txt`, ML training will fail.
- **Deprecation Warning:**  
  `Using httpx with starlette.testclient is deprecated; install httpx2 instead.` — Starlette 0.38+ deprecation notice. Tests still pass without issue.

---

## 8. Prioritized Integration Plan

To transition from the Day 1 prototype to the complete production demonstrator without breaking the frozen schema or disrupting working tests, development should follow this sequence:

```
┌────────────────────────────────────────────────────────────────────────┐
│ Phase 1: Core Modularization (sim/ + twin/)                            │
│ Extract modular plant.py, plc.py, line.py, model.py, calibrate.py      │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
┌───────────────────────────────────▼────────────────────────────────────┐
│ Phase 2: Production API & Persistence (api/)                           │
│ Port 8000 FastAPI server, REST routes, SQLite work orders & params     │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
┌───────────────────────────────────▼────────────────────────────────────┐
│ Phase 3: ML Rule Engine & Trained Model (ml/)                          │
│ AI4I rules.py, train.py, model.joblib, and metrics.json                │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
┌───────────────────────────────────▼────────────────────────────────────┐
│ Phase 4: Frontend & 3D Integration (web/ + assets/)                    │
│ Operator/Engineer dashboard, Three.js hero mill + floor view           │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
┌───────────────────────────────────▼────────────────────────────────────┐
│ Phase 5: Verification, Benchmarking & Offline Packaging                │
│ End-to-end 5-min demo rehearsal, FPS measurement, offline packaging    │
└────────────────────────────────────────────────────────────────────────┘
```

### Phase 1: Core Modularization (`sim/` and `twin/`) — *Priority: Critical*
- Extract `sim/plant.py`, `sim/plc.py`, `sim/line.py`, and `sim/faults.py` from `fake_factory.py`.
- Extract `twin/model.py`, `twin/residuals.py`, `twin/calibrate.py` (RLS), and `twin/forecast.py`.
- Ensure new modules pass unit tests mirroring `test_fake_stream.py`.
- **Constraint:** Keep `tools/fake_factory.py` intact until new modules are validated, ensuring zero regression.

### Phase 2: Production API & Persistence (`api/`) — *Priority: High*
- Build `api/app.py` running on port 8000.
- Re-use the proven WebSocket handler from `fake_stream.py` connected to the modular core.
- Add SQLite tables for `events`, `work_orders`, and `param_history`.
- Implement REST routes: `POST /api/faults/inject`, `POST /api/machines`, `POST /api/work-orders`, `POST /api/tool-wear`.
- Serve static files from `web/`.

### Phase 3: ML Rule Engine & AI4I Model (`ml/`) — *Priority: High*
- Add `scikit-learn`, `numpy`, `pandas`, `joblib` to `requirements.txt`.
- Implement `ml/rules.py` (HDF, PWF, OSF, TWF rule logic).
- Implement `ml/train.py` with reproducible seed, class weighting, and stratified split.
- Generate `ml/metrics.json` comparing rules baseline vs. Random Forest (precision, recall, F1, PR-AUC, confusion matrix).
- Hook trained model inference into the twin tick for CNC machines.

### Phase 4: Frontend & 3D Visualizer (`web/` and `assets/`) — *Priority: High*
- Create fallback primitive 3D mill or load simplified TseNC `.glb` in `assets/`.
- Build Three.js scene in `web/` with bindings: RPM $\rightarrow$ spindle rotation, temperature $\rightarrow$ color/shader, vibration $\rightarrow$ jitter.
- Build production dashboard:
  - Floor view (4 machines, buffer levels, line status).
  - Engineer view (Predicted vs. Observed chart, residual band, $\theta$-history table).
  - Operator phone view at `/operator`.
  - Onboarding wizard ("Add your machine" modal).
  - Alert cards with Fact / Inference / Action structure.

### Phase 5: Hardening & Offline Packaging — *Priority: Medium*
- Ensure all static dependencies (Three.js, fonts, CSS) are bundled locally without CDN links.
- Run complete 5-minute demo script offline 3 times consecutively.
- Record backup demonstration video.

---

## 9. Smallest First End-to-End Milestone

To make immediate, measurable progress without risking breakage, the **smallest first milestone** is:

### Milestone 1: "Modular Core Extraction & Parity Test"
**Goal:** Extract the plant and twin physics out of the monolithic `fake_factory.py` into `sim/` and `twin/`, and verify that the modular core produces identical, valid schema messages.

#### Specific Tasks:
1. Create `sim/plant.py` defining `Machine` and template dynamics (`cnc_mill`, `cnc_lathe`, `bar_saw`, `air_compressor`).
2. Create `twin/model.py` and `twin/residuals.py` calculating predictions and residuals.
3. Create `tests/test_modular_core.py` verifying that:
   - All emitted messages validate against `docs/schema.json`.
   - Calibration converges on coolant fault.
   - Calibration freezes on anomaly and stuck sensor.
4. Keep `tools/fake_stream.py` and `tools/fake_factory.py` completely unchanged so that existing frontend and testing workflows remain 100% operational.

**Estimated Effort:** 2–3 hours.  
**Risk Level:** Zero (additive only, no destructive edits).

---

## 10. Conclusion & Request for Direction

The UDYAM-TWIN project has a solid, working test harness and an inviolable message contract. All 14 tests pass and the fake stream server is fully operational. The architecture is cleanly defined in the master plan.

The next step is to begin Phase 1 (Milestone 1). Awaiting architectural approval before implementing.
