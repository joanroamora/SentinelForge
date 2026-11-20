"""Application service shared by the CLI and HTTP adapter."""

from pathlib import Path

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
from .repository import ReportConflictError, SQLiteReportRepository
from .simulation import DemoFixtureId, SimulationStartRequest, SimulationTrace
from .workflow import WorkflowCheckpoint


class AnalysisService:
    """Creates and retrieves a synthetic demo report; it does not scan code."""

    def __init__(self, database_path: str | Path | None = None) -> None:
        self._repository = SQLiteReportRepository(database_path)

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
        self, fixture_id: DemoFixtureId = "auth-disabled"
    ) -> WorkflowCheckpoint:
        request = SimulationStartRequest(fixture_id=fixture_id)
        checkpoint = WorkflowCheckpoint()
        self._repository.create_workflow(
            checkpoint, simulation=SimulationTrace(fixture_id=request.fixture_id)
        )
        return checkpoint

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
