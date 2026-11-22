# Imports dentro de funciones: mejora medida sobre el mismo corpus

Esta capa conserva la comparación 1.0 → 1.1. La [mejora posterior de ámbito de parámetros](17_AMBITO_DE_PARAMETROS_Y_GUIA.md) documenta el motor 1.2 y su comparación sobre las mismas referencias.

## Problema y vocabulario

La primera evaluación encontró una señal omitida en este patrón:

```python
def launch(command):
    import subprocess
    return subprocess.run(command, shell=True)
```

El import es local a la función. La versión 1.0 del detector solo reconocía imports de módulo. Esta iteración amplía el **alcance léxico**: el lugar del código en el que un nombre tiene un vínculo establecido. No ejecuta la función ni resuelve qué módulo se cargaría realmente en ejecución.

## Diseño y tradeoffs

El detector 1.1 acepta `import subprocess`, alias de módulo y `from subprocess import ...` cuando son sentencias directas del cuerpo de la misma función y preceden a la llamada en el orden del código. Se incluyen funciones asíncronas y métodos. Una llamada dentro de una rama puede detectarse después de un import directo; su trazado conserva los límites de flujo de control existentes.

No se extiende la resolución a imports dentro de `if`, `try`, bucles u otros bloques, cierres, lambdas, comprensiones, decoradores o valores por defecto de otra función. Tampoco se resuelven alias creados por asignación. Se rechazan nombres reasignados, borrados, declarados `global`/`nonlocal`, parámetros que compiten con el alias, imports ambiguos y mutaciones visibles de atributos/subscripts del mismo nombre. Estas reglas son conservadoras y pueden omitir usos válidos.

La resolución de imports de módulo mantiene sus comprobaciones conservadoras anteriores. En particular, la omisión por un nombre ocultado en otra función sigue visible: esta entrega no corrige todos los ámbitos simultáneamente.

El comprobador 1.1 usa tablas de símbolos del compilador, la función contenedora, los imports originales, su orden y las mutaciones observables. No llama al resolver del detector. Rechaza también un import directo válido seguido de un import condicional que pueda sustituir su nombre. Las pruebas le presentan afirmaciones de escáner deliberadamente incorrectas para evitar que se limite a ratificarlas.

## Efecto de un import sobre el trazado

Detectar el nuevo caso no bastaba: las dos estrategias de trazado trataban cualquier import como una barrera. Ahora el investigador hacia atrás omite imports que no enlazan el nombre seguido. El comprobador hacia adelante elimina de su entorno solo los nombres que el import enlaza.

Así, `import subprocess` no corta el origen de `command`. En cambio, `import math as command` sustituye ese nombre: el recorrido queda desconocido/inconcluso, sin recuperar por error el parámetro inicial. Una asignación explícita posterior puede establecer un nuevo origen. No se siguen imports como fuentes de datos ni se ejecutan sus efectos.

## Versiones e historia

El detector, el corroborador, el investigador de argumentos y su comprobador emiten versión **1.1**. Los contratos mantienen su forma y admiten metadatos de componente 1.0 y 1.1; las revisiones históricas conservan sus versiones originales.

La versión del detector forma parte del fingerprint. Analizar de nuevo los mismos bytes y nombre con 1.1 crea un expediente distinto del generado con 1.0, en vez de sobrescribir sus señales. No hay migración SQLite: permanece el esquema 7. Se comprueban recuperación de revisiones antiguas, conservación de sus filas y reintentos con sus recibos originales.

Las señales siguen `unverified`, los expedientes con señales `PARTIAL` y el contexto humano separado. Un import reconocido, un patrón corroborado o un recorrido reproducido no confirma explotabilidad ni verifica identidad o declaraciones humanas.

## Evaluación sin cambiar las etiquetas

Se conserva íntegro el corpus `sf-py-001-local` 1.0 y su hash canónico:

`7b6e4d638246e2711d4934ab472b36671e7da03c7c6bf7e04d9db48ad1e63cbd`

