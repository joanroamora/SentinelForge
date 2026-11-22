# Evaluación seleccionable y corpus de desafío

Esta página conserva la medición inicial del desafío con el motor 1.3. La
[ampliación 1.4](20_ALIAS_LOCALES_DE_FUNCIONES.md) resuelve dos de sus fronteras
sobre las mismas referencias.

## Problema y vocabulario

El motor 1.3 coincide con las 19 señales de referencia del corpus original. Esa
cifra describe un conjunto pequeño de desarrollo; hace falta exponer más
fronteras antes de decidir la siguiente ampliación. Un **corpus de desafío**
reúne ejemplos adicionales que pueden revelar omisiones aunque la referencia
anterior siga pasando. No es una auditoría independiente ni una muestra
representativa de repositorios reales.

Esta capa añade selección de conjuntos empaquetados mediante CLI y servicio.
El detector y el corroborador continúan en 1.3, los trazadores en 1.1 y SQLite
en esquema 7. No cambia la resolución del código analizado.

## Referencias separadas y versionadas

| Opción | Identidad | Versión | Casos | Señales esperadas |
|---|---|---|---:|---:|
| `baseline` | `sf-py-001-local` | 1.0 | 28 | 19 |
| `challenge` | `sf-py-001-challenge` | 1.0 | 20 | 13 |

`baseline` sigue siendo la selección predeterminada. Conserva sus fuentes,
etiquetas, categorías y hash canónico:

`7b6e4d638246e2711d4934ab472b36671e7da03c7c6bf7e04d9db48ad1e63cbd`

El conjunto nuevo está en `src/sentinelforge/data/evaluation_challenge_v1.json`.
Su hash se fijó antes de ejecutar el motor contra él:

`32ec0eecb77c3e50a6619187226417df54a6fdba858dd9f5e4764d1e8d5883fc`

Las referencias se redactaron desde la sintaxis prevista y las posiciones de
tokens, sin obtenerlas de las salidas del detector o los trazadores. Un auxiliar
de autoría calculó offsets UTF-8 a partir de líneas y tokens explícitos. Se
crearon con conocimiento del producto y permanecen etiquetadas
`not_independently_audited`; se necesita revisión externa antes de atribuirles
independencia o calidad general.

El desafío separa doce casos `in_scope` (seis positivos y seis negativos de la
regla), seis `boundary` positivos y dos `input_error`. Uno de los casos tiene
dos señales en funciones independientes: localizar una no acredita localizar
ambas. Se incluyen Unicode/BOM/CRLF, imports locales en async, argumento `args=`,
`True` entre paréntesis, alias asignados, nombres ocultos, funciones sustituidas,
código aparente en cadenas y texto con instrucciones que debe tratarse como
dato. Una excepción de protección delata una ejecución accidental.

## Diseño y contratos

`BuiltinCorpus` define las opciones válidas. Un registro interno asocia cada
opción a un recurso y una identidad esperada; la CLI no recibe rutas de corpus
arbitrarias. La selección desconocida se rechaza antes de leer archivos. Una
identidad equivocada dentro de un recurso se rechaza en vez de sustituir
silenciosamente la referencia seleccionada.

`AnalysisService.evaluate_builtin_corpus` carga el conjunto elegido y llama al
mismo evaluador y componentes existentes. Continúan los límites de 512 KiB,
64 casos y 120 segundos por ejecución, junto con los límites de los workers.
No crea expedientes, preguntas, recibos ni bases de datos. La salida conserva
metadatos y referencias, sin código ni valores literales. Esta capa se ofrece
por CLI; no añade endpoints ni una pantalla de evaluación.

El componente evaluador emite versión **1.1** y admite reportes 1.0. La forma del
contrato sigue en esquema 1.0; los algoritmos de métricas y su significado se
conservan. Cada informe identifica corpus, versión, hash y motor. Los porcentajes
de dos conjuntos diferentes no deben interpretarse como una regresión del
detector: cambian las entradas. Una comparación de versiones del motor debe
mantener el mismo hash de corpus.

## Ejecución y lectura de resultados

Desde la raíz, con la `.venv` existente:

