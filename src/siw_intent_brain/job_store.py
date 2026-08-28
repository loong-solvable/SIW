"""Persistent, owner-scoped job storage for the SIW web product."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class JobStore:
    """Small SQLite repository with one connection per operation.

    The web app uses ``ThreadingHTTPServer``. Opening short-lived connections and
    enabling WAL keeps requests isolated without sharing a connection across
    threads.
    """

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path).expanduser().resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 5000")
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _ensure_schema(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    owner_id TEXT NOT NULL,
                    kind TEXT NOT NULL CHECK (kind IN ('score', 'pipeline')),
                    status TEXT NOT NULL CHECK (
                        status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')
                    ),
                    input_summary TEXT NOT NULL,
                    result_json TEXT,
                    artifacts_json TEXT NOT NULL DEFAULT '{}',
                    error_code TEXT,
                    error_message TEXT,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_jobs_owner_created
                ON jobs(owner_id, created_at DESC);
                """
            )

    @staticmethod
    def _decode(row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        job = dict(row)
        job["result"] = (
            json.loads(job.pop("result_json"))
            if job.get("result_json") is not None
            else None
        )
        job["artifacts"] = json.loads(job.pop("artifacts_json") or "{}")
        return job

    def create_job(
        self,
        owner_id: str,
        kind: str,
        input_summary: str,
    ) -> dict[str, Any]:
        job_id = f"job_{uuid.uuid4().hex}"
        created_at = _utc_now()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO jobs (
                    id, owner_id, kind, status, input_summary, created_at
                ) VALUES (?, ?, ?, 'queued', ?, ?)
                """,
                (job_id, owner_id, kind, input_summary[:240], created_at),
            )
        job = self.get_job(job_id, owner_id)
        if job is None:  # pragma: no cover - defensive database invariant
            raise RuntimeError("created job could not be read")
        return job

    def get_job(self, job_id: str, owner_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM jobs WHERE id = ? AND owner_id = ?",
                (job_id, owner_id),
            ).fetchone()
        return self._decode(row)

    def list_jobs(self, owner_id: str, limit: int = 25) -> list[dict[str, Any]]:
        safe_limit = max(1, min(100, int(limit)))
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM jobs
                WHERE owner_id = ?
                ORDER BY rowid DESC
                LIMIT ?
                """,
                (owner_id, safe_limit),
            ).fetchall()
        return [job for row in rows if (job := self._decode(row)) is not None]

    def recover_interrupted_jobs(self) -> int:
        """Close jobs left active by a previous process.

        This is deliberately called once at application startup, not whenever a
        repository instance is created, so concurrent requests cannot interfere
        with work running in the current process.
        """
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE jobs
                SET status = 'failed', error_code = 'E_PROCESS_RESTARTED',
                    error_message = '服务曾重启，此任务未完成，请重新提交',
                    finished_at = ?
                WHERE status IN ('queued', 'running')
                """,
                (_utc_now(),),
            )
        return cursor.rowcount

    def mark_running(self, job_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE jobs
                SET status = 'running', started_at = ?, error_code = NULL,
                    error_message = NULL
                WHERE id = ? AND status = 'queued'
                """,
                (_utc_now(), job_id),
            )
            if cursor.rowcount != 1:
                raise KeyError(f"queued job not found: {job_id}")
            row = connection.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        job = self._decode(row)
        if job is None:  # pragma: no cover - defensive database invariant
            raise RuntimeError("running job could not be read")
        return job

    def mark_succeeded(
        self,
        job_id: str,
        result: dict[str, Any],
        artifacts: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        return self._finish(
            job_id,
            status="succeeded",
            result=result,
            artifacts=artifacts or {},
            error_code=None,
            error_message=None,
        )

    def mark_failed(
        self,
        job_id: str,
        error_code: str,
        error_message: str,
    ) -> dict[str, Any]:
        return self._finish(
            job_id,
            status="failed",
            result=None,
            artifacts={},
            error_code=error_code,
            error_message=error_message[:500],
        )

    def _finish(
        self,
        job_id: str,
        *,
        status: str,
        result: dict[str, Any] | None,
        artifacts: dict[str, str],
        error_code: str | None,
        error_message: str | None,
    ) -> dict[str, Any]:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE jobs
                SET status = ?, result_json = ?, artifacts_json = ?,
                    error_code = ?, error_message = ?, finished_at = ?
                WHERE id = ? AND status IN ('queued', 'running')
                """,
                (
                    status,
                    json.dumps(result, ensure_ascii=False) if result is not None else None,
                    json.dumps(artifacts, ensure_ascii=False),
                    error_code,
                    error_message,
                    _utc_now(),
                    job_id,
                ),
            )
            if cursor.rowcount != 1:
                raise KeyError(f"active job not found: {job_id}")
            row = connection.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        job = self._decode(row)
        if job is None:  # pragma: no cover - defensive database invariant
            raise RuntimeError("finished job could not be read")
        return job
