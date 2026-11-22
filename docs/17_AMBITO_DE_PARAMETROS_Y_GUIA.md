# Ámbito de parámetros y guía de las capas implementadas

Este documento conserva la entrega 1.2. La [ampliación 1.3](18_ALIAS_POR_ASIGNACION.md)
añade alias de funciones por una asignación simple en el módulo y mantiene las
mediciones históricas de esta página.

## El problema, explicado con un ejemplo

```python
import subprocess

def unrelated(subprocess):
    return subprocess

def launch(command):
    return subprocess.run(command, shell=True)
```

Un **parámetro** es el nombre con el que una función recibe un valor. El **ámbito** (*scope*) determina dónde tiene significado ese nombre. Dentro de `unrelated`, `subprocess` designa el valor recibido. Ese parámetro no sustituye al módulo importado que utiliza la función independiente `launch`.

El motor 1.1 bloqueaba conservadoramente el nombre en todo el archivo y omitía la llamada de `launch`. El motor 1.2 distingue los parámetros de otras funciones. Si el parámetro pertenece a la propia función de la llamada, o a una función exterior que la contiene, sigue impidiendo justificar el vínculo con el módulo estándar.

## Diseño de la mejora

El detector identifica mediante AST la función propietaria de cada parámetro y las funciones que contienen cada llamada. Para resolver imports de módulo, ignora las declaraciones de parámetros de otras funciones nombradas. Conserva los bloqueos por asignaciones, imports competidores, declaraciones, mutaciones de atributos, lambdas y parámetros de tipo. Es una ampliación pequeña: no pretende resolver todos los ámbitos de Python.

El corroborador separado usa las tablas de símbolos del compilador. Solo omite un parámetro de una función independiente si no aparece también asignado, importado o ligado a un namespace. Un parámetro usado en el ámbito de la llamada no se omite. Las mutaciones visibles y escrituras globales mantienen las comprobaciones anteriores. El corroborador no llama al resolver del detector.

La mejora se limita a parámetros que no tienen otros enlaces o mutaciones competidores. Por ejemplo, una asignación a un nombre igual dentro de otra función todavía puede causar una omisión conservadora. Cierres complejos, declaraciones `global`/`nonlocal`, lambdas y parámetros de tipo no reciben una resolución general nueva.

El detector y el corroborador emiten versión **1.2**, manteniendo la lectura de metadatos 1.0 y 1.1. Los trazadores continúan en 1.1: su algoritmo no cambia. El fingerprint incorpora la versión del detector, por lo que un resultado nuevo no sustituye una revisión histórica. SQLite conserva el esquema 7.

## Medición sobre las mismas referencias

El corpus 1.0 no cambia, ni sus fuentes, etiquetas o categorías. Su SHA-256 canónico sigue siendo:

`7b6e4d638246e2711d4934ab472b36671e7da03c7c6bf7e04d9db48ad1e63cbd`

| Resultado en los 28 ejemplos de desarrollo | Motor 1.0 | Motor 1.1 | Motor 1.2 |
|---|---:|---:|---:|
| Señales y recorridos reproducidos | 16/19 | 17/19 | 18/19 |
| Omisiones por caso | 3 | 2 | 1 |
| Falsos positivos observados por caso | 0 | 0 | 0 |
| Recall por caso | 83,3 % | 88,9 % | 94,4 % |
| Cobertura/acuerdo de trazado | 84,2 % | 89,5 % | 94,7 % |
| Trazados inconclusos | 4 | 4 | 4 |

La mejora esperada es `unrelated-shadow-gap`; `local-import-gap` continúa coincidiendo. La omisión restante es el alias creado por asignación, por ejemplo `runner = subprocess.run; runner(...)`. Los casos siguen en el grupo de frontera original para preservar la comparación. El gate de `evaluate` se refiere a las categorías del corpus; las pruebas específicas también vigilan la capacidad nueva.

Estas cifras no significan que el proyecto tenga 94,7 % de seguridad o esté 94,7 % terminado. Miden coincidencias con referencias sintéticas, pequeñas y todavía sin auditoría independiente. El producto no confirma explotabilidad a partir de ellas.

## Qué capas existen hoy y qué hace cada una

