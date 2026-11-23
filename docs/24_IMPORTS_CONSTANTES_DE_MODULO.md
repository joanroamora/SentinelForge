# Imports constantes de módulo: motor 1.8

## Problema y vocabulario

El desafío de desarrollo conserva una omisión en este patrón:

```python
if True:
    import subprocess

def launch(command):
    return subprocess.run(command, shell=True)
```

El motor 1.7 solo admite imports directos en el cuerpo del módulo. Esta capa
reconoce además una forma acotada de **rama constante** (*constant branch*).
No evalúa código, importa módulos del artefacto ni implementa un análisis general
de flujo de control.

## Diseño y tradeoffs

Se admite el import cuando su padre es un `if` directamente en el módulo y:

- La condición es el literal booleano `True`, también entre paréntesis.
- No existe `else`.
- Todo el cuerpo está formado por sentencias `import` o `from ... import ...`.

Se conservan imports directos, las cinco funciones canónicas de subprocess y
los alias y capturas ya admitidos. El orden se compara con la posición real
del import dentro del bloque; llamadas anteriores continúan rechazadas. Una
función definida antes del import también conserva esa restricción léxica.

El alcance excluye `if 1`, `if enabled`, `if not False`, comparaciones o llamadas,
así como ramas anidadas, `elif`, `else`, bloques con otras sentencias y imports
condicionales dentro de funciones. Esas formas pueden contener patrones válidos
que el motor siga omitiendo. No se cambian sus etiquetas para ocultar el límite.

El detector enumera imports admisibles en el módulo y utiliza su resolución
existente de vínculos y mutaciones. El corroborador inspecciona por separado la
ubicación de cada import y sus padres en el AST, contrasta las declaraciones
originales y consulta las tablas de símbolos. No recibe la lista del detector
ni importa su implementación.

Reconocer esta declaración no prueba que el import se complete en ejecución,
que cargue el módulo estándar efectivo, que se alcance la llamada o que exista
explotabilidad. Las decisiones continúan limitadas al patrón estático.

## Rechazo de imports competidores

Una prueba con señal inventada reveló un defecto previo del corroborador: un
import directo podía justificar el nombre aunque apareciera después un import
condicional competidor. El detector ya omitía conservadoramente ese caso.

El corroborador 1.8 rechaza imports no admitidos que puedan ligar el mismo
nombre, además de conflictos entre imports admitidos. También rechaza imports
estrella al resolver un vínculo de módulo. Los bloqueos se conservan aunque el
import competidor esté en `if False` u otro ámbito: no se incorpora una prueba
general de alcanzabilidad ni se relajan todos los ámbitos a la vez.

Se prueban esas afirmaciones incorrectas aunque el detector no produzca señales,
para evitar que una ausencia de resultados deje sin ejercitar al corroborador.
Las implementaciones comparten CPython y supuestos estáticos; no constituyen
verificación formal ni una auditoría independiente de las referencias.

## Alcance del trazado conservado

Los trazadores siguen en 1.2. Las llamadas directas desde una función y las
capturas admitidas en el módulo conservan el recorrido esperado del argumento.
Esta capa no transforma el `if True` en una nueva regla general de trazado.

Una captura **local por atributo** desde ese nuevo import puede detectarse y
corroborarse, pero su argumento sigue inconcluso: la excepción del trazador que
omite `runner = sp.run` requiere un import directo anterior y no reconoce este
nuevo bloque de módulo. Ambas estrategias conservan el origen desconocido.
La prueba fija esa frontera en vez de inventar un origen de parámetro.

## Versiones e historia

| Componente | Versión emitida | Lectura histórica |
|---|---|---|
| Detector / corroborador | 1.8 | 1.0–1.7 |
| Investigador / comprobador del argumento | 1.2 | 1.0, 1.1 |
| Evaluador | 1.1 | 1.0 |

Las formas de contratos y SQLite 7 se conservan. La versión nueva cambia el
fingerprint de análisis nuevos y permite leer las revisiones y recibos previos,
sin reescribirlos. La recuperación cubre metadatos 1.7 con trazado 1.2.

CLI, API y web reciben la capacidad mediante el mismo servicio. La integración
crea y corrobora un caso con el nuevo import, traza, registra contexto humano y
recupera el trazado con su UUID después de responder. Señales y declaraciones
siguen `unverified`, el expediente sigue `PARTIAL` y la primera revisión conserva
su contenido.

## Uso local y límites

Desde la raíz, con el entorno existente:

```powershell
.\.venv\Scripts\python.exe -m sentinelforge.cli scan-file tests/fixtures/local_scan/constant_module_import.py
.\.venv\Scripts\python.exe -m sentinelforge.cli --no-animation evaluate --corpus baseline --format json
.\.venv\Scripts\python.exe -m sentinelforge.cli --no-animation evaluate --corpus challenge --format pretty
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
```

La fixture es sintética y contiene una excepción de protección. Se procesa como
datos y no se ejecuta. `scan-file` no crea expedientes; `scan` o el selector de
archivos de la web permiten persistir el resultado.

