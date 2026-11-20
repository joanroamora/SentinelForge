"""SQLite persistence for local demo reports and their audit events."""

from __future__ import annotations

import json
import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from .contracts import AnalysisReport, ReportRevision

SCHEMA_VERSION = 1
DEFAULT_DATABASE_PATH = Path(".sentinelforge/analyses.sqlite3")


class ReportConflictError(ValueError):
    """Raised when an analysis ID is reused for different report content."""


class SQLiteReportRepository:
    """Stores immutable report revisions and append-only persistence events."""

    def __init__(self, database_path: str | Path | None = None) -> None:
        configured_path = database_path or os.environ.get(
            "SENTINELFORGE_DATABASE_PATH", DEFAULT_DATABASE_PATH
        )
        self.database_path = Path(configured_path)

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database_path, timeout=10, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            self._initialize(connection)
            yield connection
        finally:
            connection.close()

    @staticmethod
    def _initialize(connection: sqlite3.Connection) -> None:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        if version == SCHEMA_VERSION:
            return
        if version != 0:
            raise RuntimeError(f"unsupported_database_schema_version:{version}")

        connection.execute("BEGIN IMMEDIATE")
        try:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version == 0:
                connection.execute(
                    """
                    CREATE TABLE report_revisions (
                        analysis_id TEXT NOT NULL,
                        revision INTEGER NOT NULL CHECK (revision > 0),
                        report_json TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        PRIMARY KEY (analysis_id, revision)
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE TRIGGER report_revisions_no_update
                    BEFORE UPDATE ON report_revisions
                    BEGIN
                        SELECT RAISE(ABORT, 'report_revisions_are_immutable');
                    END
                    """
                )
                connection.execute(
                    """
                    CREATE TRIGGER report_revisions_no_delete
                    BEFORE DELETE ON report_revisions
                    BEGIN
                        SELECT RAISE(ABORT, 'report_revisions_are_immutable');
                    END
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE analysis_events (
                        sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                        event_id TEXT NOT NULL UNIQUE,
                        analysis_id TEXT NOT NULL,
                        event_type TEXT NOT NULL,
                        occurred_at TEXT NOT NULL,
                        payload_json TEXT NOT NULL
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE TRIGGER analysis_events_no_update
                    BEFORE UPDATE ON analysis_events
                    BEGIN
                        SELECT RAISE(ABORT, 'analysis_events_are_append_only');
                    END
                    """
                )
                connection.execute(
                    """
                    CREATE TRIGGER analysis_events_no_delete
                    BEFORE DELETE ON analysis_events
                    BEGIN
                        SELECT RAISE(ABORT, 'analysis_events_are_append_only');
                    END
                    """
                )
                connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            elif version != SCHEMA_VERSION:
                raise RuntimeError(f"unsupported_database_schema_version:{version}")
            connection.commit()
        except Exception:
            connection.rollback()
            raise

    def save_report(self, report: AnalysisReport) -> None:
        self.append_report_revision(report, expected_revision=0)

    def append_report_revision(
        self,
        report: AnalysisReport,
        *,
        expected_revision: int,
    ) -> int:
        report_json = report.model_dump_json()
        analysis_id = report.analysis.id

        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                latest = connection.execute(
                    """
                    SELECT revision, report_json FROM report_revisions
                    WHERE analysis_id = ? ORDER BY revision DESC LIMIT 1
                    """,
                    (analysis_id,),
                ).fetchone()
                current_revision = 0 if latest is None else latest["revision"]
                if latest is not None and latest["report_json"] == report_json:
                    connection.commit()
                    return current_revision
                if current_revision != expected_revision:
                    raise ReportConflictError("report_revision_conflict")

                next_revision = current_revision + 1
                occurred_at = datetime.now(UTC).isoformat()
                event_type = (
                    "report_created" if next_revision == 1 else "report_revision_created"
                )

                connection.execute(
                    """
                    INSERT INTO report_revisions
                        (analysis_id, revision, report_json, created_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        analysis_id,
                        next_revision,
                        report_json,
                        occurred_at,
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO analysis_events
                        (event_id, analysis_id, event_type, occurred_at, payload_json)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        str(uuid4()),
                        analysis_id,
                        event_type,
                        occurred_at,
                        json.dumps(
                            {"revision": next_revision}, separators=(",", ":")
                        ),
                    ),
                )
                connection.commit()
                return next_revision
            except Exception:
                connection.rollback()
                raise

    def get_report(self, analysis_id: str) -> AnalysisReport | None:
        result = self.get_revision(analysis_id)
        return None if result is None else result.report

    def get_revision(
        self, analysis_id: str, revision: int | None = None
    ) -> ReportRevision | None:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT revision, report_json FROM report_revisions
                WHERE analysis_id = ? AND (? IS NULL OR revision = ?)
                ORDER BY revision DESC LIMIT 1
                """,
                (analysis_id, revision, revision),
            ).fetchone()
        if row is None:
            return None
        return ReportRevision(
            revision=row["revision"],
            report=AnalysisReport.model_validate_json(row["report_json"]),
        )

    def list_events(self, analysis_id: str) -> list[dict[str, str]]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT event_id, analysis_id, event_type, occurred_at, payload_json
                FROM analysis_events WHERE analysis_id = ? ORDER BY sequence
                """,
                (analysis_id,),
            ).fetchall()
        return [dict(row) for row in rows]
