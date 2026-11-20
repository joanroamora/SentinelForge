"""FastAPI adapter over the shared AnalysisService."""

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi import Path as PathParameter
from fastapi.responses import HTMLResponse

from .contracts import AnalysisReport, DemoRevisionRequest, ReportRevision
from .repository import ReportConflictError
from .service import AnalysisService
from .web import WEB_PAGE


def create_app(
    service: AnalysisService | None = None,
    *,
    database_path: str | Path | None = None,
) -> FastAPI:
    app = FastAPI(title="SentinelForge demo", version="0.1.0")
    app.state.analysis_service = service or AnalysisService(database_path)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "mode": "demo"}

    @app.get("/", response_class=HTMLResponse)
    async def home() -> str:
        return WEB_PAGE

    @app.post("/v1/analyses", response_model=AnalysisReport)
    def create_analysis() -> AnalysisReport:
        return app.state.analysis_service.create_demo_analysis()

    @app.get("/v1/analyses/{analysis_id}", response_model=AnalysisReport)
    def get_analysis(analysis_id: str) -> AnalysisReport:
        report = app.state.analysis_service.get_report(analysis_id)
        if report is None:
            raise HTTPException(status_code=404, detail="analysis_not_found")
        return report

    @app.get(
        "/v1/analyses/{analysis_id}/reports/latest",
        response_model=AnalysisReport,
    )
    def get_latest_report(analysis_id: str) -> AnalysisReport:
        report = app.state.analysis_service.get_report(analysis_id)
        if report is None:
            raise HTTPException(status_code=404, detail="analysis_not_found")
        return report

    @app.get("/v1/analyses/{analysis_id}/report-revisions/latest", response_model=ReportRevision)
    def latest_revision(analysis_id: str) -> ReportRevision:
        result = app.state.analysis_service.get_revision(analysis_id)
        if result is None:
            raise HTTPException(status_code=404, detail="analysis_not_found")
        return result

    @app.get("/v1/analyses/{analysis_id}/reports/{revision}", response_model=ReportRevision)
    def historical_revision(
        analysis_id: str, revision: int = PathParameter(ge=1)
    ) -> ReportRevision:
        result = app.state.analysis_service.get_revision(analysis_id, revision)
        if result is None:
            raise HTTPException(status_code=404, detail="report_revision_not_found")
        return result

    @app.post("/v1/analyses/{analysis_id}/report-revisions", response_model=ReportRevision)
    def revise_demo(analysis_id: str, request: DemoRevisionRequest) -> ReportRevision:
        try:
            return app.state.analysis_service.add_demo_limitation(
                analysis_id,
                expected_revision=request.expected_revision,
                limitation=request.limitation,
            )
        except LookupError as error:
            raise HTTPException(status_code=404, detail="analysis_not_found") from error
        except ReportConflictError as error:
            raise HTTPException(status_code=409, detail="report_revision_conflict") from error

    return app


app = create_app()
