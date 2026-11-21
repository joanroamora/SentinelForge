# Origen del comando: asignaciones locales y contraste independiente

## Problema y vocabulario

Corroborar `shell=True` demuestra que el patrón aparece en la fuente original, pero no explica de dónde viene el comando. Esta capa construye una **hipótesis de recorrido** (*backward slice*: seguir las asignaciones hacia atrás) y la contrasta mediante **propagación de enlaces hacia adelante** (*forward binding replay*).

El alcance es un archivo y una función, sin ejecutar el artefacto. Un parámetro no significa entrada externa; un literal no demuestra seguridad. La cadena reproducida tampoco demuestra que la función se ejecute ni que exista inyección de comandos.

## Diseño y tradeoffs

`AnalysisService.trace_source_bytes` y `trace_local_source` son las entradas compartidas por API/web y CLI. Se exige una corroboración previa con `pattern_reproduced` para todas las señales, y bytes cuyo SHA-256 coincida con el original. La investigación no recibe declaraciones humanas ni instrucciones de comentarios como órdenes.

1. `_lineage_worker.py` reconstruye hacia atrás las asignaciones simples que llevan al primer argumento posicional, o al argumento `args=`, de cada señal.
2. `_lineage_check_worker.py` vuelve a leer la fuente, reconstruye hacia adelante los enlaces y compara la propuesta completa: origen, motivo, alcance, nombres, ubicaciones y asignaciones más recientes. No importa ni llama al investigador.
3. El motor valida referencias y contratos y conserva la hipótesis separada del resultado del comprobador.
4. Se añade una revisión inmutable y un recibo UUID, sin alterar el reporte técnico, la corroboración ni las declaraciones humanas.

Ambos procesos confiables usan el intérprete de `.venv` con `-I -S` y biblioteca estándar. Comparten el parser de CPython: la separación de estrategia y proceso no elimina fallos comunes ni equivale a verificación formal. El proceso tampoco es un sandbox de permisos ni impone una cuota dura de memoria.

Se admite `a = b` y asignación a un solo nombre, con orígenes literal, parámetro, resultado de llamada o desconocido. Se respetan el orden y las reasignaciones: en `b = a; a = otro`, `b` conserva el enlace anterior de `a`. No se siguen otras funciones. Ramas, bucles, cierres, nombres globales, atributos, colecciones, desempaquetado, argumentos dinámicos y operaciones opacas cortan el recorrido cuando impiden resolverlo. Las llamadas a nivel de módulo quedan fuera del alcance de esta iteración.

| Resultado | Interpretación |
|---|---|
| `steps_reproduced` | El comprobador reprodujo todos los pasos propuestos hasta un literal o parámetro |
| `inconclusive` | Hay un límite explícito o un resultado de llamada que no se sigue; los pasos posteriores pueden reproducirse |
| `not_reproduced` | La propuesta no coincide con la reconstrucción independiente; se conserva la discrepancia |

Los errores técnicos de worker, parser, protocolo o timeout no se guardan como decisiones de seguridad. El expediente con señales permanece `PARTIAL` y estas mantienen `unverified`. El texto humano nunca se promueve a evidencia técnica por esta operación.

## Límites y datos conservados

- Entrada máxima: 65 536 bytes UTF-8, incluidos BOM y finales de línea originales.
- Hasta 20 000 nodos AST, 100 señales, 128 sentencias previas por función, 32 pasos por señal y 512 pasos en total.
- Cinco segundos por proceso: investigador y comprobador pueden consumir hasta unos diez segundos de cómputo en conjunto. La API comparte sus dos slots de artefactos con detección y corroboración.
- Se conservan clases de paso, identificadores de hasta 120 caracteres, ubicaciones, hash, versiones, tiempo UTC y resultados por paso. Los identificadores más largos se omiten.
- No se copian valores literales, comentarios ni código al informe, SQLite o logs. Los identificadores sí son metadatos de la fuente: no aportar archivos con secretos en sus nombres. La selección no enviada del navegador se pierde al recargar.

Las posiciones usan líneas y columnas de base 1, con columnas en bytes UTF-8 y extremo final exclusivo, igual que el detector. Un límite deja el origen desconocido; no convierte la ausencia de recorrido en prueba de seguridad. No se evalúan sanitizadores, efectos entre hilos, alcanzabilidad o identidad efectiva de imports en ejecución.

## Persistencia y contrato

