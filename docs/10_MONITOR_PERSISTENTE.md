# Monitor mínimo persistente

## Problema y vocabulario

Una investigación puede necesitar contexto humano. Ese contexto debe sobrevivir a reinicios y aparecer en el informe sin confundirse con evidencia confirmada. El Monitor de esta entrega plantea una pregunta por análisis y conserva una primera respuesta inmutable.

`monitored=true` activa el modo de forma optativa. El comportamiento predeterminado sigue siendo autónomo. El ciclo mantiene sus seis estados y termina sin esperar entrada interactiva; la pregunta tiene su propio estado `pending` o `answered`.

## Política del informe

El checkpoint puede estar `COMPLETED` porque terminó el recorrido técnico simulado, mientras el informe permanece `PARTIAL` por el contexto pendiente. Recibir una respuesta tampoco elimina la parcialidad: la declaración continúa `unverified` y todavía requiere verificación humana/técnica posterior.

La declaración conserva texto original, autor y rol declarados, fecha UTC del servidor, pregunta y efecto sobre la conclusión. No se verifica la identidad de quien escribe. El verificador vuelve a contrastar la fixture al publicar una revisión, pero no transforma el texto humano en prueba ni modifica por él la conclusión simulada.

## Persistencia e idempotencia

El esquema SQLite 4 añade `monitor_questions` y `monitor_answers`. Sus triggers rechazan cambios y borrados. El estado visible de la pregunta se deriva de su respuesta; la pregunta original no se reescribe.

Cada envío requiere una UUID `submission_id`. Repetir esa UUID con el mismo contenido normalizado devuelve el recibo original sin duplicar la respuesta, los eventos ni el informe. Reutilizarla con otro contenido produce `monitor_submission_conflict`. Una segunda UUID para una pregunta respondida produce `monitor_question_already_answered`.

Se admiten respuestas antes y después del reporte:

- Antes del cierre, el recibo tiene `report_revision=null` y el primer informe incluirá la declaración.
- Después del cierre, la respuesta y la nueva revisión del reporte se guardan en una sola transacción, partiendo de la última versión disponible.
- Si falla el guardado de la revisión, también se revierten respuesta y eventos. La misma UUID permite reintentar.

Las instalaciones anteriores migran sin recibir preguntas retrospectivas. No se alteran sus reportes, checkpoints, trazas ni eventos.

## API

```http
POST /v1/demo-workflows
Content-Type: application/json

{"fixture_id":"auth-disabled","monitored":true}
```

| Método y ruta | Resultado |
|---|---|
| `GET /v1/analyses/{id}/questions` | Lista de preguntas, o lista vacía para análisis sin Monitor |
| `POST /v1/analyses/{id}/questions/{question_id}/answers` | Recibo de respuesta o de reintento |

Cuerpo del envío:

```json
{
  "submission_id": "12345678-1234-4234-8234-123456789abc",
  "actor": "demo-author",
  "role": "developer",
  "text": "Contexto no secreto declarado por una persona."
}
```

Se distinguen 404 para análisis/pregunta ausentes, 409 para conflictos y 422 para entradas inválidas. Texto: 1–4000 caracteres, autor: 1–120, rol: 1–80; todos deben contener texto visible. Se rechazan campos adicionales como fechas o estados de verificación enviados por el cliente.

## Web local

La página principal incorpora «Crear demo con pregunta». Completa el ciclo simulado, muestra la pregunta y permite registrar autor, rol y respuesta. Después de guardar, carga la nueva revisión y muestra la declaración como texto literal.

Si falla una solicitud, se conserva el borrador en esa página. Reintentar el mismo contenido usa la misma UUID. El borrador sin enviar no persiste al recargar o cerrar; una respuesta ya guardada sí puede recuperarse abriendo el análisis por ID. En una revisión histórica el formulario queda deshabilitado. El estado de la pregunta mostrado corresponde al estado actual, separado del reporte histórico.

## CLI local y uso no interactivo

```powershell
$env:SENTINELFORGE_DATABASE_PATH = ".local\monitor-demo.sqlite3"
$inicio = .\.venv\Scripts\python.exe -m sentinelforge.cli workflow-start --monitored | ConvertFrom-Json
$analysisId = $inicio.analysis_id
foreach ($version in 1..5) {
    .\.venv\Scripts\python.exe -m sentinelforge.cli workflow-advance $analysisId --expected-version $version
}
.\.venv\Scripts\python.exe -m sentinelforge.cli workflow-questions $analysisId
```

Para responder, usar `workflow-answer ID QUESTION_ID --submission-id UUID --actor NOMBRE --role ROL --text TEXTO`. Todos los datos son argumentos explícitos; ningún comando espera teclado. Una operación exitosa devuelve JSON y código 0, incluidos avances que terminan con informe parcial. El consumidor de CI debe consultar ese estado y aplicar su política; esta capa no añade un gate automático de seguridad. Errores de entrada, búsqueda o conflicto salen con código 2.

## Evidencia de validación local

El 20 de noviembre de 2026 se ejecutaron las 104 pruebas con pytest y Ruff sin errores, usando Python 3.14.10 del `.venv` existente. No se añadieron dependencias. Los casos nuevos cubren respuesta temprana y tardía, reintentos, claves en conflicto, concurrencia, rollback, migración y protección de registros inmutables.

En la web local se creó un análisis con pregunta: terminó sin esperar entrada y publicó la revisión 1 con estado `PARTIAL`. Al responder se publicó la revisión 2, conservando la primera. El texto `<b>texto literal</b>` apareció literalmente y la declaración permaneció `unverified`. Tras reiniciar Uvicorn y abrir el mismo ID se recuperaron la pregunta respondida y la revisión 2.

Antes de migrar la base local se hizo una copia en `.local/backups/`. La comparación posterior confirmó que las 13 revisiones anteriores conservan exactamente sus valores; el esquema pasó de 3 a 4. Los datos y copias locales están ignorados por Git. Esta evidencia corresponde a ejecución local; todavía no se ha ejecutado la CI remota de esta capa.

## Límites y aprendizaje

Una pregunta y una respuesta por análisis. No hay edición de respuestas, adjuntos, SSE, autenticación ni validación del contexto humano sobre sistemas reales. No se solicitan secretos ni se ejecuta el texto recibido. El flujo completo sigue siendo una demostración con fixtures.

Preguntas: ¿por qué `answered` no significa `verified`? ¿Qué protege la UUID? ¿Qué diferencia hay entre un checkpoint terminado y un reporte parcial? ¿Qué se revierte si falla la publicación de una revisión?
