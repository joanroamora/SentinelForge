# SentinelForge AI

**Multi-Agent Security Analysis Platform**  
**Estado:** workspace local con detector Python acotado por CLI/API/web, expedientes SQLite versionados y contexto humano sin verificar. Incluye una demo simulada identificada y una CLI visual con salida JSON para automatización.

## Misión

SentinelForge AI analiza artefactos de software autorizados (código, dependencias, Docker e infraestructura como código), investiga hallazgos con subagentes especializados, efectúa verificaciones independientes y produce informes auditables. El producto se usa desde:

- **CLI local / CI-CD / runners:** ejecución no interactiva, reporte en JSON y SARIF; opcionalmente envía el análisis al servidor.
- **API HTTP:** entrada común para artefactos, eventos, preguntas, aportes humanos e informes.
- **Interfaz web:** panel de análisis, revisión de evidencias y diálogo con el modo Monitor.

Las tres interfaces **comparten modelos, reglas de negocio y motor de análisis**; no implementan tres motores distintos.

## Principios de producto

1. **Evidencia antes que opinión:** los agentes no inventan pruebas de explotabilidad.
2. **Los aportes humanos pertenecen al informe:** se almacenan y citan como declaraciones del usuario, con autoría, fecha, contenido y estado de verificación. Su inclusión no implica verificación automática.
3. **Falsos positivos y negativos medibles:** el objetivo no es suprimir alertas, sino priorizarlas y justificar cada decisión.
4. **No ejecutar artefactos no confiables** sin una infraestructura de aislamiento específica, aprobada y probada.
5. **Offline-first para el núcleo local:** el MVP puede funcionar con un analizador ficticio/determinista y sin API keys. Servicios LLM y escáneres reales se agregan por adaptadores controlados.
6. **Sin instalaciones globales de paquetes Python:** usar siempre `.venv` y el intérprete de ese entorno.

## Alcance inicial del MVP

Un flujo vertical demostrable: un proyecto Python de prueba es recibido por CLI o API; se genera una señal de hallazgo de una fixture controlada; el orquestador solicita evidencia a subagentes de investigación y verificación; se formula una pregunta humana; la respuesta queda registrada, afecta la evaluación de contexto sin convertirse automáticamente en prueba; se emite un reporte con evidencias y limitaciones.

**Fuera del MVP:** escaneo activo no autorizado, ejecución de código de terceros, autenticación empresarial completa, Kubernetes, certificación de que una aplicación es segura, remediación automática y biometría real.

## Documentación

- [Visión del producto](docs/01_PRODUCTO_Y_REQUISITOS.md)
- [Arquitectura y contratos](docs/02_ARQUITECTURA_Y_CONTRATOS.md)
- [Roadmap académico](docs/03_ROADMAP_ACADEMICO.md)
- [Iteración 1: vertical slice de demostración](docs/04_ITERACION_1_VERTICAL_SLICE.md)
- [Iteración 2: expediente SQLite local](docs/05_ITERACION_2_PERSISTENCIA_SQLITE.md)
- [Consultar y editar el historial desde la web](docs/06_HISTORIAL_WEB.md)
- [Confiabilidad HTTP y CI](docs/07_CONFIABILIDAD_HTTP_Y_CI.md)
- [Ciclo simulado persistente: estados y recuperación](docs/08_CICLO_DEMO_PERSISTENTE.md)
- [Investigación y verificación simuladas](docs/09_INVESTIGACION_SIMULADA.md)
- [Monitor mínimo persistente](docs/10_MONITOR_PERSISTENTE.md)
- [Primer detector Python local](docs/11_DETECTOR_PYTHON_LOCAL.md)
- [Expedientes reales, workspace y CLI visual](docs/12_EXPEDIENTES_Y_WORKSPACE.md)
- [ADR 0007: expedientes y presentación](docs/adr/0007-expedientes-reales-y-presentacion.md)
- [ADR 0006: detector local y contrato separado](docs/adr/0006-detector-python-local.md)
- [ADR 0005: Monitor y respuestas inmutables](docs/adr/0005-monitor-minimo-persistente.md)
- [ADR 0004: roles simulados y trazas](docs/adr/0004-roles-simulados-y-trazas.md)
- [ADR 0001: persistencia local con SQLite](docs/adr/0001-persistencia-sqlite-local.md)
- [Mapa visual del estado actual](docs/diagrams/estado-actual.svg)
- [Reglas permanentes para Codex](AGENTS.md)
- [Primer encargo para Codex](prompts/01_PRIMERA_ITERACION_CODEX.md)

