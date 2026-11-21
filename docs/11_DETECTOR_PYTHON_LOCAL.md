# Primer detector Python local

## Problema y vocabulario

Hasta esta capa las señales de SentinelForge eran ficticias. Ahora se puede inspeccionar un archivo Python real, elegido explícitamente desde la CLI, con una regla estática pequeña. **SAST** significa análisis estático de seguridad: leer la estructura del código sin ejecutarlo. Un **AST** es el árbol de sintaxis que permite distinguir una llamada de un comentario o una cadena.

La regla `SF-PY-001`, versión 1.0, observa llamadas reconocidas de `subprocess` con el argumento literal `shell=True`. La documentación de Python explica que invocar el shell obliga a revisar el tratamiento de espacios y metacaracteres. La coincidencia merece revisión del origen del comando; no demuestra por sí sola inyección de comandos ni una vulnerabilidad explotable.

## Diseño y alcance

`AnalysisService.scan_local_file` es la entrada de aplicación. La CLI `scan-file` solo presenta su resultado y su código de salida. El lector valida una ruta relativa a la raíz local autorizada y entrega una instantánea de bytes; el detector analiza esos mismos bytes en un proceso hijo.

El reporte `LocalScanReport` tiene esquema `1.0`, discriminador `report_type=local_python_scan` e `is_demo=false`. Conserva la versión del detector y de Python, la ruta relativa, tamaño, SHA-256, ubicaciones y fingerprints reproducibles. Los fingerprints cambian cuando cambian el archivo, su ruta, el detector o la versión de Python. No incluyen fecha: repetir la misma entrada con las mismas versiones produce el mismo JSON.

Cada señal tiene `verification_status=unverified` y severidad `warning`. No hay investigador ni verificador de explotabilidad conectados a esta regla. Los reportes demo conservan su contrato y sus etiquetas ficticias; no se guardan señales reales en tablas demo. Esta primera entrega devuelve JSON a stdout y no persiste el resultado, no crea preguntas Monitor y no modifica SQLite.

## Cómo probarlo en PowerShell

Desde la raíz del repositorio, con la `.venv` ya existente:

```powershell
.\.venv\Scripts\python.exe -m sentinelforge.cli scan-file tests/fixtures/local_scan/shell_enabled.py
.\.venv\Scripts\python.exe -m sentinelforge.cli scan-file tests/fixtures/local_scan/shell_disabled.py
```

El primer caso debe devolver una señal y el segundo, ninguna. Ambos son casos de prueba controlados. La fixture positiva contiene una excepción de protección al final: el análisis funciona porque nunca importa ni ejecuta ese archivo.

Para un archivo propio, usar su ruta relativa a la raíz de trabajo actual, por ejemplo `src/aplicacion.py`. No se permiten prefijos `./`, rutas absolutas ni `..`. En Windows también se admite `src\aplicacion.py` y se devuelve una ruta normalizada con `/`. El adaptador de servicio admite una raíz explícita elegida por un llamador local confiable; no existe un endpoint HTTP que permita elegir rutas del host.

## Regla y limitaciones

Se reconocen `run`, `Popen`, `call`, `check_call` y `check_output`, importadas desde `subprocess` a nivel de módulo. Se admiten aliases como `import subprocess as sp` y `from subprocess import run as launch`. `shell=False`, la ausencia del argumento, cadenas y comentarios no generan esta señal.

La resolución es conservadora: un alias reasignado o sombreado puede excluirse por completo. También se omiten llamadas que aparecen antes del import en el orden del archivo, incluso dentro de una función definida antes de ese import. No se intenta resolver imports dinámicos, wrappers, valores calculados como `shell=enabled`, argumentos posicionales de `Popen` ni expansiones `**kwargs`. Tampoco se acredita que el módulo importado en ejecución sea el original, que la llamada sea alcanzable o que reciba datos no confiables. Los casos intencionales de shell pueden generar señales que requieren revisión.

**Cero señales no significa código seguro.** Esta regla no detecta otras familias de riesgo ni todos los usos del shell. Los casos positivos y negativos prueban el alcance declarado; no son una medición representativa de precision/recall sobre proyectos reales.

Las líneas y columnas son de base 1. Las columnas cuentan bytes UTF-8 y la posición final es exclusiva, conforme a los offsets del AST. El SHA-256 se calcula sobre los bytes originales, incluyendo un BOM o finales CRLF si existen. Solo se admite UTF-8, con BOM opcional.

## Entrada y modelo de amenazas

