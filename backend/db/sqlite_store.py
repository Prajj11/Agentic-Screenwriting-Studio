"""
SQLite database layer for persistent Script State storage.

Stores projects, scenes, characters, beats, continuity facts, and versioned snapshots.
Uses aiosqlite for async operations compatible with FastAPI.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from datetime import datetime

import aiosqlite

from models.script_state import ScriptState, ScriptVersion

logger = logging.getLogger(__name__)


class SQLiteStore:
    """Async SQLite store for screenplay project data."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def connect(self):
        """Open the database connection and create tables."""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(self.db_path)
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._create_tables()
        logger.info(f"SQLite connected: {self.db_path}")

    async def close(self):
        """Close the database connection."""
        if self._db:
            await self._db.close()
            self._db = None

    async def _create_tables(self):
        """Create all required tables if they don't exist."""
        await self._db.executescript("""
            CREATE TABLE IF NOT EXISTS projects (
                project_id TEXT PRIMARY KEY,
                title TEXT NOT NULL DEFAULT 'Untitled Project',
                state_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS versions (
                version_id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                version_number INTEGER NOT NULL,
                timestamp TEXT NOT NULL,
                changes_summary TEXT DEFAULT '',
                state_json TEXT NOT NULL,
                FOREIGN KEY (project_id) REFERENCES projects(project_id)
            );

            CREATE INDEX IF NOT EXISTS idx_versions_project
                ON versions(project_id, version_number);
        """)
        await self._db.commit()

    # ── Project CRUD ──────────────────────────────────────────────────

    async def save_script_state(self, state: ScriptState) -> str:
        """Save or update a full ScriptState. Returns the project_id."""
        state.update_metadata()
        state_json = state.model_dump_json()
        now = datetime.now().isoformat()

        await self._db.execute(
            """
            INSERT INTO projects (project_id, title, state_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(project_id) DO UPDATE SET
                title = excluded.title,
                state_json = excluded.state_json,
                updated_at = excluded.updated_at
            """,
            (state.project_id, state.title, state_json, state.created_at, now),
        )
        await self._db.commit()
        logger.info(f"Saved project {state.project_id}: {state.title}")
        return state.project_id

    async def load_script_state(self, project_id: str) -> ScriptState | None:
        """Load a ScriptState by project_id."""
        async with self._db.execute(
            "SELECT state_json FROM projects WHERE project_id = ?",
            (project_id,),
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return ScriptState.model_validate_json(row[0])
            return None

    async def list_projects(self) -> list[dict]:
        """List all projects with summary info."""
        async with self._db.execute(
            "SELECT project_id, title, created_at, updated_at FROM projects ORDER BY updated_at DESC"
        ) as cursor:
            rows = await cursor.fetchall()
            return [
                {
                    "project_id": r[0],
                    "title": r[1],
                    "created_at": r[2],
                    "updated_at": r[3],
                }
                for r in rows
            ]

    async def delete_project(self, project_id: str) -> bool:
        """Delete a project and all its versions."""
        await self._db.execute("DELETE FROM versions WHERE project_id = ?", (project_id,))
        result = await self._db.execute("DELETE FROM projects WHERE project_id = ?", (project_id,))
        await self._db.commit()
        return result.rowcount > 0

    # ── Versioning ────────────────────────────────────────────────────

    async def save_version(self, state: ScriptState, changes_summary: str = "") -> ScriptVersion:
        """Save a versioned snapshot of the current state."""
        # Get next version number
        async with self._db.execute(
            "SELECT MAX(version_number) FROM versions WHERE project_id = ?",
            (state.project_id,),
        ) as cursor:
            row = await cursor.fetchone()
            next_version = (row[0] or 0) + 1

        version = ScriptVersion(
            project_id=state.project_id,
            version_number=next_version,
            changes_summary=changes_summary,
            full_state_json=state.model_dump_json(),
        )

        await self._db.execute(
            """
            INSERT INTO versions (version_id, project_id, version_number, timestamp, changes_summary, state_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                version.version_id,
                version.project_id,
                version.version_number,
                version.timestamp,
                version.changes_summary,
                version.full_state_json,
            ),
        )
        await self._db.commit()
        logger.info(f"Saved version {next_version} for project {state.project_id}")
        return version

    async def load_version(self, project_id: str, version_number: int) -> ScriptState | None:
        """Load a specific version of a project."""
        async with self._db.execute(
            "SELECT state_json FROM versions WHERE project_id = ? AND version_number = ?",
            (project_id, version_number),
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return ScriptState.model_validate_json(row[0])
            return None

    async def list_versions(self, project_id: str) -> list[dict]:
        """List all versions for a project."""
        async with self._db.execute(
            """SELECT version_id, version_number, timestamp, changes_summary
               FROM versions WHERE project_id = ? ORDER BY version_number DESC""",
            (project_id,),
        ) as cursor:
            rows = await cursor.fetchall()
            return [
                {
                    "version_id": r[0],
                    "version_number": r[1],
                    "timestamp": r[2],
                    "changes_summary": r[3],
                }
                for r in rows
            ]


# ── Module-level singleton ────────────────────────────────────────────

_store: SQLiteStore | None = None


async def get_sqlite_store() -> SQLiteStore:
    """Get or create the singleton SQLite store."""
    global _store
    if _store is None:
        from config import settings
        _store = SQLiteStore(settings.sqlite_db_path)
        await _store.connect()
    return _store
