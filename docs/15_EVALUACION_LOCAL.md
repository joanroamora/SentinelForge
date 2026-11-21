# Evaluación local de detección y trazado

## Problema y vocabulario

Una suite de pruebas demuestra comportamientos concretos, pero su número no describe cuánto detecta un analizador. Esta capa añade un **corpus**: un conjunto pequeño de ejemplos con referencias esperadas, y un evaluador que compara las salidas del motor sin modificar esas referencias.

Las etiquetas describen el patrón estático `SF-PY-001` y el recorrido de asignaciones, **no vulnerabilidades**. Por ejemplo, `shell=1` y `shell=enabled` son negativos para la regla del literal `True`; eso no demuestra que no invoquen un shell en ejecución. Los resultados no estiman la seguridad de un proyecto ni la precisión en código real.

## Referencias y alcance

El corpus `sf-py-001-local` 1.0 contiene **28 casos sintéticos** en `src/sentinelforge/data/evaluation_v1.json`. El código permanece como texto JSON y nunca se importa ni se ejecuta. Cada referencia declara ubicación, llamada canónica, origen esperado, pasos y resultado esperado del comprobador. Las ubicaciones se anotaron por línea y token, sin usar salidas del detector, investigador o verificador para generarlas.

Son referencias de desarrollo, creadas con conocimiento del motor: **no tienen auditoría independiente, muestreo representativo ni un conjunto reservado de evaluación**. Se registra `reference_review=not_independently_audited`. Revisarlas y ampliarlas con muestras independientes queda pendiente; no se presentan como verdad certificada.

| Grupo | Casos | Uso |
|---|---:|---|
| `in_scope` | 23 | 15 positivos, incluidos uno con dos señales, y 8 negativos del patrón |
| `boundary` | 3 | Patrones presentes cuya forma de import/alias supera el soporte actual |
| `input_error` | 2 | Sintaxis inválida y un byte sobre el límite de 64 KiB |

Se cubren literales, parámetros, alias de import, cadenas de asignación, reasignación temporal, argumento `args=`, resultados de llamadas, ramas, expresiones compuestas, llamadas de módulo, Unicode/BOM/CRLF, varias señales y texto con instrucciones aparentes. Una fixture incluye una excepción que delataría su ejecución accidental.

Las tres fronteras mantienen referencias positivas aunque el detector no las encuentre: import dentro de una función, parámetro llamado `subprocess` en otra función que no oculta el import en la función analizada y alias de función creado por asignación. El evaluador muestra las omisiones; no amplía el detector en esta iteración.

## Diseño simple

`AnalysisService.evaluate_builtin_corpus` carga únicamente el corpus empaquetado. El evaluador reutiliza `scan_source_bytes`, `review_original_source` e `investigate_argument`; no implementa un segundo motor de análisis. Estos componentes reciben la fuente y las señales, **nunca las respuestas esperadas**. Solo el evaluador compara después con las referencias.

No crea expedientes, preguntas, recibos o tablas SQLite. La primera entrega se ofrece mediante CLI y JSON; la integración visual del benchmark en la web/API queda fuera de esta iteración. CLI, escáner y evaluador comparten los mismos componentes de dominio.

El contrato `EvaluationReport` 1.0 conserva resultados por caso y grupo, referencias y pasos observados como metadatos, hash del corpus, hash del motor, versiones de Python/Pydantic/detector, sistema operativo, fecha UTC y tiempos. No copia código, comentarios ni valores literales a la salida. No contiene aportes humanos ni promueve declaraciones a evidencia.

El hash del corpus usa JSON canónico e incluye fuentes y etiquetas. El del motor combina los hashes de los once archivos de implementación y contratos implicados, normalizando CRLF del archivo Python a LF. Se comprueba que ninguno cambió durante la ejecución. Estos hashes permiten identificar qué se midió; no son firmas ni garantizan ausencia de errores comunes.

## Métricas y denominadores

**Detección por caso** compara presencia/ausencia de señales en cada entrada válida cuyo detector terminó:

- TP: referencia positiva y al menos una señal; FP: referencia negativa con señal.
- TN: referencia negativa sin señal; FN: referencia positiva sin señal.
- `precision = TP / (TP + FP)`; `recall = TP / (TP + FN)`; `F1 = 2TP / (2TP + FP + FN)`.

**Localización por señal** empareja llamada y coordenadas inicial/final exactas. Cuenta coincidencias (`matched`), señales extra (`extra`) y omisiones (`missed`), con multiplicidad. Una señal en una ubicación equivocada puede acertar presencia por caso y, a la vez, producir una señal extra y una omisión. Esto evita ocultar errores con un simple booleano por archivo.

**Trazado** declara cuántos objetivos de referencia se trazaron, cuántos acertaron origen y pasos, y cuántos fueron inconclusos. La cobertura divide trazados entre objetivos. La exactitud del origen condicionada al trazado divide aciertos entre trazados; el acuerdo total divide coincidencias de origen, pasos y verificación entre todos los objetivos, incluidos los no trazados. Un origen desconocido puede coincidir con la referencia, sin convertirse en prueba de seguridad.