```powershell
.\.venv\Scripts\python.exe -m sentinelforge.cli --no-animation evaluate --corpus baseline --format pretty
.\.venv\Scripts\python.exe -m sentinelforge.cli --no-animation evaluate --corpus challenge --format pretty
.\.venv\Scripts\python.exe -m sentinelforge.cli evaluate --corpus challenge --format json
```

Con el motor 1.3 se localizan 7/13 señales del desafío y se trazan esos siete
objetivos con acuerdo frente a sus referencias. Por caso: 6 TP, 6 TN, 0 FP y
6 FN entre 18 entradas elegibles; los dos errores esperados quedan separados.
Los doce casos en alcance coinciden. El corpus original mantiene 19/19 señales
y sus cuatro trazados inconclusos.

Las seis fronteras permanecen positivas en las referencias, aunque el motor no
emita señales:

| Casos | Capacidad pendiente |
|---|---|
| `function-assignment-global-import`, `function-assignment-local-import` | Captura del alias dentro de una función |
| `two-hop-module-alias` | Cadena de dos alias de función |
| `annotated-module-capture` | Captura mediante asignación anotada |
| `constant-true-conditional-import` | Import en una rama constante verdadera |
| `unrelated-local-assignment` | Distinguir una asignación local en otra función |

El indicador `pass` y el código 0 continúan refiriéndose a los casos **dentro de
alcance** y al manejo de errores esperados. Las seis omisiones de frontera
siguen en `boundary_gaps`, métricas y tabla de discrepancias. No son negativos
reclasificados para mejorar cifras. Los códigos 1 y 2 mantienen sus significados
de discrepancia en alcance y error técnico. Esto es un gate de evaluación del
producto, no una política de seguridad para otros repositorios.

## Pruebas y aprendizaje

Las pruebas fijan los hashes de ambos conjuntos, verifican sus identidades,
protecciones de tamaño/JSON y rechazo de rutas externas. Se comprueban selección
en CLI, formatos JSON/terminal, recuperación de metadatos 1.0, métricas y omisiones
reales, no persistencia ni copia de código. El corpus se localiza también desde
otro directorio de trabajo.

La medición y sus vistas de terminal se conservan en `.local/evaluation/`, fuera
de Git. Los conjuntos empaquetados y las expectativas de sus pruebas sí se
versionan. La construcción del wheel, CI remota y auditoría independiente de
estas etiquetas siguen pendientes; no se instalaron nuevas dependencias.

Validación local del 21 de noviembre de 2026: **450 pruebas aprobadas, 2 omitidas
por capacidades de Windows y Ruff limpio**, con Python 3.14.10 de la `.venv`.
La suite completa tardó 100,16 s y utilizó acceso a sockets locales para las
pruebas de asyncio de Windows, con bases temporales. La CLI real terminó con
código 0 para ambos corpus, conservando los siguientes archivos locales:

- `corpora-baseline-v1.1.json` y `corpora-challenge-v1.1.json`: resultados por caso.
- `corpora-validation-v1.1.json`: hashes, métricas y comparación de la referencia
  original con su medición previa, sin pérdidas observadas.
- `corpora-baseline-v1.1-terminal.txt` y `corpora-challenge-v1.1-terminal.txt`:
  presentación de los mismos resultados, sin repetir el análisis.
- `challenge-cli-help.txt`: opciones expuestas por el comando real.

El desafío mantiene el hash fijado antes de medirlo. El conjunto original
conserva fuentes, expectativas y métricas frente a su informe anterior. Los
informes de ambos conjuntos identifican el mismo hash del motor. La aplicación
web y su base existente no se modificaron para crear esta evidencia.

Lo aprendido: completar una referencia permite pasar a una evaluación más
exigente, conservando la anterior. Las nuevas omisiones orientan la próxima
iteración; los porcentajes de conjuntos distintos requieren denominadores
explícitos.

Preguntas de repaso: ¿por qué 19/19 no describe todos los usos de subprocess?
¿Qué identifica el hash del corpus? ¿Cómo puede `pass` coexistir con seis
omisiones? ¿Por qué `shell=1` es negativo para esta regla sin acreditar seguridad?
¿Qué evidencia falta para llamar independiente a un conjunto de referencias?

Decisión: [ADR 0014](adr/0014-evaluacion-con-corpus-seleccionables.md).
