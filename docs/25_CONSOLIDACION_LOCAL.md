# Consolidación local: una validación con evidencia vinculada al código

## Problema y vocabulario

Las capas 1.5–1.8 mejoraron el detector, pero sus pruebas y mediciones se
conservaron en ejecuciones separadas. Antes de integrarlas hace falta comprobar
el conjunto y saber qué estado del código produjo los resultados.

Una **puerta de calidad** (*quality gate*) agrupa comprobaciones que deben pasar
para aceptar la validación. Un **manifiesto** es el índice de esa evidencia:
identifica el código, los pasos ejecutados y los archivos de resultados.
Una huella SHA-256 permite comparar contenidos; no acredita quién los revisó.

## Diseño y tradeoffs

`scripts/validate_local.py` es una herramienta de desarrollo, separada del motor
de análisis. Usa la biblioteca estándar y los componentes ya instalados en la
`.venv` del repositorio. Rechaza un intérprete distinto antes de crear evidencia.
La CLI/API/web y sus contratos de producto permanecen en sus versiones actuales.

El comando ejecuta, en este orden y sin stdin:

1. Ruff sobre el repositorio.
2. La suite completa de pytest.
3. La CLI JSON de evaluación con `baseline`.
4. La CLI JSON de evaluación con `challenge`.

Un paso fallido detiene los siguientes. Se conservan su salida estándar, sus
diagnósticos y su código de salida. Los pasos pendientes quedan `not_run`.
Un timeout, una interrupción o un error de lectura no se convierte en éxito.
Los límites son 60 s para Ruff, 600 s para pytest y 150 s para cada CLI; los
presupuestos internos del evaluador y los workers continúan vigentes.

Además del código de salida, se valida cada JSON con `EvaluationReport`. Se
contrasta identidad, versión, hash y listado de casos del corpus; fuentes,
categorías y referencias por caso; motor evaluado; y métricas recalculadas
desde los resultados por caso. Se rechazan reportes truncados, mayores de 2 MB,
parciales, inconsistentes o que declaren una auditoría no admitida por el contrato.
La política de aceptación del benchmark se conserva: las omisiones de frontera
siguen visibles aunque los casos dentro de alcance coincidan.

Las evaluaciones identifican el mismo motor capturado al inicio. Una segunda
huella compara implementación, pruebas, datos, recursos web, `pyproject.toml`,
workflows y el propio comando al terminar. Se normalizan CRLF a LF; se excluyen
cachés y bytecode. Documentación, `.venv`, bases, logs y evidencia generada no
forman parte de esa huella. Un cambio observado invalida la ejecución completa.

## Uso y evidencia

Windows PowerShell, con el entorno existente:

```powershell
.\.venv\Scripts\python.exe scripts/validate_local.py
```

Linux/macOS:

```bash
./.venv/bin/python scripts/validate_local.py
```

Cada ejecución crea `.local/validation/<fecha-UTC>-<identificador>/` y anuncia su
ruta. No sobrescribe una ejecución anterior. La carpeta contiene:

- `manifest.json`: esquema 1.0, estado, tiempos, Python, huellas, pasos y límites.
- `ruff.log`, `pytest.log` y sus archivos `*.stderr.log`.
- `baseline.json`, `challenge.json` y sus diagnósticos, si llegaron a ejecutarse.

Los JSON conservan metadatos de evaluación, sin copiar fuentes ni literales de
los corpus. El manifiesto incluye la huella de cada reporte y mantiene
`is_independent_audit=false`, `wheel_verified=false` y `remote_ci_verified=false`:
este comando no certifica esas fases. Los logs de pytest son diagnósticos de
desarrollo y pueden mostrar fragmentos de pruebas cuando fallan; no usar secretos
reales en ellas ni publicar evidencia sin revisarla.

Códigos de salida: **0** si pasan todos los pasos y sus comprobaciones; **1** si
una herramienta termina con discrepancias; **2** por error técnico, evidencia
inconsistente o fuentes cambiantes; **130** por interrupción. Una carpeta
parcial nunca constituye una validación aprobada; consultar el manifiesto.

