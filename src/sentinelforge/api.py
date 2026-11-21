"""FastAPI adapter over the shared AnalysisService."""

from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi import Path as PathParameter
from fastapi.responses import HTMLResponse

from .contracts import AnalysisReport, DemoRevisionRequest, ReportRevision
from .monitor import (
    MonitorAnswerReceipt,
    MonitorAnswerRequest,
    MonitorConflictError,
    MonitorQuestion,
)
from .repository import ReportConflictError
from .service import AnalysisService
from .simulation import SimulationStartRequest, SimulationTrace
from .web import WEB_PAGE
from .workflow import WorkflowAdvanceRequest, WorkflowCheckpoint, WorkflowConflictError


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

    @app.post("/v1/demo-workflows", response_model=WorkflowCheckpoint, status_code=201)
    def start_workflow(request: SimulationStartRequest | None = None) -> WorkflowCheckpoint:
        fixture_id = "auth-disabled" if request is None else request.fixture_id
        monitored = False if request is None else request.monitored
        return app.state.analysis_service.create_demo_workflow(
            fixture_id=fixture_id, monitored=monitored
        )

    @app.get("/v1/analyses/{analysis_id}/questions", response_model=list[MonitorQuestion])
    def get_monitor_questions(analysis_id: str) -> list[MonitorQuestion]:
        try:
            return app.state.analysis_service.get_monitor_questions(analysis_id)
        except LookupError as error:
            raise HTTPException(status_code=404, detail="analysis_not_found") from error

    @app.post(
        "/v1/analyses/{analysis_id}/questions/{question_id}/answers",
        response_model=MonitorAnswerReceipt,
    )
    def answer_monitor_question(
        analysis_id: str, question_id: str, request: MonitorAnswerRequest
    ) -> MonitorAnswerReceipt:
        try:
            return app.state.analysis_service.answer_monitor_question(
                analysis_id, question_id, request
            )
        except LookupError as error:
            raise HTTPException(status_code=404, detail="monitor_question_not_found") from error
        except MonitorConflictError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @app.get(
        "/v1/demo-workflows/{analysis_id}/investigation", response_model=SimulationTrace
    )
    def get_investigation(
        analysis_id: str, checkpoint_version: int | None = Query(default=None, ge=1)
    ) -> SimulationTrace:
        simulation = app.state.analysis_service.get_simulation(
            analysis_id, checkpoint_version=checkpoint_version
        )
        if simulation is None:
            raise HTTPException(status_code=404, detail="simulation_not_found")
        return simulation

    @app.get("/v1/demo-workflows/{analysis_id}", response_model=WorkflowCheckpoint)
    def get_workflow(analysis_id: str) -> WorkflowCheckpoint:
        checkpoint = app.state.analysis_service.get_workflow(analysis_id)
        if checkpoint is None:
            raise HTTPException(status_code=404, detail="workflow_not_found")
        return checkpoint

    @app.post("/v1/demo-workflows/{analysis_id}/advance", response_model=WorkflowCheckpoint)
    def advance_workflow(
        analysis_id: str, request: WorkflowAdvanceRequest
    ) -> WorkflowCheckpoint:
        try:
            return app.state.analysis_service.advance_demo_workflow(
                analysis_id, expected_version=request.expected_version
            )
        except LookupError as error:
            raise HTTPException(status_code=404, detail="workflow_not_found") from error
        except WorkflowConflictError as error:
            raise HTTPException(status_code=409, detail="workflow_version_conflict") from error

    return app


app = create_app()