## Inspeccionar un archivo Python local

Con el entorno existente, desde la raíz de trabajo actual:

```powershell
.\.venv\Scripts\python.exe -m sentinelforge.cli scan-file tests/fixtures/local_scan/shell_enabled.py
```

`scan-file` lee un `.py` relativo de hasta 64 KiB y observa llamadas reconocidas a `subprocess` con `shell=True` literal. No importa ni ejecuta el archivo. Devuelve hash, ubicación y señales sin verificar; no demuestra explotabilidad ni garantiza seguridad cuando no encuentra coincidencias. No guarda el resultado en SQLite. Consulta [alcance, errores y límites](docs/11_DETECTOR_PYTHON_LOCAL.md).

Para guardar el expediente y consultarlo en la web local:

```powershell
.\.venv\Scripts\python.exe -m sentinelforge.cli scan tests/fixtures/local_scan/shell_enabled.py --format pretty
.\.venv\Scripts\python.exe -m sentinelforge.cli scans --format pretty
```

La web acepta un archivo elegido por el usuario, conserva resultados y contexto humano y descarta el código fuente tras procesarlo. La CLI usa tablas en terminales y JSON en pipes; `--format json` lo fuerza explícitamente. Más detalles en [workspace y expedientes](docs/12_EXPEDIENTES_Y_WORKSPACE.md).

Para ver el emblema **SF 3D** girando sobre su eje vertical:

```powershell
.\.venv\Scripts\python.exe -m sentinelforge.cli logo --seconds 6 --format pretty
```

La animación aparece brevemente en los resultados visuales. `--no-animation` antes del comando la desactiva; pipes y JSON mantienen su salida sin animación.

## Ejecutar la demo local

La demo crea un reporte sintético para comprobar que CLI y API comparten el mismo motor. No analiza ni ejecuta código, y no afirma detectar vulnerabilidades.

### Windows PowerShell

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\sentinelforge.exe demo
.\.venv\Scripts\python.exe -m uvicorn sentinelforge.api:app --reload
```

Los análisis se guardan en `.sentinelforge/analyses.sqlite3` y sobreviven al reinicio. Para cambiar la ruta solo en esa sesión de PowerShell:

```powershell
$env:SENTINELFORGE_DATABASE_PATH = ".local\sentinelforge.sqlite3"
```

### Linux / macOS

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install -e '.[dev]'
./.venv/bin/python -m pytest
./.venv/bin/sentinelforge demo
./.venv/bin/python -m uvicorn sentinelforge.api:app --reload
```

Los análisis se guardan en `.sentinelforge/analyses.sqlite3`. Para cambiar la ruta en esa sesión:

```bash
export SENTINELFORGE_DATABASE_PATH=.local/sentinelforge.sqlite3
```

La web queda en `http://127.0.0.1:8000/` y la documentación HTTP en `http://127.0.0.1:8000/docs`.

El [ciclo simulado persistente](docs/08_CICLO_DEMO_PERSISTENTE.md) permite iniciar, consultar y avanzar fases desde CLI/API, recuperando el progreso tras reiniciar. Sus fases son marcadores de demostración; el reporte se publica al completar el ciclo.

Detalles: [vertical slice](docs/04_ITERACION_1_VERTICAL_SLICE.md) y [persistencia local](docs/05_ITERACION_2_PERSISTENCIA_SQLITE.md).

No ejecutar `pip install` ni herramientas Python fuera de `.venv`. No hace falta activar el entorno si se invocan sus binarios mediante rutas explícitas. La explicación de clases, pruebas y límites está en `docs/04_ITERACION_1_VERTICAL_SLICE.md`.
