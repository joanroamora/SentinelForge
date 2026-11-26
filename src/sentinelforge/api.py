"""FastAPI adapter over the shared AnalysisService."""

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import UUID

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi import Path as PathParameter
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from . import __version__
from .argument_lineage import ArgumentInvestigationReceipt, LineageError
from .contracts import AnalysisReport, DemoRevisionRequest, ReportRevision
from .local_source import MAX_SOURCE_BYTES, LocalSourceError, normalize_source_label
from .monitor import (
    MonitorAnswerReceipt,
    MonitorAnswerRequest,
    MonitorConflictError,
    MonitorQuestion,
)
from .repository import ReportConflictError
from .scan_case import ScanAnswerReceipt, ScanCase
from .service import AnalysisService
from .simulation import SimulationStartRequest, SimulationTrace
from .source_review import SourceReviewError, SourceReviewReceipt
from .web import WEB_PAGE
from .workflow import WorkflowAdvanceRequest, WorkflowCheckpoint, WorkflowConflictError


def create_app(
    service: AnalysisService | None = None,
    *,
    database_path: str | Path | None = None,
) -> FastAPI:
    app = FastAPI(title="SentinelForge · Local workspace", version=__version__)
    app.state.analysis_service = service or AnalysisService(database_path)
    app.mount("/assets", StaticFiles(directory=Path(__file__).with_name("static")), name="assets")
    scanner_slots = asyncio.Semaphore(2)

    @asynccontextmanager
    async def artifact_input(request: Request):
        if request.headers.get("content-type", "").split(";")[0] != "application/octet-stream":
            raise HTTPException(status_code=415, detail="expected_octet_stream")
        origin = request.headers.get("origin")
        if origin and origin != str(request.base_url).rstrip("/"):
            raise HTTPException(status_code=403, detail="origin_not_allowed")
        if scanner_slots.locked():
            raise HTTPException(status_code=503, detail="scanner_busy")
        async with scanner_slots:
            content = bytearray()
            async for chunk in request.stream():
                if len(content) + len(chunk) > MAX_SOURCE_BYTES:
                    raise HTTPException(status_code=413, detail="source_too_large")
                content.extend(chunk)
            yield bytes(content)

    @app.post("/v1/local-scans", response_model=ScanCase)
    async def scan_upload(request: Request, filename: str = Query(max_length=1024)) -> ScanCase:
        try:
            label = normalize_source_label(filename)
        except LocalSourceError as error:
            raise HTTPException(status_code=422, detail=error.code) from error
        async with artifact_input(request) as content:
            return await run_in_threadpool(
                app.state.analysis_service.create_source_scan, label, bytes(content)
            )

    @app.post("/v1/local-scans/{analysis_id}/verify", response_model=SourceReviewReceipt)
    async def scan_verify(analysis_id: str, request: Request, submission_id: UUID) -> SourceReviewReceipt:
        async with artifact_input(request) as content:
            try:
                return await run_in_threadpool(app.state.analysis_service.review_source_bytes,
                                              analysis_id, content, submission_id)
            except LookupError as error:
                raise HTTPException(status_code=404, detail="local_scan_not_found") from error
            except SourceReviewError as error:
                raise HTTPException(status_code=error.http_status, detail=str(error)) from error

    @app.post("/v1/local-scans/{analysis_id}/trace", response_model=ArgumentInvestigationReceipt)
    async def scan_trace(analysis_id: str, request: Request,
                         submission_id: UUID) -> ArgumentInvestigationReceipt:
        async with artifact_input(request) as content:
            try:
                return await run_in_threadpool(app.state.analysis_service.trace_source_bytes,
                                              analysis_id, content, submission_id)
            except LookupError as error:
                raise HTTPException(status_code=404, detail="local_scan_not_found") from error
            except LineageError as error:
                raise HTTPException(status_code=error.http_status, detail=str(error)) from error

    @app.get("/v1/local-scans", response_model=list[ScanCase])
    def scan_history(limit: int = Query(default=25, ge=1, le=100),
                     offset: int = Query(default=0, ge=0)) -> list[ScanCase]:
        return app.state.analysis_service.list_local_scans(limit=limit, offset=offset)

    @app.get("/v1/local-scans/{analysis_id}", response_model=ScanCase)
    def scan_detail(analysis_id: str, revision: int | None = Query(default=None, ge=1)) -> ScanCase:
        case = app.state.analysis_service.get_local_scan(analysis_id, revision)
        if case is None:
            raise HTTPException(status_code=404, detail="local_scan_not_found")
        return case

    @app.post("/v1/local-scans/{analysis_id}/answers", response_model=ScanAnswerReceipt)
    def scan_answer(analysis_id: str, request: MonitorAnswerRequest) -> ScanAnswerReceipt:
        try:
            return app.state.analysis_service.answer_local_scan(analysis_id, request)
        except LookupError as error:
            raise HTTPException(status_code=404, detail="scan_question_not_found") from error
        except MonitorConflictError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

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
