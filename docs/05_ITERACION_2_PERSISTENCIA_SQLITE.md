# Iteración 2 — expediente SQLite local

## Problema y vocabulario

En la primera iteración, un reporte solo existía dentro del proceso. Al cerrar el servidor desaparecía y un reinicio no podía recuperar el análisis. **Persistencia** significa guardar datos fuera de la memoria del proceso. Un **evento append-only** se agrega al historial y la aplicación no lo reemplaza ni lo borra. Una **revisión** guarda una versión inmutable del reporte.

## Diseño

- `AnalysisService` sigue siendo el motor compartido por CLI y API.
- `SQLiteReportRepository` guarda cada reporte como JSON validado por Pydantic.
- `report_revisions` conserva versiones completas. La tabla prohíbe cambios y borrados.
- `analysis_events` registra `report_created` y `report_revision_created`; triggers SQLite rechazan cambios y borrados.
- La ruta predeterminada es `.sentinelforge/analyses.sqlite3`. `SENTINELFORGE_DATABASE_PATH` permite elegir otra ruta local.
- Cada operación abre su propia conexión. SQLite serializa las escrituras breves; no se comparte una conexión entre hilos.

Esta iteración introdujo `PRAGMA user_version = 1`. El [ciclo persistente posterior](08_CICLO_DEMO_PERSISTENTE.md) añade una migración local transaccional de 1 a 2 para guardar checkpoints. Las migraciones y respaldos de producción siguen pendientes.

## Idempotencia y recuperación

Guardar otra vez el mismo JSON con el mismo `analysis_id` no duplica revisión ni evento. Para agregar una versión se indica `expected_revision`: si la versión actual no coincide, se produce `ReportConflictError` y no se pisa el trabajo de otra operación. Un servicio recién creado puede recuperar la revisión más reciente; las anteriores permanecen intactas.

## Pruebas de esta iteración

La suite comprueba la ruta existente de CLI/API, recuperación con una instancia nueva del servicio, escritura idempotente, creación y reintento de revisión 2, rechazo de cambios al reporte/evento y escrituras concurrentes sobre un archivo temporal. Todas las bases de prueba viven en `tmp_path`.

También se verificó el proceso local real: `POST /v1/analyses`, detener y volver a levantar Uvicorn, y consultar el mismo ID con `GET /v1/analyses/{id}`; el reporte reapareció desde SQLite.

## Límites y lo aprendido

- La demo no tiene una ejecución que pueda pausarse; por tanto, todavía no existe reanudación de un grafo. Esta iteración recupera reportes y deja el formato inicial de eventos/revisiones.
- El log no es resistente a un administrador que modifique directamente el archivo o su esquema; los triggers evitan mutaciones accidentales desde la aplicación, no son una firma criptográfica.
- La API no tiene autenticación ni protección por propietario del análisis. Debe permanecer local; no exponerla a una red pública.
- Los eventos y reportes contienen datos sintéticos. No se aceptan artefactos reales ni se ejecuta código.
- PostgreSQL, migraciones de producción, respaldo/retención e idempotency keys HTTP quedan para fases posteriores.

## Cómo comprobarlo

### Revisiones mediante HTTP

Los endpoints existentes siguen devolviendo el reporte directamente. Los nuevos devuelven `ReportRevision` con `schema_version`, `revision` y `report`:

- `GET /v1/analyses/{id}/report-revisions/latest`: última revisión con su número.
- `GET /v1/analyses/{id}/reports/{revision}`: revisión histórica (404 si falta).
- `POST /v1/analyses/{id}/report-revisions`: agrega una limitación de demo:

```json
{"expected_revision": 1, "limitation": "Contexto pendiente de revisión."}
```

La nota admite de 1 a 2000 caracteres y exige texto visible. Solo agrega una limitación; conserva evidencias, hallazgos y declaraciones originales. Es una anotación de demo sin verificación técnica ni atribución humana formal. No reemplaza el futuro protocolo Monitor.

Si otra operación guardó un cambio distinto, retorna `409 report_revision_conflict`. El cliente debe leer la versión actual y decidir cómo incorporar su cambio. Un reintento idéntico de la última escritura devuelve la misma revisión sin duplicar eventos. Un análisis inexistente retorna 404; una entrada inválida retorna 422.

Los handlers nuevos son síncronos para que FastAPI ejecute SQLite fuera del event loop. Número de revisión y contenido se consultan juntos.

Validación: 11 pruebas pasan, incluyendo escritores HTTP concurrentes (200/409), conservación de revisión 1, reintento, entradas inválidas y recuperación en otra instancia. Ruff pasa. Las bases de prueba son temporales; la API continúa siendo de desarrollo local sin autenticación.

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\ruff.exe check .
```

La base local se excluye de Git. Para una sesión de PowerShell se puede elegir una ruta distinta:

```powershell
$env:SENTINELFORGE_DATABASE_PATH = ".local\sentinelforge.sqlite3"
```
