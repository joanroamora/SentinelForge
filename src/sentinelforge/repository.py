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
from .workflow import WorkflowCheckpoint, WorkflowConflictError, next_checkpoint

SCHEMA_VERSION = 2
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
        if version not in (0, 1):
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
                version = 1
            if version == 1:
                connection.execute(
                    """
                    CREATE TABLE workflow_checkpoints (
                        analysis_id TEXT NOT NULL,
                        version INTEGER NOT NULL CHECK (version > 0),
                        checkpoint_json TEXT NOT NULL,
                        PRIMARY KEY (analysis_id, version)
                    )
                    """
                )
                for operation in ("UPDATE", "DELETE"):
                    connection.execute(
                        f"""
                        CREATE TRIGGER workflow_checkpoints_no_{operation.lower()}
                        BEFORE {operation} ON workflow_checkpoints
                        BEGIN
                            SELECT RAISE(ABORT, 'workflow_checkpoints_are_immutable');
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
                self._insert_report_revision(connection, report, next_revision)
                connection.commit()
                return next_revision
            except Exception:
                connection.rollback()
                raise

    @staticmethod
    def _append_event(
        connection: sqlite3.Connection,
        analysis_id: str,
        event_type: str,
        payload: dict[str, str | int],
    ) -> None:
        connection.execute(
            """
            INSERT INTO analysis_events
                (event_id, analysis_id, event_type, occurred_at, payload_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (str(uuid4()), analysis_id, event_type, datetime.now(UTC).isoformat(),
             json.dumps(payload, separators=(",", ":"))),
        )

    def _insert_report_revision(
        self, connection: sqlite3.Connection, report: AnalysisReport, revision: int
    ) -> None:
        workflow = self._read_checkpoint(connection, report.analysis.id)
        if workflow is not None and workflow.state != "COMPLETED":
            raise WorkflowConflictError("workflow_report_not_ready")
        connection.execute(
            """
            INSERT INTO report_revisions (analysis_id, revision, report_json, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (report.analysis.id, revision, report.model_dump_json(), datetime.now(UTC).isoformat()),
        )
        self._append_event(
            connection, report.analysis.id,
            "report_created" if revision == 1 else "report_revision_created",
            {"revision": revision},
        )

    @staticmethod
    def _read_checkpoint(
        connection: sqlite3.Connection, analysis_id: str, version: int | None = None
    ) -> WorkflowCheckpoint | None:
        row = connection.execute(
            """
            SELECT checkpoint_json FROM workflow_checkpoints
            WHERE analysis_id = ? AND (? IS NULL OR version = ?)
            ORDER BY version DESC LIMIT 1
            """,
            (analysis_id, version, version),
        ).fetchone()
        return None if row is None else WorkflowCheckpoint.model_validate_json(row[0])

    def _insert_checkpoint(
        self, connection: sqlite3.Connection, checkpoint: WorkflowCheckpoint
    ) -> None:
        connection.execute(
            "INSERT INTO workflow_checkpoints VALUES (?, ?, ?)",
            (checkpoint.analysis_id, checkpoint.version, checkpoint.model_dump_json()),
        )
        self._append_event(
            connection, checkpoint.analysis_id,
            "workflow_created" if checkpoint.version == 1 else "workflow_advanced",
            {"schema_version": "1.0", "version": checkpoint.version, "state": checkpoint.state},
        )

    def create_workflow(self, checkpoint: WorkflowCheckpoint) -> None:
        if checkpoint.version != 1:
            raise WorkflowConflictError("workflow_must_start_at_received")
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                existing = self._read_checkpoint(connection, checkpoint.analysis_id, 1)
                if existing is not None:
                    if existing != checkpoint:
                        raise WorkflowConflictError("workflow_id_conflict")
                else:
                    report_exists = connection.execute(
                        "SELECT 1 FROM report_revisions WHERE analysis_id = ? LIMIT 1",
                        (checkpoint.analysis_id,),
                    ).fetchone()
                    if report_exists:
                        raise WorkflowConflictError("workflow_id_conflict")
                    self._insert_checkpoint(connection, checkpoint)
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    def get_workflow(self, analysis_id: str) -> WorkflowCheckpoint | None:
        with self._connection() as connection:
            return self._read_checkpoint(connection, analysis_id)

    def advance_workflow(
        self, analysis_id: str, *, expected_version: int,
        final_report: AnalysisReport | None = None,
    ) -> WorkflowCheckpoint:
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                current = self._read_checkpoint(connection, analysis_id)
                if current is None:
                    raise LookupError("analysis_workflow_not_found")
                if type(expected_version) is not int or expected_version < 1:
                    raise WorkflowConflictError("workflow_version_conflict")
                if expected_version < current.version:
                    replay = self._read_checkpoint(connection, analysis_id, expected_version + 1)
                    if replay is None:
                        raise WorkflowConflictError("workflow_checkpoint_missing")
                    connection.commit()
                    return replay
                if expected_version != current.version:
                    raise WorkflowConflictError("workflow_version_conflict")
                advanced = next_checkpoint(current)
                if advanced != current:
                    self._insert_checkpoint(connection, advanced)
                    if advanced.state == "COMPLETED":
                        if (
                            final_report is None
                            or final_report.analysis.id != analysis_id
                            or final_report.analysis.status != "COMPLETED"
                            or final_report.analysis.created_at != current.created_at
                        ):
                            raise ValueError("workflow_final_report_required")
                        self._insert_report_revision(connection, final_report, 1)
                connection.commit()
                return advanced
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
