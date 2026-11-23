# Cadenas de alias de módulo: motor 1.7

## Problema y vocabulario

Un alias puede capturarse mediante varios nombres antes de usarse. Esta capa
relaciona la llamada final con el import original en una cadena como esta:

```python
import subprocess
first = subprocess.run
runner = first

def launch(command):
    return runner(command, shell=True)
```

Cada asignación es una **captura** (*capture*) de una referencia. El motor 1.6
admitía la primera y omitía la segunda. Resolver el callable sigue siendo
distinto de investigar el origen de `command`; tampoco demuestra que la llamada
se ejecute o que exista una vulnerabilidad explotable.

## Diseño acotado y tradeoffs

Se admiten hasta **ocho capturas** directamente en el cuerpo del módulo. La
primera debe proceder de un import válido y anterior; las restantes copian por
nombre una captura ya resuelta. Se admiten las cinco funciones canónicas de
`subprocess`, imports de módulo o función y las anotaciones de módulo ya
admitidas en 1.6. El import no cuenta como captura.

Cada destino tiene una sola escritura y precede a su uso en el orden léxico.
Se comprueba cada nombre intermedio frente a imports competidores, borrados,
declaraciones, patrones, mutaciones y otras escrituras. Una reasignación
posterior de `first` bloquea conservadoramente la cadena, aunque un análisis
temporal más preciso pudiera conservar la referencia anterior de `runner`.
El alcance no modela todos los efectos de ejecución.

El detector recoge destinos, descarta enlaces ambiguos y propaga referencias
válidas hacia adelante. El corroborador relee las declaraciones y sigue hacia
atrás el valor de cada captura, contrastando símbolos del compilador, orden,
escrituras y mutaciones. Comprueba ciclos y su propio límite de ocho capturas.
No importa el resolver ni recibe el mapa de referencias del detector.

El corroborador conserva solo pruebas positivas de resolución durante esa
invocación del worker. La clave incluye el alias final y sus funciones
contenedoras. La prueba conserva la posición de la captura: cada llamada debe
seguir siendo posterior, incluso si las afirmaciones llegan desordenadas.
La caché no se comparte entre archivos, procesos, solicitudes ni expedientes.
Ubicación, llamada canónica y literal `True` se contrastan para cada señal.

Una comprobación con ocho capturas y cien señales reveló que releer la misma
cadena para cada señal superaba el timeout de cinco segundos. La caché de
pruebas positivas evita repetir ese trabajo sin ampliar el límite ni compartir
estado entre fuentes. Los tests presentan primero una llamada válida y luego
una anterior a la captura o perteneciente a una función con parámetro que oculta
el alias: ambas afirmaciones posteriores deben quedar inconclusas.

En la comprobación posterior se observaron cien patrones reproducidos sobre
16 803 bytes y 4 848 nodos AST, en aproximadamente 0,51 s para la comprobación
local completa. Es una observación de una entrada sintética en esta máquina,
no una prueba de carga, garantía de latencia o cuota dura de recursos.

## Captura y visibilidad son contextos distintos

Las capturas intermedias se evaluaron en el módulo. Un parámetro `first` dentro
de `launch` no modifica por sí solo la referencia ya capturada por `runner`.
Un parámetro `runner` sí impide justificar una llamada a ese nombre como alias
global. Cada comprobador contrasta el destino final en el contexto de la llamada
y los enlaces intermedios en el contexto de su captura.

Se conservan bloqueos por escrituras y mutaciones de otras funciones. La
ampliación 1.5 de asignaciones locales independientes solo relaja la resolución
de imports de módulo, no las escrituras de destinos de alias capturados.

## Fronteras conservadas

Las cadenas dentro de funciones o que mezclan captura de módulo y captura local
no se amplían. Las capturas locales siguen requiriendo una referencia directa
a un import. También quedan fuera referencias adelantadas, capturas
condicionales/múltiples, alias de módulos completos, propiedades calculadas y
anotaciones no admitidas. Las formas válidas aún pueden omitirse por bloqueos
conservadores.

Superar ocho capturas impide establecer ese alias: el detector no emite su señal
y el corroborador devuelve `inconclusive / binding_not_established` ante una
afirmación sobre él. Es una frontera de alcance visible, no una conclusión de
seguridad. Los errores técnicos de parser, tiempo o límites globales mantienen
su tratamiento separado.

El trazado del argumento conserva la versión 1.2 y sus límites de una función.
Una llamada de módulo puede tener patrón corroborado y recorrido inconcluso
por `function_out_of_scope`. Las estrategias comparten CPython y supuestos;
su separación no constituye verificación formal.

## Versiones e historia

| Componente | Versión emitida | Lectura histórica |
|---|---|---|
| Detector / corroborador | 1.7 | 1.0–1.6 |
| Investigador / comprobador del argumento | 1.2 | 1.0, 1.1 |
| Evaluador | 1.1 | 1.0 |

Los contratos conservan su forma y SQLite sigue en esquema 7. La versión nueva
produce fingerprints nuevos sin reescribir revisiones o recibos históricos.
La recuperación cubre también metadatos 1.6 con trazado 1.2.

CLI, API y web usan el mismo servicio. La integración con fuente encadenada crea,
corrobora, traza, registra contexto humano y recupera el trazado con la misma
UUID después de responder. Las señales y declaraciones siguen `unverified`,
el expediente sigue `PARTIAL` y la revisión original se conserva.

## Uso local y aprendizaje

Desde la raíz, con la `.venv` existente:

```powershell
.\.venv\Scripts\python.exe -m sentinelforge.cli scan-file tests/fixtures/local_scan/module_alias_chain.py
.\.venv\Scripts\python.exe -m sentinelforge.cli --no-animation evaluate --corpus baseline --format json
.\.venv\Scripts\python.exe -m sentinelforge.cli --no-animation evaluate --corpus challenge --format pretty
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
```

