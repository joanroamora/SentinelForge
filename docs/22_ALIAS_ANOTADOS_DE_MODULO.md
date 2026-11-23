# Alias anotados de módulo: motor 1.6

## Problema y vocabulario

Una **anotación de tipo** (*type annotation*) expresa una intención sobre un
nombre. No prueba por sí sola qué objeto recibe. Esta capa reconoce la captura
de una función importada en una asignación anotada del módulo:

```python
import subprocess
runner: object = subprocess.run

def launch(command):
    return runner(command, shell=True)
```

El motor 1.5 omitía esa forma. El vínculo se reconstruye desde el valor
`subprocess.run` y su import, sin deducirlo de `object` ni evaluar la anotación.
Reconocer ese vínculo sigue sin probar identidad efectiva del módulo,
alcanzabilidad o explotabilidad.

## Diseño y tradeoffs

Se admite `AnnAssign` directamente en el cuerpo del módulo, con un nombre
simple como destino y un valor presente. La anotación puede ser un nombre,
como `object`, o una cadena literal, como `'Callable[..., object]'`. No se
interpreta el contenido de esa cadena ni se consulta un comprobador de tipos.
La anotación y los valores literales no se incorporan al reporte.

El valor debe ser una referencia directa a una de las cinco funciones ya
reconocidas de `subprocess`: atributo de un import de módulo o nombre importado
directamente. Se exigen import anterior, una única escritura del destino,
captura anterior a la llamada y ausencia de enlaces o mutaciones competidores.
Los bloqueos de ámbitos y el requisito de `shell=True` literal se conservan.

