"""Application service shared by the CLI and HTTP adapter."""

from .contracts import Analysis, AnalysisReport, Evidence, Finding, HumanStatement
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


class AnalysisService:
    """Creates and retrieves a synthetic demo report; it does not scan code."""

    def __init__(self) -> None:
        self._reports: dict[str, AnalysisReport] = {}

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
        self._reports[report.analysis.id] = report
        return report

    def get_report(self, analysis_id: str) -> AnalysisReport | None:
        return self._reports.get(analysis_id)