El caso `local-import-gap` permanece en el grupo `boundary`: no se reclasifica ni se cambia su referencia para mejorar las cifras. Ahora se detecta, se corrobora y su trazado coincide con el parámetro esperado. Los otros dos casos de frontera continúan sin detectarse.

El gate de `evaluate` sigue las categorías del corpus 1.0. La regresión de esta capacidad nueva se controla además con sus pruebas específicas y con las expectativas actualizadas del test de evaluación; un `pass` del comando por sí solo no acredita todas las ampliaciones futuras del alcance.

| Medición sobre el mismo corpus | Motor 1.0 | Motor 1.1 |
|---|---:|---:|
| TP / FP / TN / FN por caso | 15 / 0 / 8 / 3 | 16 / 0 / 8 / 2 |
| Recall por caso | 83,3 % | 88,9 % |
| Señales localizadas | 16 / 19 | 17 / 19 |
| Cobertura y acuerdo total de trazado | 84,2 % | 89,5 % |
| Trazados inconclusos | 4 | 4 |
| Errores de entrada esperados reconocidos | 2 / 2 | 2 / 2 |

La precisión observada permanece en 100 % dentro de este corpus pequeño. No es una estimación sobre repositorios reales; las etiquetas siguen sin auditoría independiente. Los tiempos de cada ejecución se conservan como observaciones, sin afirmar una mejora de rendimiento.

## Uso y evidencia

Las interfaces existentes utilizan el mismo servicio; no se añaden comandos o endpoints:

```powershell
.\.venv\Scripts\python.exe -m sentinelforge.cli evaluate --format pretty
.\.venv\Scripts\python.exe -m sentinelforge.cli evaluate --format json
```

La comparación local conserva la línea base anterior y una ejecución nueva en `.local/evaluation/`, fuera de Git. El criterio es que coincidan el hash del corpus y las referencias: los casos antes coincidentes deben mantenerse y `local-import-gap` debe pasar de omitido a reproducido. No se añaden dependencias, instalaciones, servicios externos o ejecución de artefactos.

Las pruebas nuevas cubren alias de import, métodos, async, orden, UTF-8/BOM/CRLF, scopes independientes, imports condicionales, cierres, nombres sustituidos, afirmaciones de escáner incorrectas, efectos del import en ambos trazadores, no ejecución, compatibilidad histórica y el recorrido API/CLI completo. Se ejecutan además las pruebas previas del producto.

Resultado local del 21 de noviembre de 2026: **354 pruebas aprobadas, 2 omitidas por Windows y Ruff limpio**, con la `.venv` existente. La CLI real devolvió código 0. Se conservaron `.local/evaluation/local-imports-v1.1.json`, su vista de terminal y `local-imports-comparison.json`, que verifica el mismo hash de corpus, una mejora y ninguna pérdida entre las referencias antes coincidentes.

Se reinició el servidor local para cargar los contratos 1.1 junto con los workers actualizados. `/health` respondió correctamente y OpenAPI anunció el detector 1.1; un expediente histórico siguió devolviendo revisión 3 y metadatos 1.0 sin cambios. No se crearon nuevos expedientes para esta comprobación.

## Nota académica

La mejora se eligió por una omisión observada y se midió sin mover las referencias. Aumentar la detección requería también contrastar el nuevo vínculo y mantener correcto el recorrido del dato. Quedan pendientes el ocultamiento en otra función y los alias creados por asignación; cada uno necesita su propio diseño y medición.

Preguntas: ¿por qué un import posterior no justifica una llamada anterior? ¿Qué distingue el import directo del condicional? ¿Por qué `import math as command` invalida el origen del parámetro? ¿Por qué conservar las etiquetas permite comparar versiones? ¿Por qué una señal adicional no demuestra una vulnerabilidad adicional?

Decisión: [ADR 0011](adr/0011-imports-locales-y-compatibilidad.md).
