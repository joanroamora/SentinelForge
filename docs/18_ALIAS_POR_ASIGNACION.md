# Alias de funciones por asignación: ampliación medida 1.3

Esta página conserva la entrega 1.3. La [ampliación 1.4](20_ALIAS_LOCALES_DE_FUNCIONES.md)
añade capturas directas dentro de funciones y documenta sus efectos en el trazado.

## Problema y vocabulario

Un **alias** es otro nombre para un valor. Esta ampliación reconoce una referencia
a una función importada de `subprocess`, capturada con una asignación simple en el
módulo:

```python
import subprocess
runner = subprocess.run

def launch(command):
    return runner(command, shell=True)
```

El motor 1.2 omitía esa señal. El motor 1.3 relaciona `runner` con la llamada
canónica `subprocess.run`, conservando la ubicación de la llamada a `runner`.
Reconocer la función llamada y averiguar el origen de `command` son operaciones
distintas; el trazado del argumento mantiene su algoritmo anterior.

## Diseño y alcance

- Una asignación `nombre = referencia` directa en el cuerpo del módulo, con un
  solo destino de tipo nombre y un import anterior en el orden del archivo.
- La referencia puede ser `sp.run`, con `import subprocess as sp`, o un nombre
  importado directamente, como `from subprocess import run as start` seguido de
  `runner = start`. Se admiten las cinco funciones ya cubiertas por `SF-PY-001`.
- El alias tiene una única escritura y no puede quedar sustituido por parámetros
  de su ámbito, imports, declaraciones, patrones, borrados o mutaciones visibles.
  Se mantienen comprobaciones conservadoras sobre el resto del archivo, incluso
  para escrituras posteriores o en otras funciones.
- El alias captura una referencia en el módulo. Un parámetro llamado
  `subprocess` dentro de `launch` no modifica por sí solo esa captura; un
  parámetro llamado `runner` dentro de `launch` sí impide justificar esa llamada
  mediante el alias global. Un parámetro de una función independiente sin otras
  escrituras no sustituye el alias del módulo.
- Las cadenas de alias, asignaciones dentro de funciones o condiciones,
  asignaciones múltiples/anotadas, alias de módulos completos y referencias
  calculadas permanecen fuera de esta extensión.

La decisión favorece un alcance pequeño con contraejemplos comprobables. Puede
omitir usos válidos debido a sus bloqueos conservadores. Se comprueba un vínculo
estático, sin demostrar qué módulo se importaría realmente, si la llamada se
ejecuta o si una entrada permite explotarla. El literal `shell=True` sigue siendo
necesario; no se reinterpretan `1`, variables o cadenas como el token `True`.

## Corroboración independiente

El detector construye candidatos desde imports aceptados y descarta nombres con
enlaces competidores. El comprobador relee la asignación original, consulta las
tablas de símbolos del compilador, comprueba la única escritura y reconstruye
la referencia desde el import. Después contrasta ubicación, llamada canónica y
token `True`. No importa el resolver del detector ni recibe su mapa de alias.

Las pruebas también presentan afirmaciones de escáner inventadas en casos
rechazados. Así se comprueba al verificador aunque el detector no haya emitido
ninguna señal. Ambas implementaciones comparten el parser CPython: esta
separación no constituye una prueba formal de independencia.

## Versiones y expedientes

Detector y corroborador emiten **1.3** y mantienen la lectura de 1.0, 1.1 y 1.2.
Los trazadores siguen en 1.1, el contrato de detección conserva esquema 1.0 y
SQLite permanece en esquema 7. La versión del detector cambia el fingerprint de
los análisis nuevos; las revisiones y recibos históricos conservan su contenido.

CLI, API y web utilizan el mismo servicio y reciben la nueva capacidad mediante
los contratos existentes. La señal continúa `unverified` y el expediente con
señales permanece `PARTIAL`. Las declaraciones humanas mantienen su separación
y estado de verificación.

## Medición y uso

Se conserva el corpus 1.0 de 28 casos, incluidas fuentes, etiquetas y categorías.
Su hash canónico es:

`7b6e4d638246e2711d4934ab472b36671e7da03c7c6bf7e04d9db48ad1e63cbd`

