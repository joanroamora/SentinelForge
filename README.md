# SentinelForge AI

**Multi-Agent Security Analysis Platform**  
**Estado:** workspace local con detector Python acotado, corroboración de la fuente e investigación del origen del comando mediante asignaciones simples en una función, con comprobador separado. Expedientes SQLite versionados y contexto humano sin verificar. Disponible por CLI/API/web, con una demo simulada identificada.

La evaluación local añade 28 casos sintéticos etiquetados y métricas separadas de detección/localización/trazado. El motor 1.2 reconoce imports directos dentro de funciones y distingue parámetros de funciones independientes: localiza 18/19 señales de referencia y conserva una omisión de frontera visible. Las etiquetas son de desarrollo, sin auditoría independiente; no miden seguridad general.

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
- [Corroboración de señales con la fuente original](docs/13_CORROBORACION_DE_FUENTES.md)
- [Origen del comando y comprobación por paso](docs/14_ORIGEN_DEL_COMANDO.md)
- [Evaluación local: corpus, métricas y límites](docs/15_EVALUACION_LOCAL.md)
- [Imports locales: mejora medida y compatibilidad](docs/16_IMPORTS_LOCALES.md)
- [Ámbito de parámetros y guía de capas para empezar](docs/17_AMBITO_DE_PARAMETROS_Y_GUIA.md)
- [ADR 0012: parámetros de funciones independientes](docs/adr/0012-parametros-de-funciones-independientes.md)
- [ADR 0011: imports locales y compatibilidad](docs/adr/0011-imports-locales-y-compatibilidad.md)
- [ADR 0010: corpus y evaluación local](docs/adr/0010-corpus-y-evaluacion-local.md)
- [ADR 0009: origen local del comando](docs/adr/0009-origen-local-del-comando.md)
- [ADR 0008: corroboración estática](docs/adr/0008-corroboracion-estatica-de-fuentes.md)
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

Para corroborar un expediente, usar el archivo original con `scan-verify ID ARCHIVO --submission-id UUID --format pretty` o la sección **Corroboración de la fuente** en la web. Se compara el hash y se revisa el patrón con una implementación separada. El resultado crea una nueva revisión; no confirma explotabilidad ni verifica las declaraciones humanas. Consulta [alcance y ejemplos](docs/13_CORROBORACION_DE_FUENTES.md).

Después de corroborar, `scan-trace ID ARCHIVO --submission-id UUID --format pretty` o **Origen del comando** en la web reconstruye asignaciones simples dentro de una función y contrasta los pasos con otra estrategia. El diagrama y el árbol de terminal distinguen recorridos reproducidos, inconclusos y no reproducidos. Se guardan identificadores y ubicaciones, sin valores literales ni código. Consulta [límites, contrato y ejemplos](docs/14_ORIGEN_DEL_COMANDO.md).

## Ejecutar la demo local

Para medir el motor con las referencias sintéticas incorporadas, sin crear expedientes ni ejecutar las fuentes:

```powershell
.\.venv\Scripts\python.exe -m sentinelforge.cli --no-animation evaluate --format pretty
```

`evaluate --format json` permite conservar y comparar resultados. El código de salida es 0 si coinciden las referencias en alcance, 1 si discrepan y 2 ante error técnico. Las fronteras conocidas se mantienen visibles aunque el gate de regresión pase. Consulta [definiciones y línea base](docs/15_EVALUACION_LOCAL.md).

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
