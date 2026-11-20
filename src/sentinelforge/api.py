"""FastAPI adapter over the shared AnalysisService."""

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse

from .contracts import AnalysisReport
from .service import AnalysisService

WEB_PAGE = """<!doctype html>
<html lang="es">
  <head><meta charset="utf-8"><title>SentinelForge — demo</title></head>
  <body>
    <main>
      <h1>SentinelForge</h1>
      <p>Demo ficticia. No analiza ni ejecuta código.</p>
      <button id="run">Crear análisis de demostración</button>
      <pre id="result" aria-live="polite"></pre>
    </main>
    <script>
      document.querySelector("#run").addEventListener("click", async () => {
        const response = await fetch("/v1/analyses", { method: "POST" });
        document.querySelector("#result").textContent =
          JSON.stringify(await response.json(), null, 2);
      });
    </script>
  </body>
</html>"""


def create_app(service: AnalysisService | None = None) -> FastAPI:
    app = FastAPI(title="SentinelForge demo", version="0.1.0")
    app.state.analysis_service = service or AnalysisService()

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "mode": "demo"}

    @app.get("/", response_class=HTMLResponse)
    async def home() -> str:
        return WEB_PAGE

    @app.post("/v1/analyses", response_model=AnalysisReport)
    async def create_analysis() -> AnalysisReport:
        return app.state.analysis_service.create_demo_analysis()

    @app.get("/v1/analyses/{analysis_id}", response_model=AnalysisReport)
    async def get_analysis(analysis_id: str) -> AnalysisReport:
        report = app.state.analysis_service.get_report(analysis_id)
        if report is None:
            raise HTTPException(status_code=404, detail="analysis_not_found")
        return report

    @app.get(
        "/v1/analyses/{analysis_id}/reports/latest",
        response_model=AnalysisReport,
    )
    async def get_latest_report(analysis_id: str) -> AnalysisReport:
        report = app.state.analysis_service.get_report(analysis_id)
        if report is None:
            raise HTTPException(status_code=404, detail="analysis_not_found")
        return report

    return app


app = create_app()