- Un archivo regular `.py` explícito, de hasta 65 536 bytes. No hay recursión de directorios, ZIP, extracción ni acceso a red.
- Se rechazan traversal, rutas absolutas/UNC, ADS de Windows, nombres de dispositivo, segmentos ocultos, enlaces simbólicos y reparse points, incluidos junctions.
- La lectura es acotada. Se comprueban identidad y metadatos antes y después para rechazar cambios detectables durante la captura.
- La raíz y sus padres deben estar bajo control del operador. Estas comprobaciones no son un sandbox de filesystem: sobre todo en Windows no eliminan todas las carreras con otro proceso que pueda cambiar directorios durante la apertura.
- El parser ejecuta únicamente el worker confiable del proyecto con el intérprete actual y `-I -S`; recibe el artefacto por stdin como datos. No carga su `PYTHONPATH`, plugins, imports ni instrucciones aparentes.
- Tiempo máximo del worker: 5 segundos. Máximo: 20 000 nodos y 100 señales. Superar un límite es error técnico, no un resultado limpio ni una lista truncada silenciosamente.
- El proceso separado contiene fallos del parser y permite terminarlo por tiempo; no impone una cuota dura de memoria ni aísla permisos de red o disco. Antes de aceptar uploads hostiles se necesitará aislamiento de recursos más fuerte.
- La salida no incluye código fuente, comandos, rutas absolutas ni mensajes de excepción del parser. Sí contiene ruta relativa y hash: revisar esos metadatos antes de compartir el JSON.

## Estados y errores

`COMPLETED` significa que esta inspección acotada terminó, con o sin señales. `ERROR` significa que no pudo completarse y contiene `errors`, con `signals=[]`. Se evita presentar un fallo técnico como ausencia de riesgo.

La CLI devuelve 0 al completar, incluso con señales. Devuelve 2 ante errores. Emite JSON ASCII con escapes Unicode para que los pipes de Windows no dependan de la página de códigos; al decodificar JSON se recuperan los textos originales. No hay gate automático de seguridad; el consumidor de CI debe evaluar su política explícitamente.

| Grupo | Códigos |
|---|---|
| Selección de archivo | `source_path_invalid`, `root_invalid`, `unsupported_file_type`, `source_not_found`, `source_unsafe_path`, `source_not_regular` |
| Lectura | `source_too_large`, `source_changed`, `source_read_failed` |
| Contenido | `invalid_encoding`, `invalid_python`, `source_too_complex`, `too_many_findings` |
| Worker | `parser_timeout`, `parser_unavailable`, `parser_failed`, `parser_invalid_output` |

Un rechazo anterior a la lectura no publica manifiesto ni fingerprint. Un error del parser conserva el manifiesto de los bytes recibidos, para correlacionar el intento sin reproducir su contenido.

## Verificación y aprendizaje

Las pruebas usan archivos y directorios temporales. Cubren señales positivas, negativos controlados, alias y sombreado, entradas inválidas, límites, enlaces, cambios durante lectura, errores del worker, reintentos reproducibles y equivalencia CLI/servicio. Se comprueba que analizar un archivo no lo ejecuta ni crea una base SQLite.

Validación local del 20 de noviembre de 2026, con Python 3.14.10 de la `.venv` existente: **212 pruebas aprobadas, 2 omitidas por capacidades del SO y Ruff limpio**. Las omisiones son la creación real de symlinks sin permiso de Windows y la prueba FIFO, cuya API no está disponible en Windows. El rechazo de reparse points sí se comprobó con metadatos simulados para raíz, directorio y archivo. Esta capa no se ha publicado ni ejecutado en CI remota.

La CLI real devolvió una señal en línea 7, columna 12 para `shell_enabled.py`, ninguna para `shell_disabled.py` y error `source_path_invalid` con salida 2 para `../outside.py`. Los JSON de comprobación quedaron en `.local/detector-evidence/`, ignorados por Git. Otra prueba ejecutó la CLI con salida cp1252 y un nombre de archivo japonés: el JSON ASCII conservó correctamente la ruta y la señal. Se corrigió además el orden import/llamada dentro de una misma línea y se añadieron sus casos de regresión.

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
```

Preguntas de repaso: ¿qué prueba `shell=True` y qué no? ¿Por qué una cadena que menciona esa llamada no cuenta? ¿Qué protege un hash y qué no? ¿Por qué un error del parser no puede devolverse como cero señales exitosas? ¿Qué falta para vincular esta señal a una investigación y a Monitor?

## Fuentes y decisión

- [Python: consideraciones de seguridad de subprocess](https://docs.python.org/3.11/library/subprocess.html#security-considerations).
- [Python 3.14: AST, offsets y límites del parser](https://docs.python.org/3.14/library/ast.html).
- [ADR 0006: detector local y contrato separado](adr/0006-detector-python-local.md).
