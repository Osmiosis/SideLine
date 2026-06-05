"""SQLite job store. Knows nothing about HTTP or pipelines."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


def connect(path: Path | str) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS jobs (
            job_id      TEXT PRIMARY KEY,
            sport       TEXT NOT NULL,
            match_name  TEXT NOT NULL,
            match_date  TEXT NOT NULL,
            state       TEXT NOT NULL DEFAULT 'created',
            stage       TEXT,
            progress    INTEGER NOT NULL DEFAULT 0,
            error       TEXT,
            created_at  TEXT NOT NULL
        )
        """
    )
    # Migration: duration_sec added later (footage-hours dashboard stat).
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(jobs)")}
    if "duration_sec" not in cols:
        conn.execute("ALTER TABLE jobs ADD COLUMN duration_sec REAL")
    conn.commit()


def insert_job(conn: sqlite3.Connection, *, job_id: str, sport: str,
               match_name: str, match_date: str, created_at: str) -> None:
    conn.execute(
        "INSERT INTO jobs (job_id, sport, match_name, match_date, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (job_id, sport, match_name, match_date, created_at),
    )
    conn.commit()


def get_job(conn: sqlite3.Connection, job_id: str) -> sqlite3.Row | None:
    cur = conn.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,))
    return cur.fetchone()


def update_job(conn: sqlite3.Connection, job_id: str, **fields: Any) -> None:
    allowed = {"state", "stage", "progress", "error"}
    sets = {k: v for k, v in fields.items() if k in allowed}
    if not sets:
        return
    cols = ", ".join(f"{k} = ?" for k in sets)
    conn.execute(
        f"UPDATE jobs SET {cols} WHERE job_id = ?",
        (*sets.values(), job_id),
    )
    conn.commit()


def set_duration(conn: sqlite3.Connection, job_id: str, duration_sec: float) -> None:
    conn.execute("UPDATE jobs SET duration_sec = ? WHERE job_id = ?",
                 (duration_sec, job_id))
    conn.commit()


def list_jobs(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    cur = conn.execute("SELECT * FROM jobs ORDER BY created_at DESC")
    return cur.fetchall()


def next_queued(conn: sqlite3.Connection) -> sqlite3.Row | None:
    cur = conn.execute(
        "SELECT * FROM jobs WHERE state = 'queued' ORDER BY created_at ASC LIMIT 1"
    )
    return cur.fetchone()
