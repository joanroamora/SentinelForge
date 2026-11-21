"""SQLite persistence for local demo reports and their audit events."""

from __future__ import annotations

import json
import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from .contracts import AnalysisReport, ReportRevision
from .local_scan import LocalScanReport
from .monitor import (
    MonitorAnswerReceipt,
    MonitorAnswerRequest,
    MonitorConflictError,
    MonitorQuestion,
    apply_monitor_report,
    make_monitor_question,
    make_monitor_statement,
)
from .scan_case import ScanAnswerReceipt, ScanCase, answer_scan_case, new_scan_case
from .simulation import SimulationTrace, advance_simulation, enrich_demo_report
from .source_review import SourceReview, SourceReviewError, SourceReviewReceipt
from .workflow import WorkflowCheckpoint, WorkflowConflictError, next_checkpoint

SCHEMA_VERSION = 6
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
        if version not in (0, 1, 2, 3, 4, 5):
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
                version = 2
            if version == 2:
                connection.execute(
                    """
                    CREATE TABLE workflow_simulations (
                        analysis_id TEXT NOT NULL,
                        checkpoint_version INTEGER NOT NULL,
                        trace_json TEXT NOT NULL,
                        PRIMARY KEY (analysis_id, checkpoint_version),
                        FOREIGN KEY (analysis_id, checkpoint_version)
                            REFERENCES workflow_checkpoints (analysis_id, version)
                    )
                    """
                )
                for operation in ("UPDATE", "DELETE"):
                    connection.execute(
                        f"""
                        CREATE TRIGGER workflow_simulations_no_{operation.lower()}
                        BEFORE {operation} ON workflow_simulations
                        BEGIN
                            SELECT RAISE(ABORT, 'workflow_simulations_are_immutable');
                        END
                        """
                    )
                version = 3
            if version == 3:
                connection.execute(
                    """
                    CREATE TABLE monitor_questions (
                        question_id TEXT PRIMARY KEY,
                        analysis_id TEXT NOT NULL UNIQUE,
                        checkpoint_version INTEGER NOT NULL DEFAULT 1 CHECK (checkpoint_version = 1),
                        question_json TEXT NOT NULL,
                        FOREIGN KEY (analysis_id, checkpoint_version)
                            REFERENCES workflow_checkpoints (analysis_id, version)
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE monitor_answers (
                        submission_id TEXT PRIMARY KEY,
                        question_id TEXT NOT NULL UNIQUE,
                        request_json TEXT NOT NULL,
                        receipt_json TEXT NOT NULL,
                        FOREIGN KEY (question_id) REFERENCES monitor_questions (question_id)
                    )
                    """
                )
                for table in ("monitor_questions", "monitor_answers"):
                    for operation in ("UPDATE", "DELETE"):
                        connection.execute(
                            f"""
                            CREATE TRIGGER {table}_no_{operation.lower()}
                            BEFORE {operation} ON {table}
                            BEGIN SELECT RAISE(ABORT, '{table}_are_immutable'); END
                            """
                        )
                version = 4
            if version == 4:
                connection.execute("""
                    CREATE TABLE local_scan_revisions (
                        analysis_id TEXT NOT NULL,
                        revision INTEGER NOT NULL CHECK (revision > 0),
                        record_json TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        PRIMARY KEY (analysis_id, revision)
                    )
                """)
                connection.execute("""
                    CREATE TABLE local_scan_submissions (
                        submission_id TEXT PRIMARY KEY,
                        analysis_id TEXT NOT NULL,
                        revision INTEGER NOT NULL,
                        request_json TEXT NOT NULL,
                        receipt_json TEXT NOT NULL,
                        FOREIGN KEY (analysis_id, revision)
                            REFERENCES local_scan_revisions (analysis_id, revision)
                    )
                """)
                for table in ("local_scan_revisions", "local_scan_submissions"):
                    for operation in ("UPDATE", "DELETE"):
                        connection.execute(f"""
                            CREATE TRIGGER {table}_no_{operation.lower()}
                            BEFORE {operation} ON {table}
                            BEGIN SELECT RAISE(ABORT, '{table}_are_immutable'); END
                        """)
                version = 5
            if version == 5:
                connection.execute("""
                    CREATE TABLE local_scan_verifications (
                        submission_id TEXT PRIMARY KEY,
                        analysis_id TEXT NOT NULL,
                        revision INTEGER NOT NULL,
                        receipt_json TEXT NOT NULL,
                        FOREIGN KEY (analysis_id, revision)
                            REFERENCES local_scan_revisions (analysis_id, revision)
                    )
                """)
                for operation in ("UPDATE", "DELETE"):
                    connection.execute(f"""
                        CREATE TRIGGER local_scan_verifications_no_{operation.lower()}
                        BEFORE {operation} ON local_scan_verifications
                        BEGIN SELECT RAISE(ABORT, 'local_scan_verifications_are_immutable'); END
                    """)
                version = 6
            if version != SCHEMA_VERSION:
                raise RuntimeError(f"unsupported_database_schema_version:{version}")
            connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            connection.commit()
        except Exception:
            connection.rollback()
            raise

    def save_report(self, report: AnalysisReport) -> None:
        self.append_report_revision(report, expected_revision=0)

    @staticmethod
    def _read_scan(connection, analysis_id: str, revision: int | None = None) -> ScanCase | None:
        row = connection.execute(
            "SELECT record_json FROM local_scan_revisions "
            "WHERE analysis_id = ? AND (? IS NULL OR revision = ?) ORDER BY revision DESC LIMIT 1",
            (analysis_id, revision, revision),
        ).fetchone()
        return None if row is None else ScanCase.model_validate_json(row[0])

    def _insert_scan(self, connection, case: ScanCase) -> None:
        connection.execute(
            "INSERT INTO local_scan_revisions VALUES (?, ?, ?, ?)",
            (case.id, case.revision, case.model_dump_json(), case.created_at.isoformat()),
        )
        self._append_event(connection, case.id, "local_scan_revision_created",
                           {"revision": case.revision, "status": case.status})

    def save_local_scan(self, report: LocalScanReport) -> ScanCase:
        initial = new_scan_case(report)
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                existing = self._read_scan(connection, initial.id)
                if existing is not None:
                    if existing.report != report:
                        raise ReportConflictError("local_scan_fingerprint_conflict")
                    connection.commit()
                    return existing
                self._insert_scan(connection, initial)
                connection.commit()
                return initial
            except Exception:
                connection.rollback()
                raise

    def get_local_scan(self, analysis_id: str, revision: int | None = None) -> ScanCase | None:
        with self._connection() as connection:
            return self._read_scan(connection, analysis_id, revision)

    def list_local_scans(self, *, limit: int = 25, offset: int = 0) -> list[ScanCase]:
        if not 1 <= limit <= 100 or offset < 0:
            raise ValueError("invalid_scan_pagination")
        with self._connection() as connection:
            rows = connection.execute("""
                SELECT r.record_json FROM local_scan_revisions r
                JOIN (SELECT analysis_id, MAX(revision) AS revision FROM local_scan_revisions
                      GROUP BY analysis_id) latest
                  ON r.analysis_id = latest.analysis_id AND r.revision = latest.revision
                ORDER BY r.created_at DESC, r.analysis_id LIMIT ? OFFSET ?
            """, (limit, offset)).fetchall()
        return [ScanCase.model_validate_json(row[0]) for row in rows]

    def answer_local_scan(self, analysis_id: str, request: MonitorAnswerRequest) -> ScanAnswerReceipt:
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                current = self._read_scan(connection, analysis_id)
                if current is None or current.question is None:
                    raise LookupError("scan_question_not_found")
                previous = connection.execute(
                    "SELECT analysis_id, request_json, receipt_json FROM local_scan_submissions "
                    "WHERE submission_id = ?", (str(request.submission_id),),
                ).fetchone()
                if previous is not None:
                    if (previous["analysis_id"] != analysis_id or
                            previous["request_json"] != request.model_dump_json()):
                        raise MonitorConflictError("monitor_submission_conflict")
                    connection.commit()
                    return ScanAnswerReceipt.model_validate_json(previous["receipt_json"])
                if current.human_statements:
                    raise MonitorConflictError("monitor_question_already_answered")
                revised = answer_scan_case(current, request)
                self._insert_scan(connection, revised)
                receipt = ScanAnswerReceipt(
                    analysis_id=analysis_id, submission_id=request.submission_id,
                    question_id=current.question.id, revision=revised.revision,
                    statement=revised.human_statements[0],
                )
                connection.execute("INSERT INTO local_scan_submissions VALUES (?, ?, ?, ?, ?)",
                                   (str(request.submission_id), analysis_id, revised.revision,
                                    request.model_dump_json(), receipt.model_dump_json()))
                self._append_event(connection, analysis_id, "local_scan_context_received",
                                   {"submission_id": str(request.submission_id),
                                    "verification_status": "unverified"})
                connection.commit()
                return receipt
            except Exception:
                connection.rollback()
                raise

    def get_source_review_receipt(self, submission_id: UUID) -> SourceReviewReceipt | None:
        with self._connection() as connection:
            row = connection.execute("SELECT receipt_json FROM local_scan_verifications "
                                     "WHERE submission_id = ?", (str(submission_id),)).fetchone()
        return None if row is None else SourceReviewReceipt.model_validate_json(row[0])

    def save_source_review(self, analysis_id: str, submission_id: UUID,
                           review: SourceReview) -> SourceReviewReceipt:
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                previous = connection.execute("SELECT receipt_json FROM local_scan_verifications "
                                              "WHERE submission_id = ?", (str(submission_id),)).fetchone()
                if previous is not None:
                    receipt = SourceReviewReceipt.model_validate_json(previous[0])
                    if receipt.analysis_id != analysis_id or receipt.review.source_sha256 != review.source_sha256:
                        raise SourceReviewError("source_review_submission_conflict")
                    connection.commit()
                    return receipt
                case = self._read_scan(connection, analysis_id)
                if case is None:
                    raise LookupError("local_scan_not_found")
                if case.source_review is not None:
                    raise SourceReviewError("source_review_already_recorded")
                payload = case.model_dump()
                payload.update(schema_version="1.1", revision=case.revision + 1,
                               source_review=review.model_dump())
                revised = ScanCase.model_validate(payload)
                self._insert_scan(connection, revised)
                receipt = SourceReviewReceipt(analysis_id=analysis_id, submission_id=submission_id,
                                              revision=revised.revision, review=review)
                connection.execute("INSERT INTO local_scan_verifications VALUES (?, ?, ?, ?)",
                                   (str(submission_id), analysis_id, revised.revision, receipt.model_dump_json()))
                self._append_event(connection, analysis_id, "local_scan_source_review_recorded",
                                   {"revision": revised.revision, "submission_id": str(submission_id),
                                    "scope": "static_pattern_only"})
                connection.commit()
                return receipt
            except Exception:
                connection.rollback()
                raise

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
        if workflow is not None:
            trace = self._read_simulation(connection, report.analysis.id, workflow.version)
            if trace is not None:
                report = enrich_demo_report(report, trace)
        question = self._read_monitor_question(connection, report.analysis.id)
        if question is not None:
            answer = self._read_monitor_answer(connection, question.id)
            report = apply_monitor_report(
                report, question, None if answer is None else answer.statement
            )
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

    @staticmethod
    def _read_simulation(
        connection: sqlite3.Connection, analysis_id: str, version: int | None = None
    ) -> SimulationTrace | None:
        row = connection.execute(
            """
            SELECT trace_json FROM workflow_simulations
            WHERE analysis_id = ? AND (? IS NULL OR checkpoint_version = ?)
            ORDER BY checkpoint_version DESC LIMIT 1
            """,
            (analysis_id, version, version),
        ).fetchone()
        return None if row is None else SimulationTrace.model_validate_json(row[0])

    @staticmethod
    def _insert_simulation(
        connection: sqlite3.Connection, checkpoint: WorkflowCheckpoint, trace: SimulationTrace
    ) -> None:
        connection.execute(
            """
            INSERT INTO workflow_simulations (analysis_id, checkpoint_version, trace_json)
            VALUES (?, ?, ?)
            """,
            (checkpoint.analysis_id, checkpoint.version, trace.model_dump_json()),
        )

    def get_simulation(
        self, analysis_id: str, *, checkpoint_version: int | None = None
    ) -> SimulationTrace | None:
        with self._connection() as connection:
            return self._read_simulation(connection, analysis_id, checkpoint_version)

    def create_workflow(
        self, checkpoint: WorkflowCheckpoint, *, simulation: SimulationTrace | None = None,
        monitored: bool = False,
    ) -> None:
        if checkpoint.version != 1:
            raise WorkflowConflictError("workflow_must_start_at_received")
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                existing = self._read_checkpoint(connection, checkpoint.analysis_id, 1)
                if existing is not None:
                    if (
                        existing != checkpoint
                        or self._read_simulation(connection, checkpoint.analysis_id, 1) != simulation
                        or (self._read_monitor_question(connection, checkpoint.analysis_id) is not None)
                        != monitored
                    ):
                        raise WorkflowConflictError("workflow_id_conflict")
                else:
                    report_exists = connection.execute(
                        "SELECT 1 FROM report_revisions WHERE analysis_id = ? LIMIT 1",
                        (checkpoint.analysis_id,),
                    ).fetchone()
                    if report_exists:
                        raise WorkflowConflictError("workflow_id_conflict")
                    self._insert_checkpoint(connection, checkpoint)
                    if simulation is not None:
                        self._insert_simulation(connection, checkpoint, simulation)
                    if monitored:
                        question = make_monitor_question(checkpoint.analysis_id, checkpoint.created_at)
                        connection.execute(
                            """
                            INSERT INTO monitor_questions (question_id, analysis_id, question_json)
                            VALUES (?, ?, ?)
                            """,
                            (question.id, checkpoint.analysis_id, question.model_dump_json()),
                        )
                        self._append_event(
                            connection, checkpoint.analysis_id, "monitor_question_created",
                            {"question_id": question.id, "finding_id": question.finding_id},
                        )
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
                    trace = self._read_simulation(connection, analysis_id, current.version)
                    if trace is None and self._read_simulation(connection, analysis_id) is not None:
                        raise ValueError("simulation_checkpoint_missing")
                    next_trace = None if trace is None else advance_simulation(trace, advanced.state)
                    self._insert_checkpoint(connection, advanced)
                    if next_trace is not None:
                        self._insert_simulation(connection, advanced, next_trace)
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

    @staticmethod
    def _read_monitor_question(
        connection: sqlite3.Connection, analysis_id: str, question_id: str | None = None
    ) -> MonitorQuestion | None:
        row = connection.execute(
            """
            SELECT question_json FROM monitor_questions
            WHERE analysis_id = ? AND (? IS NULL OR question_id = ?)
            """,
            (analysis_id, question_id, question_id),
        ).fetchone()
        return None if row is None else MonitorQuestion.model_validate_json(row[0])

    @staticmethod
    def _read_monitor_answer(
        connection: sqlite3.Connection, question_id: str
    ) -> MonitorAnswerReceipt | None:
        row = connection.execute(
            "SELECT receipt_json FROM monitor_answers WHERE question_id = ?", (question_id,)
        ).fetchone()
        return None if row is None else MonitorAnswerReceipt.model_validate_json(row[0])

    def get_monitor_questions(self, analysis_id: str) -> list[MonitorQuestion]:
        with self._connection() as connection:
            exists = connection.execute(
                """
                SELECT 1 FROM workflow_checkpoints WHERE analysis_id = ?
                UNION ALL SELECT 1 FROM report_revisions WHERE analysis_id = ? LIMIT 1
                """, (analysis_id, analysis_id),
            ).fetchone()
            if exists is None:
                raise LookupError("analysis_not_found")
            question = self._read_monitor_question(connection, analysis_id)
            if question is None:
                return []
            answer = self._read_monitor_answer(connection, question.id)
            if answer is not None:
                question = MonitorQuestion.model_validate(
                    question.model_dump() | {"status": "answered", "answer": answer.statement}
                )
            return [question]

    def answer_monitor_question(
        self, analysis_id: str, question_id: str, request: MonitorAnswerRequest
    ) -> MonitorAnswerReceipt:
        request_json = request.model_dump_json()
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                question = self._read_monitor_question(connection, analysis_id, question_id)
                if question is None:
                    raise LookupError("monitor_question_not_found")
                replay = connection.execute(
                    "SELECT question_id, request_json, receipt_json FROM monitor_answers "
                    "WHERE submission_id = ?", (str(request.submission_id),),
                ).fetchone()
                if replay is not None:
                    if replay["question_id"] != question_id or replay["request_json"] != request_json:
                        raise MonitorConflictError("monitor_submission_conflict")
                    connection.commit()
                    return MonitorAnswerReceipt.model_validate_json(replay["receipt_json"])
                if self._read_monitor_answer(connection, question_id) is not None:
                    raise MonitorConflictError("monitor_question_already_answered")
                latest = connection.execute(
                    "SELECT revision, report_json FROM report_revisions WHERE analysis_id = ? "
                    "ORDER BY revision DESC LIMIT 1", (analysis_id,),
                ).fetchone()
                revision = None if latest is None else latest["revision"] + 1
                receipt = MonitorAnswerReceipt(
                    question_id=question_id, submission_id=request.submission_id,
                    statement=make_monitor_statement(question, request), report_revision=revision,
                )
                connection.execute(
                    "INSERT INTO monitor_answers VALUES (?, ?, ?, ?)",
                    (str(request.submission_id), question_id, request_json, receipt.model_dump_json()),
                )
                self._append_event(
                    connection, analysis_id, "monitor_answer_recorded",
                    {"question_id": question_id, "submission_id": str(request.submission_id),
                     "verification_status": "unverified"},
                )
                if latest is not None:
                    self._insert_report_revision(
                        connection, AnalysisReport.model_validate_json(latest["report_json"]), revision
                    )
                connection.commit()
                return receipt
            except Exception:
                connection.rollback()
                raise

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
