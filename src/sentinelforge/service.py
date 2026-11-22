"""Application service shared by the CLI and HTTP adapter."""

from pathlib import Path
from uuid import UUID

from .argument_lineage import (
    ArgumentInvestigationReceipt,
    LineageError,
    investigate_argument,
    original_lineage_bytes,
    require_corroboration,
)
from .contracts import Analysis, AnalysisReport, Evidence, Finding, HumanStatement, ReportRevision
from .demo_fixture import (
    EVIDENCE_DESCRIPTION,
    EVIDENCE_ID,
    FINDING_DESCRIPTION,
    FINDING_ID,
    FINDING_TITLE,
    LIMITATIONS,
    STATEMENT_EFFECT,
    STATEMENT_ID,
    STATEMENT_QUESTION,
    STATEMENT_TEXT,
)
from .evaluation import evaluate_corpus, load_builtin_corpus
from .evaluation_contracts import BuiltinCorpus, EvaluationReport
from .local_scan import LocalScanReport, scan_local_file, scan_source_bytes
from .local_source import load_local_source
from .monitor import MonitorAnswerReceipt, MonitorAnswerRequest, MonitorQuestion
from .repository import ReportConflictError, SQLiteReportRepository
from .scan_case import ScanAnswerReceipt, ScanCase
from .simulation import DemoFixtureId, SimulationStartRequest, SimulationTrace
from .source_review import (
    SourceReviewError,
    SourceReviewReceipt,
    ensure_original_bytes,
    review_original_source,
)
from .workflow import WorkflowCheckpoint


