# Expedientes reales, workspace web y CLI visual

## Problema y vocabulario

El detector anterior devolvía un JSON efímero por terminal. Esta capa lo convierte en un **expediente** recuperable: resultado técnico original, pregunta de contexto y revisiones inmutables. La web y la CLI presentan ese mismo expediente usando `AnalysisService`.

Un proceso de detección terminado no equivale a software seguro. `LocalScanReport.status` indica si el detector terminó; `ScanCase.status` indica si el expediente conserva asuntos pendientes. Una señal produce un expediente `PARTIAL`, incluso después de recibir una respuesta humana sin verificar. Un fallo técnico produce `ERROR`, nunca un resultado exitoso sin señales.

## Datos e idempotencia

`ScanCase` tiene contrato `1.0`, `report_type=local_scan_case` e `is_demo=false`. Contiene `LocalScanReport`, ID, fecha UTC de creación, número de revisión, pregunta y declaraciones humanas. No amplía los contratos ficticios de la demo.

El ID `scan-<fingerprint>` depende del contenido, nombre relativo, regla, versión de detector y Python. Repetir la misma entrada devuelve el expediente existente en su última revisión; no agrega eventos ni revisiones duplicadas. El detector vuelve a procesar los bytes antes de comparar el resultado, por lo que esta idempotencia no es una caché de ejecución. Cambiar el nombre o contenido crea otro expediente.

La migración SQLite 4→5 añade `local_scan_revisions` y `local_scan_submissions`. Ambas tablas rechazan `UPDATE` y `DELETE`; cada escritura y sus eventos se confirman juntos. Las tablas de reportes, checkpoints y Monitor demo se conservan sin transformar su contenido.

Cuando hay señales se crea una pregunta para la primera. Se admite una respuesta inmutable con autor/rol declarados, texto, fecha UTC del servidor, pregunta, efecto y estado `unverified`. La respuesta publica la revisión 2 y conserva la 1. `submission_id` es una UUID: un reintento idéntico devuelve el mismo recibo; otra carga con esa clave o reutilizarla en otro expediente genera conflicto. Una segunda respuesta con otra clave también se rechaza. Los fallos revierten respuesta, revisión y eventos.

El código fuente no se conserva en SQLite, archivos de upload ni logs de la aplicación. Se persisten hash, nombre relativo, tamaño, ubicaciones y observaciones. Los aportes humanos sí se guardan: no incluir secretos. La ausencia del código original implica que una futura verificación independiente necesitará recibir otra vez bytes cuyo hash coincida; esta capa no acredita esa verificación.

## API y nueva superficie de entrada

| Operación | Ruta |
|---|---|
| Analizar bytes y guardar | `POST /v1/local-scans?filename=example.py` |
| Historial paginado | `GET /v1/local-scans?limit=25&offset=0` |
| Última revisión | `GET /v1/local-scans/{id}` |
| Revisión histórica | `GET /v1/local-scans/{id}?revision=1` |
| Respuesta humana | `POST /v1/local-scans/{id}/answers` |

El POST de análisis requiere `Content-Type: application/octet-stream`. Recibe bytes del archivo elegido, no una ruta que permita leer el filesystem del servidor. El nombre es únicamente una etiqueta validada; nunca se abre como archivo. Se rechazan traversal, nombres especiales, segmentos ocultos y extensiones distintas de `.py` usando la misma normalización que la CLI.

El cuerpo se lee por streaming y se rechaza al superar 65 536 bytes con 413. Se admiten dos solicitudes simultáneas de upload/análisis; una tercera recibe 503 `scanner_busy`. La API no habilita CORS y rechaza un `Origin` diferente al suyo. Un tipo de contenido distinto produce 415. Una etiqueta inválida produce 422. Un error de sintaxis produce HTTP 200 con expediente `ERROR`, porque el intento y su error se guardaron correctamente.

Se reutiliza el worker AST confiable con `-I -S`, límite de cinco segundos, 20 000 nodos y 100 señales. Ni el código ni sus imports se ejecutan. Los límites y el proceso separado no sustituyen una cuota dura de memoria o un sandbox de permisos. Este entorno continúa siendo local y sin autenticación; no se ha autorizado exposición pública ni procesamiento multiusuario hostil.

## Workspace web

- **Vista general:** contadores y gráfico de estados calculados sobre hasta 25 expedientes recientes; incluye ejemplos controlados. No muestra una puntuación de seguridad ni cifras inventadas.
- **Nuevo análisis:** selección o arrastre de un `.py`, tamaño visible y envío explícito. Los ejemplos usan el detector real sobre texto sintético, identificado por su nombre `example_*`.
- **Expedientes:** historial paginado y búsqueda dentro de la página, estado, señales y contexto recibido/pendiente.
- **Detalle:** ubicaciones, hash, revisiones anterior/siguiente, contexto humano y descarga del JSON de la revisión visible. El contrato completo está plegado para priorizar la lectura.
- **Laboratorio demo:** conserva el recorrido ficticio y sus preguntas anteriores, con identificación explícita.