La fixture es sintética y contiene una excepción de protección. Se procesa como
datos, nunca se ejecuta. `scan-file` no persiste; `scan`, la corroboración y el
trazado existentes permiten guardar el expediente con el mismo original.

Se conservan los límites de 64 KiB, 20 000 nodos, 100 señales y cinco segundos
por worker, además de los límites de trazado. No se añaden dependencias,
migraciones, proveedores LLM, ejecución de artefactos ni servicios externos.

## Comparación con las mismas referencias

Se conservan fuentes, expectativas, categorías y hash de ambos corpus:

- Baseline 1.0: `7b6e4d638246e2711d4934ab472b36671e7da03c7c6bf7e04d9db48ad1e63cbd`.
- Challenge 1.0: `32ec0eecb77c3e50a6619187226417df54a6fdba858dd9f5e4764d1e8d5883fc`.

Antes de editar se contrastaron las mediciones 1.6 con el hash del motor
existente y se conservaron sus cuatro archivos modificados. La comparación
final comprueba las referencias y hashes de fuentes de cada caso, sin perder
coincidencias anteriores.

| Medición sobre challenge | Motor 1.6 | Motor 1.7 |
|---|---:|---:|
| Señales localizadas | 11/13 | 12/13 |
| Recorridos coincidentes con la referencia | 11/13 | 12/13 |
| Omisiones por caso | 2 | 1 |
| Falsos positivos observados por caso | 0 | 0 |

Mejora `two-hop-module-alias` sin modificar su referencia ni categoría.
`constant-true-conditional-import` continúa como omisión visible. Baseline
conserva 19/19 señales y recorridos coincidentes, incluidos cuatro inconclusos.
Cada corpus reconoce sus dos errores esperados y no se pierden coincidencias
previas. `pass` conserva su significado de acuerdo en alcance; la omisión sigue
en `boundary_gaps` y las métricas totales.

Los conjuntos son sintéticos y sus referencias no tienen auditoría independiente.
Estas cifras no estiman seguridad general, precisión en proyectos reales o el
grado de terminación del producto.

## Evidencia y nota académica

Validación final local del 21 de noviembre de 2026: **700 pruebas aprobadas,
2 omitidas por capacidades de Windows y Ruff limpio**, con Python 3.14.10 de
la `.venv`. La suite completa tardó 239,43 s y usó SQLite temporal y sockets
locales en las pruebas HTTP. Una primera ejecución específica quedó detenida
en la integración bajo el sandbox de Windows; se interrumpió y la suite completa
se ejecutó con acceso a sockets locales.

La corrida final emitió una `UnsupportedFieldAttributeWarning` de Pydantic en
`test_concurrent_api_revisions_allow_one_writer`; sus aserciones pasaron. No se
cambiaron dependencias ni se atribuye aquí una causa confirmada a la advertencia.

Las pruebas cubren las cinco funciones e imports admitidos, cadenas anotadas,
Unicode/BOM/CRLF, capturas frente a parámetros, todos los enlaces competidores,
ciclos, referencias adelantadas, fronteras locales/mixtas y ocho frente a nueve
capturas. Las afirmaciones incorrectas también se envían al corroborador. El
caso de cien señales reveló el timeout por trabajo repetido; después de la
caché, la prueba y el experimento acotado terminaron conservando cien decisiones.
Las pruebas de orden y ámbitos impiden reutilizar una prueba fuera de su contexto.

La CLI real devolvió código 0 en ambos corpus y en la fixture, cuya señal está
en línea 11, columna 12 y final exclusivo en columna 49. La evidencia ignorada
por Git queda en `.local/evaluation/`:

- `alias-chain-*-before-v1.6.json` y `alias-chain-before-v1.6/`: mediciones y
  archivos previos contrastados con el motor al inicio.
- `alias-chain-*-v1.7.json` y `alias-chain-comparison.json`: resultados finales
  y comparación de fuentes, categorías, referencias y coincidencias conservadas.
- `alias-chain-tests-v1.7.txt`, `alias-chain-scan-v1.7.json` y
  `alias-chain-delta-v1.6.patch`: suite final, fixture y delta de implementación.
- `alias-chain-bounds-v1.7.json`: observación de ocho capturas y cien señales.
- `alias-chain-api-before.json` y `alias-chain-api-after.json`: OpenAPI anuncia
  detector/corroborador 1.7 y el expediente histórico consultado conserva revisión
  3 y una huella de JSON idéntica.

La recarga no creó expedientes ni migró la base real. La integración conserva
la revisión original y recupera el trazado tras registrar una respuesta humana
sin verificar. La construcción del wheel, CI remota de 1.7 y auditoría de las
referencias siguen pendientes. Las capas 1.5–1.7 permanecen locales, sin commit
ni publicación, en `codex/module-alias-chains`.

Lo aprendido: resolver una cadena exige revisar cada enlace, su orden y el
contexto en que se capturó. Repetir pruebas de seguridad puede consumir el
presupuesto de tiempo; reutilizarlas exige conservar sus condiciones de validez.
La mejora del callable no implica ampliar automáticamente el recorrido del dato.

Preguntas de repaso: ¿por qué un parámetro `first` no sustituye un `runner`
capturado antes? ¿Qué cambia si el parámetro se llama `runner`? ¿Por qué se
rechaza una reasignación intermedia posterior? ¿Qué información limita la
reutilización de una prueba? ¿Qué queda sin demostrar al reproducir 12/13 señales
de un corpus sintético?

Decisión: [ADR 0018](adr/0018-cadenas-acotadas-de-alias-de-modulo.md).