`ScanCase` **1.2** añade `argument_investigation`. Las revisiones **1.0** y **1.1** mantienen su formato JSON sin recibir este campo retrospectivamente. `ArgumentInvestigation` 1.0 separa `hypothesis` y `verification` por señal y declara el alcance `single_function_assignments`.

La migración aditiva SQLite **6 → 7** añade `local_scan_investigations` y triggers contra UPDATE/DELETE. Revisión, recibo y evento se guardan en una sola transacción, leyendo el último expediente para preservar respuestas humanas concurrentes. Un fallo revierte todos los cambios de la operación.

Se admite una investigación por expediente en esta entrega. Una solicitud con el mismo `submission_id` y bytes originales recupera el recibo, incluso después de otra revisión humana; la misma clave en otro expediente genera conflicto. Otra clave cuando ya existe investigación también genera conflicto. Un archivo modificado no pasa al parser ni modifica el expediente.

## Uso local

En la web, abrir el último expediente, corroborar la fuente y usar **Origen del comando → Archivo original para investigar → Investigar origen del comando**. El diagrama enumera los pasos, su ubicación y el resultado del comprobador; las revisiones anteriores muestran lo que existía entonces.

Desde PowerShell, con el entorno existente y una UUID nueva para el primer envío:

```powershell
$submissionId = [guid]::NewGuid().ToString()
.\.venv\Scripts\python.exe -m sentinelforge.cli scan-trace ID tests/fixtures/local_scan/argument_origins.py --submission-id $submissionId --format pretty
```

`ID` identifica un expediente del mismo archivo ya corroborado. Conservar la UUID para reintentar. La ruta sigue las protecciones del lector local: relativa, sin traversal, enlaces ni reparse points. La CLI no espera entrada interactiva; muestra un árbol en modo `pretty` y JSON en pipes o con `--format json`. Devuelve 0 por operación registrada/recuperada y 2 ante error. Un resultado inconcluso sigue siendo una operación terminada, no una vulnerabilidad confirmada ni un fallo técnico.

```http
POST /v1/local-scans/{id}/trace?submission_id=UUID
Content-Type: application/octet-stream

<bytes originales>
```

La API devuelve el recibo con su revisión; la CLI muestra el expediente más reciente. No acepta rutas del servidor ni decisiones impuestas por el cliente. Errores principales: 409 por hash, prerrequisito o conflicto; 413 por tamaño; 404 por expediente ausente; 422 por UUID o fuente no interpretable; 503 por slots, timeout o worker no disponible; 502 por fallo/protocolo del worker. La aplicación sigue local y sin autenticación.

## Evidencia y nota académica

Validación con `.venv`: **301 pruebas aprobadas, 2 omitidas por Windows y Ruff limpio**. Se probaron cadenas y reasignaciones temporales, literales/parámetros/llamadas, límites y entradas fuera de alcance, BOM/CRLF/Unicode, propuestas alteradas, fuente manipulada, fallos técnicos, no ejecución, recuperación, idempotencia, escritores concurrentes, rollback, migración y equivalencia CLI/API.

La base local se respaldó antes de migrar. La comparación de las nueve tablas existentes confirmó que todas sus filas permanecieron intactas; `integrity_check` devolvió `ok`. En el navegador se investigó el expediente existente de `shell_enabled.py`: creó la revisión 4 y preservó su contexto humano sin verificar. Su revisión 3 conserva el formato anterior.

La fixture `argument_origins.py` demuestra una cadena parámetro → dos asignaciones → llamada y un segundo recorrido inconcluso por una rama. Se comprobó la adaptación a 390 px sin desbordamiento horizontal y la recuperación de ambos recorridos después de reiniciar Uvicorn. Repetir la operación desde la CLI con su UUID original mantuvo la revisión 3. No se instalaron dependencias, se enviaron artefactos a proveedores ni se publicaron cambios remotos.

Lo aprendido: una ubicación y una conclusión no bastan para explicar el origen; hacen falta enlaces reproducibles y límites explícitos. La independencia exige contrastar la propuesta con la fuente, no confiar en la narración del investigador. El siguiente alcance deberá decidirse con ejemplos y evaluación de falsos positivos/negativos antes de ampliar a flujo de control o llamadas entre funciones.

Preguntas de repaso: ¿por qué un parámetro no demuestra entrada externa? ¿Qué ocurre si se reasigna `a` después de `b = a`? ¿Por qué una llamada que no seguimos deja una frontera inconclusa? ¿Qué información podría perderse si se guardara sobre una revisión antigua durante una respuesta humana concurrente?

Decisión: [ADR 0009](adr/0009-origen-local-del-comando.md).
