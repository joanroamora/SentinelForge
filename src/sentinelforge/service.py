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


class AnalysisService:
    """Creates and retrieves a synthetic demo report; it does not scan code."""

    def __init__(self, database_path: str | Path | None = None) -> None:
        self._repository = SQLiteReportRepository(database_path)

    def create_demo_analysis(self) -> AnalysisReport:
        evidence = Evidence(
            id=EVIDENCE_ID,
            kind="demo_fixture",
            description=EVIDENCE_DESCRIPTION,
            source="sentinelforge://fixtures/demo",
        )
        report = AnalysisReport(
            analysis=Analysis(),
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
                    effect=STATEMENT_EFFECT,
                )
            ],
            limitations=list(LIMITATIONS),
        )
        self._repository.save_report(report)
        return report

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
