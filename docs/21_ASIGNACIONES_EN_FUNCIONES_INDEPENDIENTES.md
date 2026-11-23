# Asignaciones en funciones independientes: motor 1.5

## Problema y vocabulario

Un **ámbito** (*scope*) decide a qué variable corresponde un nombre. Una
asignación local dentro de `unrelated` no sustituye el import de módulo que
consulta `launch`:

```python
import subprocess as sp

def unrelated():
    sp = replacement

def launch(command):
    return sp.run(command, shell=True)
```

El motor 1.4 omitía esa señal por bloquear conservadoramente cualquier escritura
de `sp` en el archivo. Esta capa distingue las asignaciones simples de funciones
independientes. Continúa observando un patrón estático; no ejecuta las funciones
ni confirma qué módulo se cargaría o si existe una vulnerabilidad.

## Diseño simple y tradeoffs

La ampliación afecta a la resolución de **imports de módulo**, tanto del módulo
`subprocess` como de una de sus cinco funciones reconocidas. Se puede omitir una
escritura al resolver ese import cuando:

- Es una asignación simple a un único nombre, directamente en el cuerpo de una
  función nombrada. Puede haber varias asignaciones simples a ese nombre.
- La función no contiene la llamada analizada, ni es una función exterior que
  la contiene.
- No aparece una declaración `global` o `nonlocal` de ese nombre en el archivo.
- No hay otras escrituras de ese nombre dentro de esa función que incumplan la
  forma admitida. Los restantes bloqueos del motor también deben cumplirse.

Los parámetros de funciones independientes conservan el soporte previo; ahora
pueden también recibir una asignación simple local. Se contemplan funciones
asíncronas, métodos, lectores globales anidados y coordenadas UTF-8/BOM/CRLF.

El detector identifica los destinos y sus funciones propietarias mediante AST.
Para cada llamada conserva las escrituras de su propio ámbito y de sus
funciones exteriores. El corroborador separado comprueba que el compilador
clasifica el nombre como local y relee las asignaciones originales. No importa
el resolver del detector ni recibe su mapa de destinos permitidos.

El tradeoff sigue favoreciendo un alcance pequeño: asignaciones condicionales,
anotadas, múltiples, aumentadas, borrados, imports competidores y nombres ligados
por patrones o excepciones mantienen los bloqueos conservadores. Las mutaciones
de atributos o subscripts también bloquean, aunque aparezcan en otra función.
Una declaración `global`/`nonlocal` en otra parte del archivo puede impedir una
resolución válida; no se introduce una resolución general de todos los ámbitos.

Esta mejora también permite establecer el import original usado en una captura
de callable ya admitida. No relaja por sí misma las escrituras competidoras del
**destino** de un alias por asignación: un `runner` local en otra función puede
seguir impidiendo justificar un `runner` capturado en el módulo. Las cadenas y
capturas anotadas o condicionales continúan fuera de alcance.

## Contraejemplo del corroborador

Las pruebas envían señales inventadas al corroborador, incluso si el detector
no produjo ninguna. Así apareció un defecto previo al contrastar una
comprensión que oculta el import:

```python
import subprocess as sp
[sp.run('EXAMPLE', shell=True) for sp in values]
```

En el Python 3.14 local, las tablas de símbolos no bastaban para rechazar esa
afirmación: una comprensión optimizada no necesariamente presenta una tabla
hija. El corroborador 1.5 comprueba además los destinos de las comprensiones en
el AST. Si enlazan el nombre, mantiene el rechazo conservador del detector.
Se prueban listas, conjuntos, diccionarios y generadores.

El objetivo es impedir una corroboración injustificada, no acreditar seguridad
del ejemplo. Ambos componentes siguen compartiendo CPython y supuestos de
análisis estático; la separación de estrategias no es verificación formal.

## Versiones e historia

| Componente | Versión emitida | Lectura histórica |
|---|---|---|
| Detector / corroborador | 1.5 | 1.0–1.4 |
| Investigador / comprobador del argumento | 1.2 | 1.0, 1.1 |
| Evaluador | 1.1 | 1.0 |

Los contratos conservan su forma y SQLite sigue en esquema 7. Los fingerprints
nuevos incluyen la versión 1.5; las revisiones y recibos anteriores no se
reescriben. La prueba de recuperación incluye ahora metadatos de detector y
corroborador 1.4 junto con trazado 1.2.

CLI, API y web utilizan el mismo servicio. Un caso nuevo puede corroborarse,
trazarse, recibir contexto humano y recuperarse con la misma UUID. Sus señales
y declaraciones humanas permanecen `unverified` y el expediente con señales
sigue `PARTIAL`.

## Cómo comprobarlo

Desde la raíz, con la `.venv` existente:

