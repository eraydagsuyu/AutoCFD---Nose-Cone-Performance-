"""SQLite durum veritabanı (data/results.db) — orkestratör ve rcfd ortak erişimi.

Tablolar:
  runs      (campaign, geom_id, vel_idx) başına bir satır; durum makinesi + kesin Cd
  attempts  her çözüm denemesi (profil, override, sonuç, kim karar verdi, gerekçe)
  events    olay günlüğü (logs/events.jsonl'a da yazılır)
  control   pause / stop_after_current anahtarları

runs.status: pending | running | done | done_flagged | retry_pending | needs_review | skipped | mesh_error
"""
from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

from .config import DATA_DIR, LOG_DIR

DB_PATH = DATA_DIR / "results.db"
EVENTS_JSONL = LOG_DIR / "events.jsonl"

RUNNABLE = ("pending", "retry_pending")
FINAL_OK = ("done", "done_flagged")

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id         INTEGER PRIMARY KEY,
    campaign       TEXT NOT NULL,
    geom_id        TEXT NOT NULL,
    vel_idx        INTEGER NOT NULL,
    velocity_ms    REAL, mach REAL, altitude_m REAL, regime TEXT,
    status         TEXT NOT NULL DEFAULT 'pending',
    cd             REAL,
    cd_flagged     INTEGER DEFAULT 0,
    n_attempts     INTEGER DEFAULT 0,
    budget_base    INTEGER DEFAULT 0,
    next_overrides TEXT,
    next_init      TEXT,
    next_decided_by TEXT,
    next_reason    TEXT,
    priority       INTEGER DEFAULT 0,
    mesh_version   TEXT,
    updated_at     TEXT,
    UNIQUE (campaign, geom_id, vel_idx)
);
CREATE TABLE IF NOT EXISTS attempts (
    attempt_id     INTEGER PRIMARY KEY,
    run_id         INTEGER NOT NULL REFERENCES runs(run_id),
    attempt_no     INTEGER NOT NULL,
    started_at     TEXT, ended_at TEXT,
    profile_hash   TEXT, profile_json TEXT, overrides_json TEXT, init_method TEXT,
    outcome        TEXT, cd REAL, iterations INTEGER, elapsed_s REAL,
    cd_rel_std REAL, cd_rel_drift REAL, cd_rel_amp REAL,
    message        TEXT, workdir TEXT,
    decided_by     TEXT, reason TEXT, machine TEXT
);
CREATE TABLE IF NOT EXISTS events (
    event_id INTEGER PRIMARY KEY, ts TEXT, level TEXT, kind TEXT,
    run_id INTEGER, geom_id TEXT, message TEXT
);
CREATE TABLE IF NOT EXISTS control (key TEXT PRIMARY KEY, value TEXT, updated_at TEXT);
CREATE INDEX IF NOT EXISTS ix_runs_status ON runs(campaign, status);
CREATE INDEX IF NOT EXISTS ix_att_run ON attempts(run_id);
"""


def _migrate(con) -> None:
    """Eski veritabanlarına yeni sütunları ekler (idempotent)."""
    cols = {r["name"] for r in con.execute("PRAGMA table_info(runs)").fetchall()}
    if "budget_base" not in cols:
        con.execute("ALTER TABLE runs ADD COLUMN budget_base INTEGER DEFAULT 0")


def now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


@contextmanager
def connect(path: Path = DB_PATH):
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path, timeout=60, isolation_level=None)   # autocommit; açık BEGIN ile işlem
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA busy_timeout=60000")
    try:
        con.executescript(SCHEMA)
        _migrate(con)
        yield con
    finally:
        con.close()


def event(con, level: str, kind: str, message: str, run_id: int | None = None, geom_id: str | None = None) -> None:
    ts = now()
    con.execute("INSERT INTO events (ts, level, kind, run_id, geom_id, message) VALUES (?,?,?,?,?,?)",
                (ts, level, kind, run_id, geom_id, message))
    EVENTS_JSONL.parent.mkdir(parents=True, exist_ok=True)
    with open(EVENTS_JSONL, "a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": ts, "level": level, "kind": kind, "run_id": run_id,
                            "geom_id": geom_id, "message": message}, ensure_ascii=False) + "\n")


def get_control(con, key: str) -> str | None:
    r = con.execute("SELECT value FROM control WHERE key=?", (key,)).fetchone()
    return r["value"] if r else None


def set_control(con, key: str, value: str | None) -> None:
    if value is None:
        con.execute("DELETE FROM control WHERE key=?", (key,))
    else:
        con.execute("INSERT INTO control (key, value, updated_at) VALUES (?,?,?) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
                    (key, value, now()))


def ensure_runs(con, campaign: str, geom_ids: list[str], points: list[dict], mesh_version: str = "v1") -> int:
    """(geom × hız) satırlarını yoksa ekler. points: velocities.json noktaları (+mach/regime eklenmiş)."""
    n = 0
    con.execute("BEGIN")
    for g in geom_ids:
        for p in points:
            cur = con.execute(
                "INSERT OR IGNORE INTO runs (campaign, geom_id, vel_idx, velocity_ms, mach, altitude_m, regime, "
                "mesh_version, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
                (campaign, g, p["index"], p["velocity_ms"], p["mach"], p["altitude_m"], p["regime"], mesh_version, now()))
            n += cur.rowcount
    con.execute("COMMIT")
    return n


def find_run(con, ref: str, campaign: str = "main"):
    """ref: run_id (sayı) veya 'P16_L300:5' biçimi."""
    if ref.isdigit():
        return con.execute("SELECT * FROM runs WHERE run_id=?", (int(ref),)).fetchone()
    g, _, v = ref.partition(":")
    return con.execute("SELECT * FROM runs WHERE campaign=? AND geom_id=? AND vel_idx=?",
                       (campaign, g.upper(), int(v))).fetchone()
