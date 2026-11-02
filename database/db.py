"""SQLite persistence layer for the SDLC Orchestration Platform.

All workflow state lives here: projects, stage approvals, stage payloads,
status history and the audit trail. The public API is intentionally narrow
so the backend can later be swapped from SQLite to Databricks Delta / Unity
Catalog without touching the UI or the agent services.

Workflow rules encoded here:
    * every stage requires explicit user approval before the next unlocks
    * a completed stage can be reopened (downstream approvals are revoked)
    * state persists across restarts (single .db file)
    * every transition is written to status_history and audit_log
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "database" / "sdlc_orchestrator.db"
ARTIFACTS_DIR = BASE_DIR / "artifacts"

STAGES = ["requirements", "jira", "build", "testing", "release"]
STAGE_LABELS = {
    "requirements": "Requirements Analysis",
    "jira": "Jira Story",
    "build": "Build & Deploy",
    "testing": "Validation & Testing",
    "release": "Release & Pull Request",
}
STATUS_LABELS = {
    "pending": "Pending",
    "in_progress": "In Progress",
    "completed": "Completed",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    return conn


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    with closing(_connect()) as conn, conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS projects (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT NOT NULL UNIQUE,
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS stage_status (
                project_id  INTEGER NOT NULL,
                stage       TEXT NOT NULL,
                status      TEXT NOT NULL DEFAULT 'pending',
                approved    INTEGER NOT NULL DEFAULT 0,
                approved_at TEXT,
                updated_at  TEXT,
                PRIMARY KEY (project_id, stage)
            );

            CREATE TABLE IF NOT EXISTS stage_data (
                project_id  INTEGER NOT NULL,
                stage       TEXT NOT NULL,
                data_key    TEXT NOT NULL,
                data_json   TEXT NOT NULL,
                updated_at  TEXT NOT NULL,
                PRIMARY KEY (project_id, stage, data_key)
            );

            CREATE TABLE IF NOT EXISTS status_history (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id   INTEGER NOT NULL,
                stage        TEXT NOT NULL,
                from_status  TEXT NOT NULL,
                to_status    TEXT NOT NULL,
                actor        TEXT NOT NULL,
                changed_at   TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS audit_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id  INTEGER,
                stage       TEXT,
                action      TEXT NOT NULL,
                details     TEXT NOT NULL,
                logged_at   TEXT NOT NULL
            );
            """
        )


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------

def create_project(name: str) -> int:
    """Create a project (or return the id of an existing project with this name)."""
    now = _now()
    with closing(_connect()) as conn, conn:
        conn.execute(
            "INSERT OR IGNORE INTO projects (name, created_at, updated_at) VALUES (?, ?, ?)",
            (name, now, now),
        )
        row = conn.execute("SELECT id FROM projects WHERE name = ?", (name,)).fetchone()
        return int(row["id"])


def list_projects() -> list:
    with closing(_connect()) as conn:
        rows = conn.execute("SELECT * FROM projects ORDER BY id").fetchall()
        return [dict(r) for r in rows]


def get_project(project_id: int):
    with closing(_connect()) as conn:
        row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        return dict(row) if row else None


# ---------------------------------------------------------------------------
# Stage state machine
# ---------------------------------------------------------------------------

def approve_stage(project_id: int, stage: str, actor: str = "user") -> None:
    if stage not in STAGES:
        raise ValueError("Unknown stage: %s" % stage)
    before = derive_statuses(project_id)[stage]["status"]
    now = _now()
    with closing(_connect()) as conn, conn:
        conn.execute(
            "INSERT INTO stage_status (project_id, stage, status, approved, approved_at, updated_at) "
            "VALUES (?, ?, 'completed', 1, ?, ?) "
            "ON CONFLICT (project_id, stage) DO UPDATE SET status='completed', approved=1, "
            "approved_at=excluded.approved_at, updated_at=excluded.updated_at",
            (project_id, stage, now, now),
        )
    record_history(project_id, stage, before, "completed", actor)
    log_audit(project_id, stage, "approved", "Stage '%s' approved by %s" % (STAGE_LABELS[stage], actor))


