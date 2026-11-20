# ADR 0003: ciclo simulado con checkpoints SQLite

- **Estado:** implementado localmente
- **Fecha:** 2026-11-20

## Contexto

El historial conserva reportes, pero no había un proceso de análisis recuperable entre pasos. El roadmap exige entender y recuperar el estado antes de incorporar orquestadores o agentes.

## Decisión

Añadir una máquina de seis estados simulados, con checkpoints inmutables separados del audit trail. CLI y API usan el mismo `AnalysisService`. Una llamada avanza una fase; su versión identifica la operación y permite reproducir el resultado anterior sin duplicar eventos.

La migración local 1→2 crea la tabla de checkpoints sin transformar reportes existentes. El checkpoint final, su reporte y los eventos se escriben en una sola transacción. Se conservan la demo inmediata y los contratos existentes de reporte.

## Consecuencias

- Se recupera el avance después de reiniciar sin una dependencia nueva.
- Las escrituras concurrentes del mismo avance convergen en el mismo checkpoint; no saltan fases.
- No se introducen LangGraph, llamadas LLM ni ejecución de artefactos.
- Los nombres de fase son marcadores de progreso; no acreditan trabajo técnico realizado.
- No hay pausas dentro de una tarea, preguntas pendientes, cancelación ni workers. Las herramientas y los estados por hallazgo se definirán en una iteración posterior.
- Crear un ciclo sin una clave de idempotencia crea un ID distinto en cada POST. La idempotencia implementada cubre el avance por versión.