La CI existente Linux/Windows × Python 3.11/3.14.10 invoca este mismo comando
después de su instalación efímera en `.venv`. No se añaden acciones, permisos,
publicación ni dependencias. Los archivos permanecen en el runner; no hay subida
automática de artefactos. Un fallo imprime el tramo final de sus diagnósticos.

## Validación de esta capa

Las pruebas específicas cubren entorno incorrecto, éxito, fallos en cada paso,
timeout, interrupción, evidencia incompleta o corrupta, mezcla de identidades,
métricas inconsistentes, cambios de código, preservación de ejecuciones previas
y rechazo de destinos fuera del repositorio. Los casos de protocolo usan
subconjuntos negativos acotados; la ejecución real del comando mide los dos
corpus completos, sin modificar fuentes, etiquetas ni categorías.

Validación local del 22 de noviembre de 2026, con Python 3.14.10 de `.venv`:
**789 pruebas aprobadas, 2 omitidas por capacidades de Windows y Ruff limpio**.
Las 30 pruebas específicas pasan. La suite completa tardó 179,70 s; la puerta
completa, aproximadamente 193,37 s, terminó con código 0.

Ambas evaluaciones reales conservaron sus fuentes, etiquetas y categorías:
baseline localizó 19/19 señales y mantuvo cuatro trazados inconclusos; challenge
localizó 13/13, sin inconclusos. Sus informes identifican el mismo motor 1.8,
con huella `bdb79b0964be7a83e78f95a7cadc916c0109edb2a1e725d6493cc5f5ac1325cd`.
La huella de fuentes al inicio y final coincide:
`92938b78c747ff3dc2171fd982abc29a26aace767a36bbd2f440cdf6cda71427`.

Los archivos están en `.local/validation/20261123T051603Z-79e25e05/`: la fecha
de la carpeta es UTC, correspondiente al día 22 en la zona local. Incluyen el
manifiesto, los logs y los dos reportes JSON con sus huellas. La primera
ejecución bajo el sandbox quedó incompleta al bloquearse el socket interno de
`asyncio` de Windows. Una comprobación mínima confirmó esa restricción; se
detuvo la ejecución y se repitió con permiso para sockets locales. La evidencia
aprobada corresponde únicamente a la repetición completa.

Se comprobó también la sintaxis de los archivos nuevos con la gramática de
Python 3.11; esa comprobación no sustituye la ejecución real de la matriz CI.
Las capas 1.5–1.8 y este gate se agrupan en `codex/local-quality-gate` para una
integración conjunta. Publicación y comprobación remota siguen pendientes.

## Límites y nota académica

Este es un control de integración local, no un nuevo detector ni una auditoría
independiente. La aplicación conserva detector/corroborador 1.8, trazadores 1.2,
evaluador 1.1 y SQLite 7. El comando ejecuta las pruebas de SentinelForge, que es
el producto confiable de este repositorio; no ejecuta tests ni código de proyectos
recibidos para analizar.

Las huellas no son firmas y solo comparan capturas de inicio y fin: no detectan
una modificación transitoria que se revierta entre ambas. Tampoco fijan todas
las dependencias o el sistema operativo. La construcción del wheel sigue
pendiente porque `.venv` no incluye el backend de construcción; no se instala
para resolverlo. También faltan CI remota de estas capas, revisión externa de
referencias y casos reservados representativos. No se crean recursos GCP.

Lo aprendido: muchos tests aprobados no bastan para saber si dos mediciones
corresponden a la misma implementación. Un código de salida cero necesita
acompañarse de resultados completos, coherentes e identificables.

Preguntas de repaso: ¿qué invalida una huella distinta? ¿Por qué se verifican
los JSON además del código de salida? ¿Qué significa `not_run`? ¿Por qué un
manifiesto no es una auditoría independiente? ¿Qué queda por probar del wheel?

Decisión: [ADR 0020](adr/0020-validacion-local-y-evidencia.md).