def reopen_stage(project_id: int, stage: str, actor: str = "user") -> None:
    """Reopen a completed stage; its approval and every downstream approval
    are revoked. Generated data is retained for review."""
    idx = STAGES.index(stage)
    affected = STAGES[idx:]
    before = derive_statuses(project_id)
    now = _now()
    with closing(_connect()) as conn, conn:
        for s in affected:
            conn.execute(
                "INSERT INTO stage_status (project_id, stage, updated_at) VALUES (?, ?, ?) "
                "ON CONFLICT (project_id, stage) DO UPDATE SET "
                "status='pending', approved=0, approved_at=NULL, updated_at=excluded.updated_at",
                (project_id, s, now),
            )
        conn.execute(
            "UPDATE stage_status SET status='in_progress', updated_at=? WHERE project_id=? AND stage=?",
            (now, project_id, stage),
        )
    record_history(project_id, stage, before[stage]["status"], "in_progress", actor)
    log_audit(
        project_id, stage, "reopened",
        "Stage '%s' reopened by %s; downstream approvals revoked" % (STAGE_LABELS[stage], actor),
    )
    for s in STAGES[idx + 1:]:
        if before[s]["status"] == "completed":
            record_history(project_id, s, "completed", "pending", actor)
            log_audit(project_id, s, "revoked", "Approval revoked because '%s' was reopened" % STAGE_LABELS[stage])


def get_approvals(project_id: int) -> dict:
    with closing(_connect()) as conn:
        rows = conn.execute(
            "SELECT stage, approved FROM stage_status WHERE project_id = ?", (project_id,)
        ).fetchall()
        return {r["stage"]: bool(r["approved"]) for r in rows}


def derive_statuses(project_id: int) -> dict:
    """Derive the display status of every stage from approval flags:
    completed   -> stage approved
    in_progress -> all previous stages approved, this one not yet
    pending     -> at least one previous stage is not approved
    """
    approvals = get_approvals(project_id)
    statuses = {}
    all_prior_approved = True
    for stage in STAGES:
        approved = approvals.get(stage, False)
        if approved:
            status = "completed"
        elif all_prior_approved:
            status = "in_progress"
        else:
            status = "pending"
        statuses[stage] = {"status": status, "approved": approved}
        all_prior_approved = all_prior_approved and approved
    return statuses


# ---------------------------------------------------------------------------
# Stage payloads
# ---------------------------------------------------------------------------

def save_stage_data(project_id: int, stage: str, data_key: str, data: dict) -> None:
    with closing(_connect()) as conn, conn:
        conn.execute(
            "INSERT INTO stage_data (project_id, stage, data_key, data_json, updated_at) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT (project_id, stage, data_key) DO UPDATE SET "
            "data_json=excluded.data_json, updated_at=excluded.updated_at",
            (project_id, stage, data_key, json.dumps(data, ensure_ascii=False), _now()),
        )


def load_stage_data(project_id: int, stage: str, data_key: str):
    with closing(_connect()) as conn:
        row = conn.execute(
            "SELECT data_json FROM stage_data WHERE project_id=? AND stage=? AND data_key=?",
            (project_id, stage, data_key),
        ).fetchone()
        return json.loads(row["data_json"]) if row else None


# ---------------------------------------------------------------------------
# History & audit
# ---------------------------------------------------------------------------

def record_history(project_id: int, stage: str, from_status: str, to_status: str, actor: str = "user") -> None:
    with closing(_connect()) as conn, conn:
        conn.execute(
            "INSERT INTO status_history (project_id, stage, from_status, to_status, actor, changed_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (project_id, stage, from_status, to_status, actor, _now()),
        )


def get_status_history(project_id: int) -> list:
    with closing(_connect()) as conn:
        rows = conn.execute(
            "SELECT * FROM status_history WHERE project_id=? ORDER BY id DESC LIMIT 100",
            (project_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def log_audit(project_id: int, stage, action: str, details: str) -> None:
    with closing(_connect()) as conn, conn:
        conn.execute(
            "INSERT INTO audit_log (project_id, stage, action, details, logged_at) VALUES (?, ?, ?, ?, ?)",
            (project_id, stage, action, details, _now()),
        )


def get_audit_log(project_id: int, limit: int = 50) -> list:
    with closing(_connect()) as conn:
        rows = conn.execute(
            "SELECT * FROM audit_log WHERE project_id=? ORDER BY id DESC LIMIT ?",
            (project_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Artifacts
# ---------------------------------------------------------------------------

def get_artifacts_dir(project_id: int) -> Path:
    path = ARTIFACTS_DIR / str(project_id)
    path.mkdir(parents=True, exist_ok=True)
    return path