La comparación debe mostrar la mejora de `assignment-alias-gap` sin perder las
referencias antes coincidentes. Conservar una categoría `boundary` histórica
permite comparar versiones; no implica que sus omisiones continúen presentes.

Resultado local del 21 de noviembre de 2026, sobre las mismas referencias:

| Medición | Motor 1.2 | Motor 1.3 |
|---|---:|---:|
| Señales localizadas | 18/19 | 19/19 |
| Recorridos coincidentes con la referencia | 18/19 | 19/19 |
| Omisiones por caso | 1 | 0 |
| Falsos positivos observados por caso | 0 | 0 |
| Trazados inconclusos | 4 | 4 |

La CLI real terminó con código 0. La comparación confirma el mismo hash del
corpus, fuentes y referencias esperadas idénticas, una mejora en
`assignment-alias-gap` y ninguna pérdida entre los casos antes coincidentes.
Se reconocieron los dos errores de entrada esperados. Los cuatro recorridos
inconclusos coinciden con sus referencias: no se transformaron en conclusiones
positivas para completar la tabla.

Desde la raíz del repositorio, con la `.venv` existente:

```powershell
.\.venv\Scripts\python.exe -m sentinelforge.cli scan-file tests/fixtures/local_scan/assignment_alias.py
.\.venv\Scripts\python.exe -m sentinelforge.cli --no-animation evaluate --format pretty
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
```

`scan-file` no guarda expedientes. Para guardar y consultar un análisis se usan
`scan`, `scan-verify` y `scan-trace`, o la web local, con la misma fixture aportada
como datos. El archivo de ejemplo contiene una excepción de protección y debe
analizarse, nunca ejecutarse.

La medición conserva metadatos en `.local/evaluation/`, fuera de Git. Ningún
resultado de este corpus sintético pequeño, sin auditoría independiente ni
muestreo representativo, estima por sí solo la seguridad de proyectos reales.
Los resultados inconclusos siguen siendo explícitos aunque coincidan con la
referencia esperada.

## Validación y evidencia local

**435 pruebas aprobadas, 2 omitidas por capacidades de Windows y Ruff limpio**,
usando Python 3.14.10 de la `.venv` existente. La suite completa tardó 141,23 s.
En el sandbox de Windows, la integración se bloqueó al crear el socketpair de
`asyncio`; la ejecución con acceso a sockets locales completó las pruebas con
bases temporales. No se cambió el código del producto para sortear esa restricción.

Los archivos locales ignorados por Git incluyen:

- `assignment-alias-baseline-v1.2.json` y `assignment-alias-v1.3.json`: mediciones.
- `assignment-alias-comparison.json`: comprobaciones de referencias y regresión.
- `assignment-alias-scan-v1.3.json`: la fixture devuelve una señal `subprocess.run`
  en línea 10, columna 12, con final exclusivo en columna 36.
- `assignment-alias-tests.txt`: salida de la suite completa.
- `assignment-alias-api-before.json` y `assignment-alias-api-after.json`: recarga
  del servidor local, valores por defecto 1.3 en OpenAPI y huella idéntica del
  expediente histórico consultado, que conserva revisión 3.

La recarga no creó análisis nuevos ni migró SQLite. La integración comprueba
también versiones históricas 1.0, 1.1 y 1.2 con sus recibos. La construcción del
wheel y la CI remota de esta entrega siguen sin verificarse; no se instalaron
herramientas ni se publicó la rama durante esta iteración.

## Nota académica

Esta iteración parte de una omisión observada y contrasta una mejora conservando
las referencias. Las pruebas cubren alias válidos, reasignaciones, ámbitos,
imports competidores, posiciones UTF-8/BOM/CRLF, afirmaciones incorrectas,
manipulación de prompts como datos, no ejecución, historia y CLI/API.

Preguntas de repaso: ¿qué diferencia hay entre identificar la función y seguir
su argumento? ¿Por qué un parámetro `runner` puede ocultar el alias global?
¿Qué coste tiene rechazar una reasignación posterior a la llamada? ¿Por qué un
comprobador debe recibir afirmaciones incorrectas en las pruebas? ¿Qué queda sin
demostrar cuando todas las referencias del corpus coinciden?

Decisión: [ADR 0013](adr/0013-alias-de-funciones-por-asignacion.md).
