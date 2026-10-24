@echo off
echo ========================================================
echo   UDYAM-TWIN: Industrial Digital Twin Platform
echo   INAE Youth Conclave 2026 - HT14 MSME Digital Twin
echo ========================================================
echo.

IF EXIST .venv\Scripts\activate.bat (
    call .venv\Scripts\activate.bat
) ELSE (
    echo [INFO] Virtual environment .venv not found, using system Python...
)

echo [INFO] Launching browser dashboard at http://localhost:8000 ...
start "" http://localhost:8000

echo [INFO] Starting FastAPI server on port 8000...
python -m uvicorn api.app:app --host 0.0.0.0 --port 8000 --log-level info