Un denominador cero devuelve `null` en JSON y `n/a` en terminal. Se muestran grupos separados y total. Los errores esperados se cuentan aparte; un fallo inesperado del detector no se convierte en TN o FN. Si falla la corroboración o el trazado después de detectar, se conserva la medición de detección y baja la cobertura de trazado. El informe queda `PARTIAL` por el fallo técnico.

Los tiempos usan un reloj monotónico e incluyen arranque y ejecución de procesos. Hay una ejecución por caso. Se publican total, mediana/p50 y p95 por rango más próximo entre los casos iniciados, además de `timed_cases`; los no iniciados no reducen artificialmente los percentiles. No son una prueba de carga ni un SLA.

## Ejecución y códigos de salida

Desde la raíz, con la `.venv` existente:

```powershell
.\.venv\Scripts\python.exe -m sentinelforge.cli --no-animation evaluate --format pretty
.\.venv\Scripts\python.exe -m sentinelforge.cli evaluate --format json
```

El formato automático produce JSON en pipes y tablas en terminales. Para conservar una ejecución fuera de Git:

```powershell
New-Item -ItemType Directory -Force .local/evaluation | Out-Null
.\.venv\Scripts\python.exe -m sentinelforge.cli evaluate --format json > .local/evaluation/report.json
```

- **0 / `pass`:** coinciden las referencias dentro de alcance y los errores esperados. Las fronteras pueden mostrar omisiones y permanecen visibles.
- **1 / `fail`:** ejecución terminada con discrepancias en referencias dentro de alcance o manejo de errores esperados.
- **2 / `error`:** evaluación incompleta o error técnico de carga/proceso. La CLI conserva el informe parcial cuando existe; un fallo al cargar emite solo un diagnóstico estable por stderr.

El indicador `pass` significa coincidencia con referencias de desarrollo, no ausencia de omisiones globales o vulnerabilidades. Esta política es una comprobación del benchmark; no implementa todavía las políticas de seguridad para analizar otros repositorios en CI.

Límites: corpus empaquetado de hasta 512 KiB, 64 casos, 65 537 bytes por fuente para probar el rechazo de tamaño y los límites ya existentes de cada worker. Presupuesto de 120 segundos comprobado entre etapas y después de cada caso: un worker en curso conserva su timeout propio, por lo que no es un corte instantáneo. Los casos pendientes quedan `NOT_RUN` si vence el presupuesto. No hay ejecución de artefactos, red, instalación, proveedor LLM ni nuevas migraciones.

## Primera línea base y nota académica

Con la implementación actual: 15 TP, 8 TN, 0 FP y 3 FN por caso entre 26 entradas elegibles. La precisión observada es 100 % y el recall por caso 83,3 %. Por ubicación, se reproducen 16 de 19 señales de referencia: recall 84,2 %. Los dos errores de entrada se reconocen correctamente.

Se trazan 16 de 19 objetivos; los 16 coinciden con sus referencias, incluidos 4 resultados inconclusos. La exactitud de origen condicionada al trazado es 100 %, pero la cobertura y el acuerdo total son 84,2 %. Son resultados de este corpus pequeño, no estimaciones de calidad sobre repositorios reales. Deben compararse con el mismo hash de corpus y condiciones registradas.

Las pruebas verifican cálculos con FP/FN deliberados, ubicaciones incorrectas, señales duplicadas, denominadores vacíos, fallos de componentes, referencias alteradas, vencimiento de presupuesto, estabilidad de identidades, no persistencia, carga inválida y formatos/códigos de salida de la CLI. Se valida también el corpus con el motor real en la suite existente.

Validación local del 21 de noviembre de 2026: **320 pruebas aprobadas, 2 omitidas por Windows y Ruff limpio**, usando la `.venv` existente. El comando real de CLI terminó con código 0 y guardó una línea base ignorada por Git en `.local/evaluation/baseline-v1.json`, junto a su vista de terminal. Una ejecución local completa del corpus tardó aproximadamente 16,66 s, con p50 836,9 ms y p95 1010,3 ms; las condiciones de ejecución pueden cambiar estos tiempos.

El corpus se declara como package data y su carga se verifica desde el repositorio y desde otro directorio de trabajo. La construcción de un wheel continúa sin verificarse localmente por la ausencia de `setuptools.build_meta` en `.venv`, ya registrada en la capa 12; no se instaló para resolverla. Esta entrega no publica paquetes ni añade dependencias.

Lo aprendido: una cobertura incompleta puede coexistir con aciertos perfectos entre los casos resueltos. Hacer visibles los no detectados y los inconclusos es necesario para decidir la siguiente mejora. El siguiente alcance debería elegirse a partir de las omisiones observadas y una revisión independiente de las etiquetas.

Preguntas de repaso: ¿qué diferencia hay entre detectar alguna señal y acertar su ubicación? ¿Por qué un parser fallido no es un negativo? ¿Cómo puede haber 100 % de acierto del origen y 84,2 % de cobertura? ¿Qué significan los cuatro resultados inconclusos? ¿Por qué cambiar las etiquetas para seguir al motor invalidaría la comparación?

Decisión: [ADR 0010](adr/0010-corpus-y-evaluacion-local.md).