class AnalysisService:
    """Shared application entry point for demo history and bounded static scans."""

    def __init__(self, database_path: str | Path | None = None) -> None:
        self._repository = SQLiteReportRepository(database_path)

    def evaluate_builtin_corpus(self, corpus: BuiltinCorpus = BuiltinCorpus.baseline) -> EvaluationReport:
        """Measure fixed synthetic references locally without creating analysis records."""
        return evaluate_corpus(load_builtin_corpus(corpus))

    def scan_local_file(self, relative_path: str, *, root: Path | None = None) -> LocalScanReport:
        """Inspect one file relative to the caller's authorized local root; do not persist it."""
        return scan_local_file(Path.cwd() if root is None else root, relative_path)

    def create_local_scan(self, relative_path: str, *, root: Path | None = None) -> ScanCase:
        return self._repository.save_local_scan(self.scan_local_file(relative_path, root=root))

    def create_source_scan(self, label: str, content: bytes) -> ScanCase:
        return self._repository.save_local_scan(scan_source_bytes(label, content))

    def get_local_scan(self, analysis_id: str, revision: int | None = None) -> ScanCase | None:
        return self._repository.get_local_scan(analysis_id, revision)

    def list_local_scans(self, *, limit: int = 25, offset: int = 0) -> list[ScanCase]:
        return self._repository.list_local_scans(limit=limit, offset=offset)

    def answer_local_scan(self, analysis_id: str, request: MonitorAnswerRequest) -> ScanAnswerReceipt:
        return self._repository.answer_local_scan(analysis_id, request)

    def trace_source_bytes(self, analysis_id: str, content: bytes,
                           submission_id: UUID) -> ArgumentInvestigationReceipt:
        case = self.get_local_scan(analysis_id)
        if case is None:
            raise LookupError("local_scan_not_found")
        original_lineage_bytes(case.report, content)
        require_corroboration(case.source_review)
        previous = self._repository.get_argument_receipt(submission_id)
        if previous is not None:
            if previous.analysis_id != analysis_id:
                raise LineageError("lineage_submission_conflict")
            return previous
        if case.argument_investigation is not None:
            raise LineageError("lineage_already_recorded")
        investigation = investigate_argument(case.report, content, case.source_review)
        return self._repository.save_argument_investigation(analysis_id, submission_id, investigation)

    def trace_local_source(self, analysis_id: str, relative_path: str,
                           submission_id: UUID, *, root: Path | None = None) -> ArgumentInvestigationReceipt:
        _, content = load_local_source(Path.cwd() if root is None else root, relative_path)
        return self.trace_source_bytes(analysis_id, content, submission_id)

    def review_source_bytes(self, analysis_id: str, content: bytes,
                            submission_id: UUID) -> SourceReviewReceipt:
        case = self.get_local_scan(analysis_id)
        if case is None:
            raise LookupError("local_scan_not_found")
        ensure_original_bytes(case.report, content)
        previous = self._repository.get_source_review_receipt(submission_id)
        if previous is not None:
            if previous.analysis_id != analysis_id:
                raise SourceReviewError("source_review_submission_conflict")
            return previous
        if case.source_review is not None:
            raise SourceReviewError("source_review_already_recorded")
        review = review_original_source(case.report, content)
        return self._repository.save_source_review(analysis_id, submission_id, review)

    def review_local_source(self, analysis_id: str, relative_path: str,
                            submission_id: UUID, *, root: Path | None = None) -> SourceReviewReceipt:
        _, content = load_local_source(Path.cwd() if root is None else root, relative_path)
        return self.review_source_bytes(analysis_id, content, submission_id)

    def create_demo_analysis(self) -> AnalysisReport:
        report = self._build_demo_report(Analysis())
        self._repository.save_report(report)
        return report

    @staticmethod
    def _build_demo_report(analysis: Analysis) -> AnalysisReport:
        evidence = Evidence(
            id=EVIDENCE_ID,
            kind="demo_fixture",
            description=EVIDENCE_DESCRIPTION,
            source="sentinelforge://fixtures/demo",
        )
        report = AnalysisReport(
            analysis=analysis,
            findings=[
                Finding(
                    id=FINDING_ID,
                    title=FINDING_TITLE,
                    description=FINDING_DESCRIPTION,
                    evidence_ids=[evidence.id],
                )
            ],
            evidence=[evidence],
            human_statements=[
                HumanStatement(
                    id=STATEMENT_ID,
                    question=STATEMENT_QUESTION,
                    text=STATEMENT_TEXT,
                    actor="demo-user",
                    role="developer",
                    created_at=analysis.created_at,
                    effect=STATEMENT_EFFECT,
                )
            ],
            limitations=list(LIMITATIONS),
        )
        return report

    def create_demo_workflow(
        self, fixture_id: DemoFixtureId = "auth-disabled", *, monitored: bool = False
    ) -> WorkflowCheckpoint:
        request = SimulationStartRequest(fixture_id=fixture_id, monitored=monitored)
        checkpoint = WorkflowCheckpoint()
        self._repository.create_workflow(
            checkpoint, simulation=SimulationTrace(fixture_id=request.fixture_id),
            monitored=request.monitored,
        )
        return checkpoint

    def get_monitor_questions(self, analysis_id: str) -> list[MonitorQuestion]:
        return self._repository.get_monitor_questions(analysis_id)

    def answer_monitor_question(
        self, analysis_id: str, question_id: str, request: MonitorAnswerRequest
    ) -> MonitorAnswerReceipt:
        return self._repository.answer_monitor_question(analysis_id, question_id, request)

    def get_simulation(
        self, analysis_id: str, *, checkpoint_version: int | None = None
    ) -> SimulationTrace | None:
        return self._repository.get_simulation(analysis_id, checkpoint_version=checkpoint_version)

    def get_workflow(self, analysis_id: str) -> WorkflowCheckpoint | None:
        return self._repository.get_workflow(analysis_id)

    def advance_demo_workflow(
        self, analysis_id: str, *, expected_version: int
    ) -> WorkflowCheckpoint:
        checkpoint = self.get_workflow(analysis_id)
        final_report = None
        if checkpoint is not None:
            final_report = self._build_demo_report(
                Analysis(id=analysis_id, created_at=checkpoint.created_at)
            )
        return self._repository.advance_workflow(
            analysis_id, expected_version=expected_version, final_report=final_report
        )

    def get_report(self, analysis_id: str) -> AnalysisReport | None:
        return self._repository.get_report(analysis_id)

    def get_revision(
        self, analysis_id: str, revision: int | None = None
    ) -> ReportRevision | None:
        return self._repository.get_revision(analysis_id, revision)

    def add_demo_limitation(
        self, analysis_id: str, *, expected_revision: int, limitation: str
    ) -> ReportRevision:
        # Build from the requested snapshot so a retry produces identical content.
        snapshot = self.get_revision(analysis_id, expected_revision)
        if snapshot is None:
            if self.get_revision(analysis_id) is None:
                raise LookupError("analysis_not_found")
            raise ReportConflictError("report_revision_conflict")
        report = snapshot.report.model_copy(deep=True)
        report.limitations.append(limitation)
        revision = self.append_report_revision(report, expected_revision=expected_revision)
        return ReportRevision(revision=revision, report=report)

    def append_report_revision(
        self,
        report: AnalysisReport,
        *,
        expected_revision: int,
    ) -> int:
        return self._repository.append_report_revision(
            report,
            expected_revision=expected_revision,
        )