```powershell
.\.venv\Scripts\python.exe -m sentinelforge.cli scan-file tests/fixtures/local_scan/independent_local_binding.py
.\.venv\Scripts\python.exe -m sentinelforge.cli --no-animation evaluate --corpus baseline --format json
.\.venv\Scripts\python.exe -m sentinelforge.cli --no-animation evaluate --corpus challenge --format pretty
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
```

La fixture es código sintético con una excepción de protección: debe procesarse
como datos, nunca ejecutarse. `scan-file` no crea un expediente. Para persistir
el caso se utiliza `scan` o el selector de archivos de la web, y después se aporta
el original para corroborar y trazar.

Se mantienen 64 KiB por archivo, 20 000 nodos, 100 señales, tiempos máximos de
workers y límites de trazado. No se añaden dependencias, migraciones,
proveedores LLM, ejecución de artefactos ni infraestructura.

## Medición con las referencias intactas

Se conservan fuentes, categorías y expectativas de ambos corpus:

- Baseline 1.0: `7b6e4d638246e2711d4934ab472b36671e7da03c7c6bf7e04d9db48ad1e63cbd`.
- Challenge 1.0: `32ec0eecb77c3e50a6619187226417df54a6fdba858dd9f5e4764d1e8d5883fc`.

Antes de cambiar código se comprobó que las mediciones 1.4 correspondían al
hash del motor integrado. La comparación posterior verifica hashes de fuentes,
referencias y categorías, conservando los casos antes coincidentes.

| Medición sobre challenge | Motor 1.4 | Motor 1.5 |
|---|---:|---:|
| Señales localizadas | 9/13 | 10/13 |
| Recorridos coincidentes con la referencia | 9/13 | 10/13 |
| Omisiones por caso | 4 | 3 |
| Falsos positivos observados por caso | 0 | 0 |

Mejora `unrelated-local-assignment`, sin reetiquetarlo. Los tres casos aún
omitidos son `two-hop-module-alias`, `annotated-module-capture` y
`constant-true-conditional-import`. Baseline conserva 19/19 señales y recorridos
coincidentes, incluidos cuatro resultados inconclusos. Los dos errores esperados
de cada corpus se reconocen. No se pierden referencias antes coincidentes.

Las cifras describen ejemplos sintéticos de desarrollo sin auditoría
independiente; no estiman seguridad general. `pass` conserva el significado de
coincidencia en alcance, mientras las tres omisiones continúan visibles en las
métricas y `boundary_gaps`.

## Evidencia y nota académica

Validación local del 21 de noviembre de 2026: **563 pruebas aprobadas, 2 omitidas
por capacidades de Windows y Ruff limpio**, con Python 3.14.10 de la `.venv`.
La suite completa tardó 140,51 s; las pruebas HTTP usaron sockets locales y
bases temporales. Las pruebas específicas cubren resoluciones válidas, ámbitos
que sí ocultan el import, mutaciones, escrituras fuera de alcance, afirmaciones
inventadas y compatibilidad histórica. Dos pruebas del caso nuevo fallaron
antes del cambio; después pasan dentro de la suite completa.

La CLI real terminó con código 0 para ambos corpus y para la fixture, que
devuelve una señal `subprocess.run` en línea 12, columna 12 y final exclusivo
en columna 52. La evidencia ignorada por Git queda en `.local/evaluation/`:

- `local-bindings-*-before-v1.4.json`: mediciones previas contrastadas con el motor.
- `local-bindings-*-v1.5.json` y `local-bindings-comparison.json`: mediciones y
  comparación de referencias, fuentes y ausencia de pérdidas observadas.
- `local-bindings-scan-v1.5.json` y `local-bindings-tests-v1.5.txt`: fixture y suite.
- `local-bindings-api-before.json` y `local-bindings-api-after.json`: OpenAPI
  anuncia 1.5/1.5 tras recargar el servidor; el expediente histórico consultado
  conserva revisión 3 y una huella de JSON idéntica.

No se crearon expedientes nuevos ni se migró la base real para esa comprobación.
La prueba CLI/API usa una base temporal y preserva la revisión original, contexto
humano sin verificar y reintento de trazado después de responder. La construcción
del wheel, CI remota de esta iteración y auditoría de las referencias siguen
pendientes. No se ha hecho commit ni publicación de esta capa.

Lo aprendido: identificar el propietario de una escritura permite resolver un
caso antes omitido sin ignorar el sombreado real. También es necesario presentar
afirmaciones incorrectas al corroborador: una ausencia de señales del detector
no ejercita su capacidad para refutarlas.

Preguntas de repaso: ¿por qué una asignación local no sustituye al import global?
¿Qué cambia con `global` o `nonlocal`? ¿Por qué una tabla de símbolos no basta
siempre para revisar comprensiones? ¿Qué significa pasar la evaluación con tres
omisiones? ¿Por qué conservar recibos y referencias permite comparar versiones?

Decisión: [ADR 0016](adr/0016-asignaciones-locales-de-funciones-independientes.md).
