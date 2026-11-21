# ADR 0010: corpus sintético y evaluación local sin persistencia de análisis

- **Estado:** implementado localmente
- **Fecha:** 2026-11-21

## Contexto

El motor detecta un patrón y reconstruye asignaciones dentro de una función. La suite comprueba sus contratos, pero falta una medición explícita de cobertura, omisiones, inconclusos y tiempo. No se dispone todavía de etiquetas auditadas o un dataset representativo.

## Decisión

Empaquetar 28 ejemplos como texto JSON con referencias estáticas fijas de ubicaciones, orígenes y pasos. Separar alcance soportado, fronteras y errores de entrada. Declarar que las etiquetas son de desarrollo y no han sido auditadas independientemente. No generarlas a partir de resultados del motor ni tratarlas como decisiones de vulnerabilidad.

Evaluar con los componentes actuales mediante `AnalysisService` y CLI; devolver `EvaluationReport` 1.0. Medir detección por caso y localización por señal, además de cobertura y acuerdo de trazado. No ocultar errores ni omisiones; métricas indefinidas son `null`. Un fallo posterior de verificación conserva la detección que sí terminó.

No crear expedientes ni modificar SQLite. No aceptar rutas de corpus arbitrarias desde la CLI y no integrar el benchmark en web/API en esta entrega. Guardar solo metadatos en la salida, sin fuente ni valores literales. Registrar hashes de corpus/motor, versiones, plataforma y tiempos.

Usar códigos 0/1/2 para referencias coincidentes/discrepantes/error técnico. Las omisiones de frontera se muestran en métricas y resultados, pero no cambian por sí solas el gate de regresión del alcance declarado. Un `pass` no es una decisión de seguridad.

## Consecuencias

- La evaluación puede reproducirse y expone tres limitaciones del detector actual sin modificarlo.
- No acredita precisión/recall general, independencia de anotadores o resistencia general a prompt injection de modelos.
- La exactitud condicionada puede ser alta con cobertura baja; se muestran ambos denominadores y los inconclusos.
- El corpus contiene código inerte en JSON; los workers solo lo procesan como datos.
- Límites del corpus y presupuesto global acotan trabajo, pero un worker en curso conserva su propio timeout. No hay sandbox de permisos ni cuota dura de memoria.
- Un corpus independiente, otros dominios, comparaciones estadísticas, nuevos detectores y evaluación de agentes requieren iteraciones posteriores.
