"""SQLite database storage for events, work orders, parameter versions, and economics.

Thread-safe, lightweight, and works offline with zero external database dependencies.
"""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DB_PATH = Path(__file__).resolve().parent.parent / "udyam_twin.sqlite"


def get_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Path = DB_PATH) -> None:
    """Initialize database tables and default configuration."""
    conn = get_connection(db_path)
    with conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT UNIQUE NOT NULL,
                ts TEXT NOT NULL,
                machine_id TEXT,
                kind TEXT NOT NULL,
                severity TEXT NOT NULL,
                title TEXT NOT NULL,
                measured TEXT,
                inferred TEXT,
                suggested TEXT,
                data_json TEXT
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS work_orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                wo_id TEXT UNIQUE NOT NULL,
                created_at TEXT NOT NULL,
                machine_id TEXT NOT NULL,
                title TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Open',
                priority TEXT NOT NULL DEFAULT 'Medium',
                assigned_to TEXT,
                operator_notes TEXT,
                tool_wear_measured REAL
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS parameter_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                machine_id TEXT NOT NULL,
                param TEXT NOT NULL,
                from_val REAL NOT NULL,
                to_val REAL NOT NULL,
                version TEXT NOT NULL,
                residual_ewma REAL NOT NULL
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS economics_config (
                key TEXT PRIMARY KEY,
                value REAL NOT NULL,
                description TEXT NOT NULL
            );
        """)
        # Seed default MSME assumptions if not present
        defaults = [
            ("inr_per_part", 450.0, "Gross contribution per finished good part (INR)"),
            ("downtime_cost_per_hr", 2500.0, "Estimated cost per machine breakdown hour (INR)"),
            ("electricity_tariff_per_kwh", 8.5, "Commercial electricity tariff (INR / kWh)"),
            ("cea_co2_factor", 0.716, "CEA CO2 Baseline Database Grid Factor (kg CO2 / kWh, 2024-25)"),
            ("sensor_node_cost_inr", 2200.0, "Indicative BOM cost per clip-on sensor node (INR)"),
        ]
        for key, val, desc in defaults:
            conn.execute(
                "INSERT OR IGNORE INTO economics_config (key, value, description) VALUES (?, ?, ?);",
                (key, val, desc),
            )


def log_event(event: dict[str, Any], db_path: Path = DB_PATH) -> None:
    """Log an emitted telemetry event into the database."""
    conn = get_connection(db_path)
    data_json = json.dumps(event.get("data", {})) if event.get("data") else None
    with conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO events
            (event_id, ts, machine_id, kind, severity, title, measured, inferred, suggested, data_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                event["event_id"],
                event["ts"],
                event.get("machine_id"),
                event["kind"],
                event["severity"],
                event["title"],
                event.get("measured"),
                event.get("inferred"),
                event.get("suggested"),
                data_json,
            ),
        )


def get_events(limit: int = 50, db_path: Path = DB_PATH) -> list[dict[str, Any]]:
    """Retrieve recent events sorted newest first."""
    conn = get_connection(db_path)
    cur = conn.execute("SELECT * FROM events ORDER BY id DESC LIMIT ?;", (limit,))
    rows = cur.fetchall()
    out = []
    for r in rows:
        d = dict(r)
        if d.get("data_json"):
            d["data"] = json.loads(d["data_json"])
        else:
            d["data"] = {}
        out.append(d)
    return out


def create_work_order(
    machine_id: str,
    title: str,
    priority: str = "Medium",
    notes: str = "",
    db_path: Path = DB_PATH,
) -> dict[str, Any]:
    """Create a new work order."""
    conn = get_connection(db_path)
    ts = datetime.now(timezone.utc).isoformat()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM work_orders;")
    count = cur.fetchone()[0] + 1
    wo_id = f"WO-{count:04d}"
    with conn:
        conn.execute(
            """
            INSERT INTO work_orders
            (wo_id, created_at, machine_id, title, status, priority, operator_notes)
            VALUES (?, ?, ?, ?, 'Open', ?, ?);
            """,
            (wo_id, ts, machine_id, title, priority, notes),
        )
    return {
        "wo_id": wo_id,
        "created_at": ts,
        "machine_id": machine_id,
        "title": title,
        "status": "Open",
        "priority": priority,
        "operator_notes": notes,
    }


def update_work_order_status(
    wo_id: str,
    status: str,
    notes: str | None = None,
    tool_wear_measured: float | None = None,
    db_path: Path = DB_PATH,
) -> dict[str, Any] | None:
    """Update work order status or operator measurements."""
    conn = get_connection(db_path)
    with conn:
        if tool_wear_measured is not None and notes is not None:
            conn.execute(
                "UPDATE work_orders SET status = ?, operator_notes = ?, tool_wear_measured = ? WHERE wo_id = ?;",
                (status, notes, tool_wear_measured, wo_id),
            )
        elif notes is not None:
            conn.execute(
                "UPDATE work_orders SET status = ?, operator_notes = ? WHERE wo_id = ?;",
                (status, notes, wo_id),
            )
        else:
            conn.execute("UPDATE work_orders SET status = ? WHERE wo_id = ?;", (status, wo_id))
    cur = conn.execute("SELECT * FROM work_orders WHERE wo_id = ?;", (wo_id,))
    row = cur.fetchone()
    return dict(row) if row else None


def list_work_orders(db_path: Path = DB_PATH) -> list[dict[str, Any]]:
    conn = get_connection(db_path)
    cur = conn.execute("SELECT * FROM work_orders ORDER BY id DESC;")
    return [dict(r) for r in cur.fetchall()]


def log_parameter_change(
    machine_id: str,
    param: str,
    from_val: float,
    to_val: float,
    version: str,
    residual_ewma: float,
    ts: str | None = None,
    db_path: Path = DB_PATH,
) -> None:
    conn = get_connection(db_path)
    if not ts:
        ts = datetime.now(timezone.utc).isoformat()
    with conn:
        conn.execute(
            """
            INSERT INTO parameter_history
            (ts, machine_id, param, from_val, to_val, version, residual_ewma)
            VALUES (?, ?, ?, ?, ?, ?, ?);
            """,
            (ts, machine_id, param, from_val, to_val, version, residual_ewma),
        )


def get_parameter_history(machine_id: str | None = None, db_path: Path = DB_PATH) -> list[dict[str, Any]]:
    conn = get_connection(db_path)
    if machine_id:
        cur = conn.execute("SELECT * FROM parameter_history WHERE machine_id = ? ORDER BY id DESC;", (machine_id,))
    else:
        cur = conn.execute("SELECT * FROM parameter_history ORDER BY id DESC;")
    return [dict(r) for r in cur.fetchall()]


def get_economics(db_path: Path = DB_PATH) -> dict[str, float]:
    conn = get_connection(db_path)
    cur = conn.execute("SELECT key, value FROM economics_config;")
    return {r["key"]: r["value"] for r in cur.fetchall()}


def update_economics(updates: dict[str, float], db_path: Path = DB_PATH) -> dict[str, float]:
    conn = get_connection(db_path)
    with conn:
        for k, v in updates.items():
            conn.execute("UPDATE economics_config SET value = ? WHERE key = ?;", (float(v), k))
    return get_economics(db_path)