Las anotaciones pueden contener expresiones. Python 3.11 documenta su
tratamiento en [asignaciones anotadas](https://docs.python.org/3.11/reference/simple_stmts.html#annotated-assignment-statements).
Esta ampliación opta por una lista pequeña de formas admitidas y no las ejecuta.
Anotaciones con llamadas, atributos, subscripts o uniones permanecen fuera,
incluso si un lector humano puede resolverlas. La cadena `'Callable[..., object]'`
es dato literal; la expresión `Callable[..., object]` no pertenece a este alcance.

No se amplían capturas anotadas dentro de funciones, en ramas, sin valor, con
destino entre paréntesis o con referencias encadenadas. Las asignaciones simples
sin anotación mantienen su soporte previo en módulo y función. Una anotación
adicional sin valor sobre un alias existente también conserva el rechazo
conservador por escrituras competidoras.

## Corroboración y recorrido del argumento

El detector selecciona destinos admisibles y aplica su resolución de imports.
El corroborador reconstruye la declaración desde los bytes originales, consulta
las tablas de símbolos, comprueba las escrituras y relee el import. No llama al
resolver del detector. Las pruebas le presentan también señales inventadas en
casos rechazados, llamadas canónicas erróneas y literales distintos de `True`.

No se modifica el trazado del argumento. Las capturas nuevas están en el módulo,
mientras los trazadores recorren asignaciones dentro de una función. Una llamada
al alias en el módulo puede corroborarse y seguir teniendo origen desconocido
por `function_out_of_scope`. La inconclusión se conserva, no se completa con una
explicación inventada.

Ambos comprobadores comparten CPython y supuestos estáticos. Separar estrategias
y procesos no constituye verificación formal ni resuelve efectos dinámicos.

## Versiones, historia y adaptadores

| Componente | Versión emitida | Lectura histórica |
|---|---|---|
| Detector / corroborador | 1.6 | 1.0–1.5 |
| Investigador / comprobador del argumento | 1.2 | 1.0, 1.1 |
| Evaluador | 1.1 | 1.0 |

Se mantienen las formas de los contratos y SQLite 7. Los fingerprints nuevos
incluyen 1.6; no se reescriben expedientes antiguos. La recuperación de revisiones
y recibos cubre también detector/corroborador 1.5 con trazadores 1.2.

CLI, API y web reciben la capacidad mediante el mismo servicio y las operaciones
existentes. La integración usa SQLite temporal: crea, corrobora, traza, registra
contexto humano y recupera la operación con la misma UUID después de una nueva
revisión. Las señales y declaraciones permanecen `unverified`; el expediente
con señales sigue `PARTIAL` y la primera revisión conserva su contenido.

## Uso local

Desde la raíz, con el entorno existente:

```powershell
.\.venv\Scripts\python.exe -m sentinelforge.cli scan-file tests/fixtures/local_scan/annotated_assignment_alias.py
.\.venv\Scripts\python.exe -m sentinelforge.cli --no-animation evaluate --corpus baseline --format json
.\.venv\Scripts\python.exe -m sentinelforge.cli --no-animation evaluate --corpus challenge --format pretty
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
```

La fixture es sintética, tiene una excepción de protección y debe analizarse
como datos. `scan-file` no persiste expedientes. Para guardarlo y consultarlo
en la web se usan `scan`, `scan-verify` y `scan-trace`, o el selector de archivos.

Se conservan límites de entrada, nodos, señales, pasos y tiempo de los workers.
No se instalan dependencias, ejecutan artefactos, crean migraciones, invocan
proveedores LLM ni modifican servicios externos.

## Comparación con las mismas referencias

Ambos corpus conservan fuentes, etiquetas, categorías y hash:

- Baseline 1.0: `7b6e4d638246e2711d4934ab472b36671e7da03c7c6bf7e04d9db48ad1e63cbd`.
- Challenge 1.0: `32ec0eecb77c3e50a6619187226417df54a6fdba858dd9f5e4764d1e8d5883fc`.

Antes del cambio se contrastaron las mediciones 1.5 con el hash del motor
existente y se conservó una instantánea de sus cuatro archivos modificados.
La comparación posterior verifica referencias y hashes de fuentes, además de
conservar todos los casos que antes coincidían.

| Medición sobre challenge | Motor 1.5 | Motor 1.6 |
|---|---:|---:|
| Señales localizadas | 10/13 | 11/13 |
| Recorridos coincidentes con la referencia | 10/13 | 11/13 |
| Omisiones por caso | 3 | 2 |
| Falsos positivos observados por caso | 0 | 0 |

Mejora `annotated-module-capture`, sin cambiar su referencia ni categoría.
Permanecen `two-hop-module-alias` y `constant-true-conditional-import` como
omisiones visibles. Baseline conserva 19/19 señales y recorridos coincidentes,
incluidos cuatro inconclusos; se reconocen los dos errores esperados de cada
conjunto y no se pierden coincidencias previas.

Son referencias sintéticas de desarrollo sin auditoría independiente. `pass`
sigue describiendo coincidencia en alcance, no seguridad general. Las dos
fronteras pendientes continúan en `boundary_gaps` y las métricas totales.

## Evidencia y nota académica

Validación local del 21 de noviembre de 2026: **628 pruebas aprobadas, 2 omitidas
por capacidades de Windows y Ruff limpio**, con Python 3.14.10 de la `.venv`.
La suite completa tardó 191,77 s y usó bases temporales y sockets locales para
la integración HTTP. Las pruebas específicas cubren las cinco funciones
canónicas, ambas formas de import, anotaciones como datos, Unicode/BOM/CRLF,
orden, ámbitos, reasignaciones, mutaciones y afirmaciones inventadas. Los primeros
casos de detección fallaron antes del cambio; pasan en la suite posterior.

La CLI real terminó con código 0 para ambos conjuntos y para la fixture.
Esta última observa una llamada en línea 10, columna 12, con final exclusivo
en columna 49. La evidencia ignorada por Git queda en `.local/evaluation/`:

- `annotated-alias-*-before-v1.5.json` y `annotated-alias-before-v1.5/`: mediciones
  y archivos previos contrastados con el hash del motor.
- `annotated-alias-*-v1.6.json` y `annotated-alias-comparison.json`: mediciones y
  comparación de referencias, fuentes, categorías y coincidencias conservadas.
- `annotated-alias-scan-v1.6.json`, `annotated-alias-tests-v1.6.txt` y
  `annotated-alias-delta-v1.5.patch`: fixture, suite y delta de implementación.
- `annotated-alias-api-before.json` y `annotated-alias-api-after.json`: OpenAPI
  anuncia detector/corroborador 1.6; el expediente histórico consultado conserva
  revisión 3 y la misma huella de JSON.

La recarga no creó expedientes ni migró la base real. En integración, el contexto
humano permanece sin verificar y reintentar el trazado conserva la revisión 4
después de responder. La construcción del wheel, CI remota de 1.6 y auditoría
de las referencias siguen pendientes. Esta capa y la 1.5 permanecen locales,
sin commit ni publicación, en `codex/annotated-module-aliases`.

Lo aprendido: la anotación y el valor asignado son elementos distintos. Resolver
el callable exige comprobar el valor, el import y los ámbitos; leer un nombre
de tipo no reemplaza esa evidencia. Conservar los inconclusos evita presentar
una ampliación de detección como si también ampliara todo el trazado.

Preguntas de repaso: ¿qué demuestra `object` y qué no? ¿Por qué hace falta un
valor en la captura? ¿En qué difieren una anotación entre comillas y una expresión
que habría que interpretar? ¿Por qué una llamada del módulo conserva un trazado
inconcluso? ¿Qué queda sin demostrar cuando coinciden 11/13 señales sintéticas?

Decisión: [ADR 0017](adr/0017-alias-anotados-de-modulo.md).
