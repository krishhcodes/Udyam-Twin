# UDYAM-TWIN

A self-calibrating, browser-based digital twin for MSME machine shops: a 4-machine CNC mini line with one detailed hero machine. Built by Tech Titans (NIT Raipur) for INAE Youth Conclave 2026, HT14.

- **Plan:** [`docs/MASTER_PLAN.md`](docs/MASTER_PLAN.md) · **your role:** [`docs/briefs/`](docs/briefs/)
- **Message contract (frozen v1.0):** [`docs/SCHEMA.md`](docs/SCHEMA.md) + [`docs/schema.json`](docs/schema.json)

## Quick start

### 1. Production Digital Twin Platform (FastAPI + Dashboard + WebSocket)
```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
python -m uvicorn api.app:app --host 0.0.0.0 --port 8000   # or run start.bat
```
- Open Dashboard: [http://localhost:8000](http://localhost:8000)
- Mobile Operator Screen: [http://localhost:8000/operator](http://localhost:8000/operator)
- Interactive API Docs: [http://localhost:8000/docs](http://localhost:8000/docs)
- WebSocket: `ws://localhost:8000/ws/telemetry`

### 2. Standalone Fake Stream Server (Day 1 Dev Harness)
```bash
python -m tools.fake_stream                              # then open http://localhost:8765
```
- WebSocket: `ws://localhost:8765/ws/telemetry`. Every message follows `docs/schema.json`.
- Scripted **150-second demo loop**: coolant drift → twin recalibrates → over-temperature forecast → auto-derate → compressor common cause → bearing anomaly (calibration frozen) → reset.
- `--machines 3` starts without the compressor (to test the "Add your machine" wizard); `--no-auto` turns off the scripted faults.
- **No Python?** Use [`samples/demo_stream.jsonl`](samples/demo_stream.jsonl): one message per line, one full loop.

### 3. ML Model Training & Evaluation
```bash
python -m ml.train
```
Generates `ml/model.joblib` and `ml/metrics.json` comparing rule baseline vs. Random Forest.

### 4. Running the Tests
```bash
python -m pytest -v
```

## Layout

| Folder | Owner | What goes there |
|---|---|---|
| `sim/` | R1 | plant simulators (hidden "true" machines), virtual PLC, fault injectors, line model |
| `twin/` | R1 | twin model, residuals, calibration (RLS), forecast |
| `api/` | R3 | FastAPI app, WebSocket, REST, SQLite |
| `ml/` | R3 | AI4I rules + RandomForest, metrics |
| `web/` | R2 + R4 | Three.js scenes + dashboard |
| `assets/` | R2 | glb models + attribution (TseNC, CERN-OHL-W) |
| `edge/` | R5 | ESP32 firmware (stretch) |
| `tools/` | R1 | fake stream + dev viewer |
| `tests/` | all | contract and behaviour tests |

## Rules

Each person works on their own branch; R1 merges `main` every evening, and `main` must always run the demo. Schema changes need R1's approval and a version bump.
