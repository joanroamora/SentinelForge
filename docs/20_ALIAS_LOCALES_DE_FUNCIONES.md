# Alias dentro de funciones: motor 1.4 y trazado 1.2

## Problema y vocabulario

El corpus de desafío reveló dos omisiones con una misma causa: el alias de una
función de `subprocess` se asignaba dentro de otra función. Un **ámbito**
(*scope*) determina dónde tiene significado ese nombre:

```python
def launch(command):
    import subprocess as sp
    runner = sp.run
    return runner(command, shell=True)
```

`runner` pertenece a `launch`. Identificar que apunta a `subprocess.run` y
seguir el origen de `command` son tareas distintas. Esta capa reconoce el
callable, lo corrobora y conserva el trazado del argumento en los casos
admitidos. No ejecuta la función ni demuestra que el comando sea explotable.

## Diseño y alcance

Se admite una asignación simple, con un solo nombre de destino, directamente
en el cuerpo de la misma función y anterior a la llamada en el orden léxico.
La referencia procede de un import directo de módulo o de esa función. Puede
ser un atributo como `sp.run` o un nombre de función importado directamente.
Se conservan las cinco llamadas canónicas y el requisito de `shell=True`
literal de `SF-PY-001`.

El destino debe tener una única escritura. Parámetros competidores,
reasignaciones, borrados, imports sustitutos, patrones, declaraciones,
mutaciones y enlaces anidados ambiguos impiden establecer el alias. Las
comprobaciones siguen siendo conservadoras y pueden omitir usos válidos. Se
incluyen métodos, async, Unicode/BOM/CRLF y varias sentencias en una línea.

Las capturas condicionales, múltiples o anotadas, cadenas de alias y lecturas de
un alias capturado en una función exterior siguen fuera de esta ampliación.
La resolución no demuestra qué módulo se cargaría realmente ni alcanzabilidad,
ausencia de efectos dinámicos o explotabilidad.

El detector reutiliza su resolución de capturas, aplicándola al ámbito de la
función y a imports admisibles. El comprobador separado relee la asignación,
consulta la tabla de símbolos local, rechaza vínculos competidores y reconstruye
la referencia desde el import original. No importa el resolver del detector.

## Efecto sobre el origen del comando

Una captura como `runner = sp.run` es un atributo en el AST. Antes cortaba
conservadoramente el recorrido de otros nombres. Ahora, bajo el prerrequisito
de corroboración positiva de la fuente original, se admite omitir esa captura
al seguir un argumento diferente.

La excepción exige que sea el destino usado como callable en la llamada, con
el atributo canónico esperado y un import de `subprocess` anterior. No convierte
el atributo en un origen conocido del argumento. Si se pasa el propio callable
como argumento, ese valor sigue fuera del alcance del trazado.

El investigador recorre hacia atrás y relee las declaraciones de import. El
comprobador reconstruye hacia adelante y mantiene referencias de módulo que
actualiza con imports y asignaciones. Conservan implementaciones y procesos
separados. Comparten CPython y supuestos estáticos; no son una verificación
formal ni prueban efectos en ejecución.

Otras propiedades, incluso una captura de función con otro destino, siguen
pudiendo interrumpir el recorrido. Las pruebas envían también propuestas de
origen manipuladas al comprobador para verificar su rechazo. Un literal o un
parámetro no se transforma en una decisión de seguridad.

## Versiones, historia y adaptadores

| Componente | Versión emitida | Lectura histórica |
|---|---|---|
| Detector / corroborador | 1.4 | 1.0, 1.1, 1.2, 1.3 |
| Investigador / comprobador del argumento | 1.2 | 1.0, 1.1 |
| Evaluador | 1.1 | 1.0 |

Las formas de los contratos y SQLite 7 se conservan. La nueva versión del
detector produce fingerprints nuevos; las revisiones y recibos anteriores no se
reescriben. Se prueba también la recuperación de metadatos 1.3 con trazado 1.1.

CLI, API y web utilizan el mismo servicio y contratos existentes. La integración
crea y corrobora un expediente, traza el comando, agrega contexto humano y
reintenta la operación. La revisión original se conserva y el aporte humano
permanece `unverified`, al igual que la señal. El expediente sigue `PARTIAL`.

## Evaluación con las mismas referencias

Los dos corpus conservan sus fuentes, etiquetas, categorías y hashes:

