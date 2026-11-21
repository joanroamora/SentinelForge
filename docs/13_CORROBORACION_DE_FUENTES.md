# Corroboración estática con la fuente original

## Problema y vocabulario

Una señal de un detector es una observación que necesita contraste. Esta capa permite aportar de nuevo el archivo original y revisar las señales ya guardadas con una implementación separada. **Corroborar el patrón** significa comprobar su ubicación, import y argumento literal; no confirma una vulnerabilidad ni la veracidad de una declaración humana.

Primero se compara el SHA-256 de los bytes recibidos con el manifiesto original. Un archivo modificado se rechaza antes de iniciar el parser y no cambia el expediente. El nombre puede ser diferente: lo que debe coincidir son los bytes, incluidos BOM y finales de línea.

## Diseño y alcance

`AnalysisService.review_source_bytes` y `review_local_source` son las entradas comunes para API/web y CLI. El proceso confiable `_review_worker.py`, ejecutado con `-I -S`, no importa ni llama al detector. Relee los bytes aportados, localiza el nodo exacto y contrasta tres aspectos:

1. Línea/columna inicial y final, contando offsets UTF-8 de base 1.
2. Import declarado de `subprocess`, incluidos alias admitidos, usando imports originales y tablas de símbolos del compilador para rechazar vínculos ambiguos.
3. La llamada esperada y el token literal `True` del argumento `shell`, mediante AST y tokenización.

Solo se revisan señales existentes de `SF-PY-001`; no se buscan nuevas. El worker recibe código como datos, sin ejecutarlo. El parser y la biblioteca estándar de Python son compartidos con el detector: hay separación de implementación/proceso, no independencia formal frente a todos los errores de esas herramientas. Tampoco se resuelve qué archivo real se importaría en ejecución ni se rastrea el flujo de los argumentos.

| Resultado | Qué demuestra |
|---|---|
| `pattern_reproduced` | El patrón reportado se observó en la ubicación original dentro de este alcance estático |
| `not_reproduced` | La ubicación, llamada o literal no respalda la observación reportada |
| `inconclusive` | No se pudo establecer el vínculo del nombre importado con suficiente claridad |

No reproducir un patrón no certifica seguridad ni clasifica automáticamente un falso positivo. Si falla el proceso, el parser o un límite técnico, se devuelve un error y no se guarda una decisión de seguridad.

## Contratos, revisiones y recuperación

Las revisiones anteriores conservan `ScanCase` versión `1.0` y su JSON no recibe un campo nuevo retrospectivo. Una corroboración crea la siguiente revisión con versión `1.1` y `source_review`: componente/verificador y versión, Python usado, fecha UTC, SHA-256, decisiones referenciadas por fingerprint y limitaciones.

El reporte técnico original, las preguntas y las declaraciones humanas se conservan. El expediente con señales permanece `PARTIAL`; las señales y declaraciones siguen `unverified`. La nueva observación vive separada y su alcance explícito es `static_pattern_only`.

El esquema SQLite 6 añade `local_scan_verifications` para los recibos inmutables. Revisión, recibo y evento se guardan en una sola transacción, leyendo la última revisión para no perder respuestas humanas concurrentes. Un fallo revierte todo. Se admite una corroboración por expediente en esta entrega.

Cada solicitud usa UUID `submission_id`. Un reintento con la misma clave y archivo devuelve el recibo original, incluso después de otra revisión humana. Reutilizar la clave en otro expediente genera conflicto; otra clave tras una corroboración ya registrada también. Las operaciones rechazadas no añaden revisiones ni recibos. El código aportado se descarta y no se guarda en SQLite ni en logs.

## CLI local

Desde la raíz del repositorio, usando una UUID nueva para el primer envío:

```powershell
$submissionId = [guid]::NewGuid().ToString()
.\.venv\Scripts\python.exe -m sentinelforge.cli scan-verify ID tests/fixtures/local_scan/shell_enabled.py --submission-id $submissionId --format pretty
```

`ID` es el expediente que se desea corroborar. La ruta de archivo sigue la validación local existente: relativa, sin traversal ni enlaces y con límite de 64 KiB. Para reintentar, conservar la misma UUID. La CLI muestra el último expediente completo; el recibo HTTP identifica la revisión original de la operación. La ejecución es no interactiva, devuelve 0 si guardó/recuperó la corroboración y 2 ante error técnico, archivo distinto, conflicto o búsqueda fallida. No cambia las políticas de CI.

## API y web

```http
POST /v1/local-scans/{id}/verify?submission_id=UUID
Content-Type: application/octet-stream

<bytes del archivo original>
```

No recibe rutas del servidor ni decisiones del cliente. Comparte el límite de entrada de 65 536 bytes, el control de `Origin` y los dos slots de upload/análisis del detector. Recibir un archivo no habilita acceso a sus imports ni ejecución.

En la web, abrir un expediente y usar **Corroboración de la fuente → Archivo original para corroborar → Corroborar fuente original**. La última revisión muestra el resultado y permite volver al historial. Las revisiones anteriores no presentan la corroboración como si ya existiera entonces. El fichero y la UUID de un envío fallido se conservan en esa página para reintentar; recargar pierde la selección no enviada.

Errores principales: 409 `source_hash_mismatch`, `source_review_already_recorded` o `source_review_submission_conflict`; 413 por tamaño; 404 por expediente ausente; 422 por UUID o fuente no interpretable; 503 por timeout, worker no disponible o slots ocupados; 502 por fallo o protocolo inválido del worker. Los límites del verificador son cinco segundos, 20 000 nodos y 100 señales. El proceso contiene fallos, pero no es un sandbox de permisos ni impone una cuota dura de memoria.

## Evidencia local y límites

**260 pruebas aprobadas, 2 omitidas por capacidades de Windows y Ruff limpio**, con la `.venv` existente. Los casos nuevos incluyen alias/BOM/CRLF/Unicode, metadatos de escáner incorrectos, archivo cambiado, errores de proceso y protocolo, no ejecución ni copia de fuente, concurrencia entre respuesta y revisión, idempotencia, rollback, migración y equivalencia CLI/API.

Se respaldó la base local antes de migrar de 5 a 6. La comparación confirmó que todas las filas previas de las ocho tablas existentes permanecen intactas. En la web se aportó la fixture original al expediente que ya contenía contexto humano: se publicó revisión 3, permaneció parcial y se recuperó tras reiniciar Uvicorn. La revisión 2 mantuvo su contenido previo. Se verificó el diseño de 390 px sin desbordamiento horizontal. La CLI recuperó la operación con la misma UUID sin añadir revisiones.

No hay nuevas instalaciones, proveedores LLM, escaneos remotos ni publicación. La API permanece local sin autenticación. Siguen pendientes investigación del origen de argumentos, alcanzabilidad, controles reales, evaluación representativa y verificación del contexto humano.

Preguntas de repaso: ¿qué prueba el hash y qué no? ¿Por qué no basta repetir la conclusión del detector? ¿Qué diferencia hay entre patrón reproducido y riesgo confirmado? ¿Por qué el texto humano sigue sin verificar? ¿Cómo se conserva una respuesta que llega mientras se corrobora la fuente?

Referencias: [tablas de símbolos de Python](https://docs.python.org/3.11/library/symtable.html), [tokenización](https://docs.python.org/3.11/library/tokenize.html), [ADR 0008](adr/0008-corroboracion-estatica-de-fuentes.md).
