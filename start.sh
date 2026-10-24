#!/usr/bin/env bash
echo "========================================================"
echo "  UDYAM-TWIN: Industrial Digital Twin Platform"
echo "  INAE Youth Conclave 2026 - HT14 MSME Digital Twin"
echo "========================================================"
echo ""

if [ -d ".venv" ]; then
    source .venv/bin/activate
elif [ -d "venv" ]; then
    source venv/bin/activate
fi

echo "[INFO] Starting FastAPI server on port 8000..."
python -m uvicorn api.app:app --host 0.0.0.0 --port 8000 --log-level info
