# Ciclo de demostración con recuperación

## Problema y vocabulario

Hasta ahora se recuperaban reportes terminados. Faltaba conservar el progreso de un análisis entre llamadas. Un **checkpoint** es una instantánea recuperable del progreso; la **máquina de estados** define qué paso puede seguir al actual.

Esta entrega cierra esa parte de la persistencia antes de incorporar investigadores y verificadores simulados. Las fases solo registran progreso: todavía no hacen detección, investigación ni verificación técnica.

La [capa posterior de investigación simulada](09_INVESTIGACION_SIMULADA.md) añade resultados a los ciclos nuevos y migra el esquema a 3. Los ciclos anteriores mantienen el comportamiento descrito en esta entrega.

```text
RECEIVED → DETECTING → INVESTIGATING → VERIFYING → REPORTING → COMPLETED
versión 1       2             3              4           5             6
```

## Diseño

`workflow.py` define el contrato versionado del checkpoint y la transición pura de una fase. `AnalysisService` sigue siendo el servicio compartido; el repositorio SQLite guarda cada versión inmutable en `workflow_checkpoints` y un evento separado en `analysis_events`.

La transición final guarda el checkpoint `COMPLETED`, el reporte sintético y sus eventos en la misma transacción. Si algo falla, todos esos cambios se revierten. Las evidencias siguen marcadas como simuladas y las declaraciones humanas como `unverified`.

Cada llamada avanza como máximo un paso y exige `expected_version`. Si se repite una solicitud ya aplicada, se devuelve su resultado histórico, aunque el ciclo haya avanzado más. Consultar el estado devuelve siempre la última versión. Una versión futura produce conflicto; un ciclo completado no genera más eventos al reintentarlo.

No hay trabajo en segundo plano ni un proceso que deba quedar vivo: basta con dejar de avanzar para detenerse entre fases y volver a consultar/avanzar después de reiniciar. Esto no pausa una herramienta en mitad de su ejecución ni constituye todavía un checkpoint de LangGraph.

## API local

| Método y ruta | Resultado |
|---|---|
| `POST /v1/demo-workflows` | 201 con un nuevo checkpoint `RECEIVED` |
| `GET /v1/demo-workflows/{analysis_id}` | Último checkpoint, o 404 |
| `POST /v1/demo-workflows/{analysis_id}/advance` | Avanza o reproduce un resultado previo |

Cuerpo de avance:

```json
{"expected_version": 1}
```

Errores: 404 `workflow_not_found`, 409 `workflow_version_conflict`, 422 para entradas inválidas. La versión es un entero positivo estricto: se rechazan booleanos, cadenas y campos extra. No se acepta un estado de destino arbitrario.

Al completar el ciclo, el mismo ID permite consultar el reporte con `GET /v1/analyses/{analysis_id}/reports/latest` o abrirlo en la web existente. Antes del final, esas rutas de reporte retornan 404. La página web todavía no tiene controles para avanzar el ciclo; se usan CLI o Swagger local.

## Ejemplo PowerShell

Cada comando usa el entorno ya existente del repositorio. Puede elegirse una base de desarrollo separada en esa sesión:

```powershell
$env:SENTINELFORGE_DATABASE_PATH = ".local\ciclo-demo.sqlite3"
$inicio = .\.venv\Scripts\python.exe -m sentinelforge.cli workflow-start | ConvertFrom-Json
$analysisId = $inicio.analysis_id
.\.venv\Scripts\python.exe -m sentinelforge.cli workflow-advance $analysisId --expected-version 1
.\.venv\Scripts\python.exe -m sentinelforge.cli workflow-status $analysisId
```

Se puede cerrar esa terminal y abrir otra conservando la misma ruta de base e ID. Para terminar, avanzar con las versiones 2, 3, 4 y 5. La versión de checkpoint y la revisión de reporte son contadores distintos: al completar el checkpoint 6 se publica la revisión de reporte 1.

Los comandos son no interactivos. Un error de búsqueda o versión sale con código 2 y mensaje en stderr; éxito devuelve JSON y código 0.

## Migración y entradas

El esquema SQLite pasa de 1 a 2 mediante una migración aditiva transaccional al abrir la base. Conserva reportes/eventos existentes y crea la tabla de checkpoints con triggers que bloquean actualización y borrado. Las versiones futuras desconocidas se rechazan. Esto es una migración de desarrollo; producción seguirá necesitando respaldos, estrategia de despliegue y PostgreSQL.

Los nuevos endpoints solo reciben una versión y un ID usado mediante parámetros SQL. No reciben archivos, código ni prompts. Los checkpoints no autentican al usuario y los triggers no impiden que un administrador altere el archivo de base directamente. La API debe permanecer local.

## Verificación y aprendizaje

Las pruebas cubren contratos, secuencia, reinicio entre instancias, reintentos tardíos, concurrencia, migración y rollback de un fallo inyectado durante la publicación final. El comando general es:

Resultado local del 20 de noviembre de 2026: **46 pruebas aprobadas y Ruff limpio**, con Python 3.14.10 de `.venv`. Incluye la recuperación entre procesos Python reales y ocho avances finales simultáneos que producen un solo reporte. Esta capa todavía no se ha publicado ni ejecutado en CI remota.

Comprobación adicional con Uvicorn local: crear un ciclo, avanzar a `DETECTING` versión 2, detener el servidor, levantarlo otra vez, recuperar el mismo checkpoint y continuar hasta `COMPLETED` versión 6. La base real migró de 1 a 2; se conservó una copia local previa y se comprobó que sus ocho filas de reportes permanecieran intactas tras agregar el nuevo reporte.

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
```

Preguntas de repaso: ¿qué guarda un checkpoint que no guarda un reporte final? ¿Por qué completar y publicar deben compartir transacción? ¿Por qué un reintento antiguo devuelve un checkpoint histórico? ¿Qué falta para ejecutar una investigación real dentro de una fase?