- Baseline 1.0: `7b6e4d638246e2711d4934ab472b36671e7da03c7c6bf7e04d9db48ad1e63cbd`.
- Challenge 1.0: `32ec0eecb77c3e50a6619187226417df54a6fdba858dd9f5e4764d1e8d5883fc`.

| Medición sobre challenge | Motor 1.3 | Motor 1.4 |
|---|---:|---:|
| Señales localizadas | 7/13 | 9/13 |
| Recorridos coincidentes con la referencia | 7/13 | 9/13 |
| Omisiones por caso | 6 | 4 |
| Falsos positivos observados por caso | 0 | 0 |

Mejoran `function-assignment-global-import` y
`function-assignment-local-import`, sin reclasificarlos ni modificar sus
referencias. Baseline mantiene 19/19 señales y recorridos coincidentes, incluidos
cuatro resultados inconclusos. Las cadenas, capturas anotadas, import condicional
y asignación local en otra función continúan como cuatro omisiones visibles.

Estas cifras describen referencias sintéticas de desarrollo sin auditoría
independiente. No estiman seguridad general o calidad sobre repositorios reales.
El `pass` del evaluador sigue refiriéndose al alcance declarado; las fronteras
pendientes continúan en sus métricas y tabla de discrepancias.

## Uso y aprendizaje

Desde la raíz del repositorio, con la `.venv` existente:

```powershell
.\.venv\Scripts\python.exe -m sentinelforge.cli scan-file tests/fixtures/local_scan/function_assignment_alias.py
.\.venv\Scripts\python.exe -m sentinelforge.cli --no-animation evaluate --corpus challenge --format pretty
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
```

La fixture tiene una excepción de protección: debe analizarse como datos,
nunca ejecutarse. `scan-file` devuelve resultados sin crear un expediente; `scan`
o la carga desde la web permiten guardarlo y aportar el mismo original para
corroborar y trazar.

Las pruebas cubren combinaciones de import y llamada, ámbitos, reasignaciones,
afirmaciones falsas, propiedades opacas, propuestas de trazado manipuladas,
compatibilidad histórica y el recorrido CLI/API con contexto humano. Se mantienen
límites de bytes, nodos, pasos, señales y tiempo. No hay nuevas dependencias,
proveedores LLM, ejecución de artefactos ni escaneos externos.

Validación local del 21 de noviembre de 2026: **513 pruebas aprobadas, 2 omitidas
por capacidades de Windows y Ruff limpio**, con Python 3.14.10 de la `.venv`.
La suite completa tardó 128,14 s; las pruebas de asyncio usaron sockets locales
y bases temporales. La CLI real terminó con código 0 para ambos corpus y para
la fixture, que devuelve una señal en línea 8, columna 12, con final exclusivo
en columna 36.

La evidencia ignorada por Git queda en `.local/evaluation/`:

- `function-alias-baseline-before-v1.3.json` y
  `function-alias-challenge-before-v1.3.json`: mediciones anteriores verificadas
  contra el hash del motor al comenzar la iteración.
- `function-alias-baseline-v1.4.json`, `function-alias-challenge-v1.4.json` y
  `function-alias-comparison.json`: mediciones y comparación de fuentes,
  expectativas, categorías y ausencia de pérdidas entre referencias coincidentes.
- `function-alias-scan-v1.4.json`: comportamiento de la fixture real.
- `function-alias-challenge-v1.4-terminal.txt`: vista de los resultados guardados,
  sin repetir el análisis.
- `function-alias-api-before.json` y `function-alias-api-after.json`: recarga de
  la API local, versiones 1.4/1.2 en OpenAPI y huella idéntica del expediente
  histórico consultado, que conserva su revisión 3.

La recarga no creó análisis nuevos ni migró SQLite. La prueba de integración
conserva una primera revisión y una respuesta humana al reintentar el trazado.

Lo aprendido: ampliar detección exige comprobar también la corroboración y los
efectos sobre el recorrido de datos. El callable y su argumento tienen pruebas
y límites distintos. La construcción del wheel, CI remota y auditoría de las
referencias continúan pendientes.

Preguntas: ¿dónde tiene significado un alias local? ¿Qué diferencia hay entre
identificar la función y conocer su argumento? ¿Por qué otra propiedad puede
dejar el origen inconcluso? ¿Por qué conservar versiones y recibos antiguos?
¿Qué queda por demostrar cuando una referencia coincide?

Decisión: [ADR 0015](adr/0015-alias-locales-y-captura-del-callable.md).