| Capa | Explicación para quien empieza |
|---|---|
| Entorno `.venv` | Mantiene las bibliotecas del proyecto separadas de otros proyectos. No es una máquina aislada para ejecutar código peligroso. |
| Motor compartido | `AnalysisService` reúne las operaciones del producto. CLI, API y web lo utilizan para mantener el mismo comportamiento. |
| Entrada de un archivo | Recibe un `.py` autorizado de hasta 64 KiB. La lectura local comprueba rutas y enlaces; la web recibe bytes elegidos por el usuario. |
| Detector estático | Lee la estructura del código sin ejecutarlo. Busca una regla concreta: usos reconocidos del literal `shell=True` en `subprocess`. |
| Expediente SQLite | Guarda resultados, hash, revisiones y eventos. Permite recuperar el historial después de cerrar y volver a abrir el programa. |
| Idempotencia y concurrencia | Repetir un envío con su UUID conserva el resultado; guardar cambios simultáneos no debe borrar una respuesta que llegó durante otra operación. |
| Corroboración | Recibe de nuevo la fuente, compara su hash y contrasta la ubicación, el import y el patrón con otra implementación. |
| Trazado del argumento | Sigue asignaciones simples para explicar si el comando procede de un literal, parámetro o llamada, o queda desconocido. Otra estrategia contrasta los pasos. |
| Contexto humano / Monitor mínimo | Guarda una pregunta y una primera respuesta, con autor/rol declarados y fecha. La afirmación se conserva sin convertirse automáticamente en prueba técnica. |
| Ciclo demo recuperable | Demuestra estados, checkpoints e investigación/verificación deterministas con datos ficticios. No integra todavía agentes LLM ni un grafo real de análisis completo. |
| CLI, API y web | Ofrecen terminal, endpoints y pantalla local. Ya hay tablas/árboles, animación SF, carga de archivo, historial, revisiones y descarga JSON. |
| Evaluación | Compara el motor con 28 ejemplos etiquetados y muestra aciertos, omisiones, inconclusos y tiempos, incluyendo sus limitaciones. |
| Calidad y Git | pytest verifica comportamientos; Ruff revisa código; ramas/commits/PR permiten revisar cambios. La CI del repositorio está configurada para Linux/Windows y dos Python. |

**Ejemplo del recorrido real:** eliges un archivo → se valida y detecta una señal → se crea un expediente → aportas el original para corroborar y trazar → puedes añadir contexto humano → consultas las nuevas revisiones desde las interfaces. El contexto puede llegar antes o después de las comprobaciones técnicas.

El hash es una huella digital de los bytes; ayuda a comprobar que se volvió a aportar el mismo archivo. Un reporte parcial conserva asuntos pendientes. Una señal es una observación que merece revisión: no equivale por sí sola a una vulnerabilidad demostrada.

## Qué continúa pendiente

Sigue pendiente analizar proyectos completos, ampliar familias de reglas y dependencias, resolver flujo entre funciones/archivos, verificar evidencias humanas y permitir más preguntas por hallazgo. También faltan agentes LLM opcionales, políticas/SARIF para analizar otros repositorios en CI y controles de producción como autenticación, permisos y PostgreSQL. GCP y la ejecución aislada de artefactos requieren una etapa posterior y autorización propia.

La CI de nuestro repositorio comprueba que el producto funciona; todavía no es un servicio que revise automáticamente la seguridad de cualquier repositorio externo. Las últimas capas locales necesitan publicación autorizada y nueva CI remota antes de atribuirles esa validación.

## Pruebas y aprendizaje

Se comprueban alias de módulo/función, funciones asíncronas, métodos, nombres Unicode, lectores globales anidados y parámetros que realmente ocultan al módulo. Las afirmaciones de escáner incorrectas también se envían al comprobador para verificar su rechazo. Las pruebas previas conservan los controles por mutación y la compatibilidad de revisiones/recibos 1.0 y 1.1. No se ejecutan las fuentes.

Resultado local del 21 de noviembre de 2026: **370 pruebas aprobadas, 2 omitidas por Windows y Ruff limpio**, mediante la `.venv` existente. La CLI real devuelve código 0. `.local/evaluation/parameter-scope-v1.2.json`, su vista de terminal y `parameter-scope-comparison.json` conservan la medición, fuera de Git. La comparación con 1.1 comprueba el mismo hash del corpus, la mejora de `unrelated-shadow-gap`, ninguna pérdida entre las referencias antes coincidentes y la omisión restante por alias asignado.

El servidor local se reinició con los contratos 1.2. `/health` respondió correctamente, OpenAPI mostró el detector 1.2 y la consulta de un expediente histórico conservó revisión 3 y detector 1.0. No se crearon análisis nuevos para comprobarlo ni se migró la base de datos.

Preguntas de repaso: ¿por qué dos funciones pueden utilizar el mismo nombre para cosas distintas? ¿Cuándo sí puede influir un parámetro exterior? ¿Qué diferencia hay entre una señal y una vulnerabilidad confirmada? ¿Qué demuestra el hash y qué queda sin probar? ¿Por qué el porcentaje del corpus no representa seguridad general?

Decisión: [ADR 0012](adr/0012-parametros-de-funciones-independientes.md).