Continúan 64 KiB de entrada, 20 000 nodos, 100 señales, ocho capturas de módulo,
cinco segundos por worker y los límites del trazado. No se instalan dependencias,
crean migraciones, invocan proveedores LLM, ejecutan artefactos o modifican
servicios externos. El proceso del parser no es un sandbox de permisos ni una
cuota dura de memoria.

## Comparación sin cambiar las referencias

Ambos corpus conservan fuentes, expectativas, categorías y hash:

- Baseline 1.0: `7b6e4d638246e2711d4934ab472b36671e7da03c7c6bf7e04d9db48ad1e63cbd`.
- Challenge 1.0: `32ec0eecb77c3e50a6619187226417df54a6fdba858dd9f5e4764d1e8d5883fc`.

Antes de editar se verificó que las mediciones previas correspondían al hash
del motor 1.7 y se conservaron los cuatro archivos de implementación modificados.
La comparación final contrasta las referencias y hashes de cada fuente, además
de conservar las coincidencias previas.

| Medición sobre challenge | Motor 1.7 | Motor 1.8 |
|---|---:|---:|
| Señales localizadas | 12/13 | 13/13 |
| Recorridos coincidentes con la referencia | 12/13 | 13/13 |
| Omisiones por caso | 1 | 0 |
| Falsos positivos observados por caso | 0 | 0 |

Mejora `constant-true-conditional-import`, sin modificar su etiqueta ni categoría.
Baseline conserva 19/19 señales y recorridos coincidentes, incluidos cuatro
resultados inconclusos. Se reconocen los dos errores esperados de cada corpus
y no se pierden coincidencias anteriores. Las categorías de frontera originales
siguen identificadas aunque `boundary_gaps` ahora esté vacío.

Las referencias siguen siendo sintéticas de desarrollo, sin auditoría
independiente. `pass` conserva su significado de acuerdo en alcance: no certifica
seguridad, ausencia general de falsos negativos o cobertura sobre repositorios.
Las pruebas de presentación mantienen una omisión deliberada en un reporte de
prueba para comprobar que una futura discrepancia siga siendo visible.

## Evidencia y nota académica

Validación local del 22 de noviembre de 2026: **759 pruebas aprobadas, 2 omitidas
por capacidades de Windows y Ruff limpio**, con Python 3.14.10 de la `.venv`.
La suite completa tardó 220,04 s y utilizó bases temporales y sockets locales
para las pruebas HTTP de Windows. Las 57 pruebas específicas también pasan.

Los casos cubren las cinco llamadas, ambas formas de import, alias, cadenas,
orden, métodos/async, Unicode/BOM/CRLF, bloques y condiciones no admitidas,
mutaciones, competidores y afirmaciones incorrectas. Dos casos de detección y
la afirmación inventada con import competidor fallaron antes del cambio; pasan
después. Se mantiene la prueba de cien señales y la caché acotada de la capa 1.7.

La CLI real terminó con código 0 en ambos corpus y en la fixture, que localiza
una llamada en línea 9, columna 12 y final exclusivo en columna 49. La evidencia
ignorada por Git está en `.local/evaluation/`:

- `constant-import-*-before-v1.7.json` y `constant-import-before-v1.7/`: mediciones
  y archivos previos contrastados con el motor al comenzar.
- `constant-import-*-v1.8.json` y `constant-import-comparison.json`: mediciones
  y comparación de referencias, fuentes, categorías y coincidencias conservadas.
- `constant-import-tests-v1.8.txt`, `constant-import-scan-v1.8.json` y
  `constant-import-delta-v1.7.patch`: suite, fixture y delta de implementación.
- `constant-import-api-before.json` y `constant-import-api-after.json`: OpenAPI
  anuncia detector/corroborador 1.8; el expediente histórico consultado conserva
  revisión 3 y una huella de JSON idéntica.

No se crearon expedientes nuevos ni se migró la base real para esa comprobación.
La integración conserva la revisión original y recupera el trazado después de
registrar contexto humano sin verificar. Las capas 1.5–1.8 siguen locales,
sin commits ni publicación, en `codex/constant-true-module-imports`. La CI remota
de estas capas, el wheel y la auditoría independiente siguen pendientes.

Lo aprendido: una regla literal pequeña permite resolver una omisión medida sin
convertir condiciones arbitrarias en hechos. El comprobador también necesita
contraejemplos que el detector no emita. Resolver todas las referencias actuales
es motivo para exigir ejemplos nuevos e independientes, no para extrapolar una
conclusión general de seguridad.

Preguntas de repaso: ¿por qué `True` y `enabled` reciben trato distinto? ¿Qué
import puede sustituir el nombre observado? ¿Por qué otra declaración en una
rama muerta sigue bloqueando conservadoramente? ¿Por qué detectar y corroborar
no completan automáticamente el trazado? ¿Qué evidencia falta después de 13/13?

Decisión: [ADR 0019](adr/0019-imports-constantes-de-modulo.md).