Los datos no confiables se representan con `textContent` y nodos de texto, nunca `innerHTML`. El diseño usa CSS, tipografías del sistema y gráficos locales, sin CDNs, fuentes remotas ni paquetes frontend. Los assets se distribuyen dentro del paquete Python. Incluye foco visible, estados de carga, mensajes accesibles, adaptación móvil y respeto a movimiento reducido.

El borrador de respuesta vive en la página. Un fallo conserva texto y UUID para reintentar; recargar descarta el borrador no guardado. Un envío ya confirmado se recupera desde SQLite. En revisiones históricas se oculta el formulario y se identifica la revisión. No hay SSE, edición de respuestas ni múltiples preguntas por expediente.

## CLI: personas y automatización

```powershell
.\.venv\Scripts\python.exe -m sentinelforge.cli scan tests/fixtures/local_scan/shell_enabled.py --format pretty
.\.venv\Scripts\python.exe -m sentinelforge.cli scans --format pretty
.\.venv\Scripts\python.exe -m sentinelforge.cli scan-report ID --revision 1 --format json
```

`scan` guarda el expediente; `scan-file` mantiene su comportamiento de lectura y JSON efímero, sin SQLite. `scan-answer ID --submission-id UUID --actor AUTOR --role ROL --text TEXTO` registra contexto sin esperar stdin.

`--format auto` usa la presentación visual en una terminal y JSON ASCII en pipes. `--format json` fuerza el contrato limpio. `--format pretty` fuerza paneles y tablas; se respetan `NO_COLOR` y terminales sin Unicode completo. El parámetro también puede darse antes del comando para las operaciones anteriores de demo: `--format pretty workflow-start`.

La CLI visual usa Rich 15.0.0, que ya estaba presente como dependencia de Typer en `.venv`; ahora se declara su uso directo en `pyproject.toml`. No se ejecutó ninguna instalación. La barra representa bytes usados del límite de entrada, no riesgo o confianza. Los nombres y declaraciones se muestran como texto literal y se filtran caracteres de control para impedir secuencias ANSI/OSC inyectadas; el JSON conserva el original escapado.

Una inspección exitosa, incluso `PARTIAL`, devuelve 0. Los errores técnicos devuelven 2. Un rechazo de entrada sin manifiesto no crea expediente y devuelve un código de error en stderr. No hay gate automático de seguridad para CI.

## Evidencia y aprendizaje

Las pruebas cubren equivalencia CLI/API/servicio, reinicios, reintentos, concurrencia, conflictos, rollback, migración y conservación de tablas anteriores, límites de uploads, rechazo de origen, inmutabilidad, codificación cp1252 y texto manipulador. Los tests de symlinks/FIFO mantienen las limitaciones de plataforma ya documentadas.

Resultado local: **221 pruebas aprobadas, 2 omitidas por capacidades de Windows y Ruff limpio**, usando Python 3.14.10. La suite emitió una advertencia `UnsupportedFieldAttributeWarning` de Pydantic en una prueba concurrente existente; las aserciones de esa prueba pasaron. No se ha ejecutado CI remota de esta capa.

Antes de migrar se respaldó la base real en `.local/backups/`. La comparación posterior verificó que todas las filas anteriores de las seis tablas existentes permanecen intactas, incluidas las 17 revisiones previas de reportes. Los resultados nuevos se guardaron en las tablas del esquema 5.

Los assets están declarados como package data. Se intentó construir un wheel local sin red, sin aislamiento de build y sin instalar dependencias; ese chequeo quedó pendiente porque `setuptools.build_meta` no está disponible en `.venv`. No se instaló para resolverlo. La ejecución desde el repositorio y la entrega de los tres assets por HTTP sí están verificadas. Las vistas exportadas de la CLI están en `.local/product-preview/`, fuera del control de versiones.

En navegador se seleccionó `shell_enabled.py` mediante el selector de archivos, se guardó la señal y una respuesta que contenía `<b>texto literal</b>`. La revisión 2 mantuvo el expediente parcial y la 1 permaneció intacta. Tras reiniciar Uvicorn se recuperaron ambas revisiones y el texto literal. Se comprobó el ejemplo sin coincidencias y el Monitor demo anterior. En 390 px el documento no desbordó horizontalmente y se restauró después el viewport normal.

La siguiente capa requiere investigación y verificación técnica independiente sobre fuentes originales, no convertir la respuesta humana en una decisión confirmada. Preguntas de repaso: ¿por qué un detector terminado puede tener expediente parcial? ¿Qué conserva una revisión? ¿Qué protege la UUID? ¿Por qué el hash no reemplaza la fuente original? ¿Por qué la barra de la CLI no es una medida de seguridad?

Referencia de presentación: [Rich Console API](https://rich.readthedocs.io/en/stable/console.html). Decisión: [ADR 0007](adr/0007-expedientes-reales-y-presentacion.md).
