# Primera tarea para Codex — SentinelForge AI

Lee primero `AGENTS.md`, `README.md` y `docs/01_PRODUCTO_Y_REQUISITOS.md`, `docs/02_ARQUITECTURA_Y_CONTRATOS.md`, `docs/03_ROADMAP_ACADEMICO.md`. Inspecciona el repositorio antes de modificar nada; no sobrescribas archivos preexistentes sin mostrarme un plan.

**Implementa solamente la Iteración 1 descrita en el roadmap.** Queremos un vertical slice pedagógico de CLI + FastAPI + web mínima servido todo desde Python, compartiendo `AnalysisService`. Construye una demo **explícitamente ficticia**, sin afirmar haber analizado vulnerabilidades reales.

Restricción absoluta: paquetes Python solo en `.venv`. Usa el intérprete de `.venv` para instalar/ejecutar. Si el entorno no existe, proponme comandos locales para crearlo; no instales globalmente y no ejecutes instalaciones del sistema. No uses Node ni Docker en esta fase. No necesites credenciales LLM ni internet aparte de instalar paquetes autorizados en venv. No ejecutes el artefacto del usuario ni pruebas de red.

Contratos de datos Pydantic: `Analysis`, `Finding`, `Evidence`, `HumanStatement`, `AnalysisReport`. Usa IDs, estados claros y campos de procedencia. La declaración humana debe aparecer en el informe y quedar marcada como `unverified`; reporta con precisión qué verificaciones son simuladas.

Entregables: estructura de paquete, `pyproject.toml` con grupo `dev`, `.gitignore`, CLI, API, web HTML básica, fixture, pruebas pytest, documentación de comandos para Windows PowerShell y Linux/macOS y explicación académica de clases, interfaces y tests.

**Detente tras la primera iteración** y muéstrame: árbol de archivos, comandos para correr, pruebas ejecutadas (o razón por la que no), limitaciones actuales y tres preguntas para validar mi comprensión.
