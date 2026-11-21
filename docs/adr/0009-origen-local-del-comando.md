# ADR 0009: hipótesis de origen local y comprobación hacia adelante

- **Estado:** implementado localmente
- **Fecha:** 2026-11-20

## Contexto

La corroboración estática prueba que una señal aparece en los bytes originales, pero no explica el argumento que llega a `shell=True`. No se conserva código fuente ni se permite ejecutar artefactos. Es necesario investigar sin confundir inferencias, evidencia o declaraciones humanas.

## Decisión

Exigir corroboración previa y hash original. Un worker genera una hipótesis siguiendo hacia atrás asignaciones simples dentro de una función. Otro worker reconstruye enlaces hacia adelante en la fuente original y compara todos los pasos. No comparten la implementación de trazado ni se llaman entre sí. Usan el parser de CPython en procesos `-I -S` distintos, sin imports ni ejecución del artefacto.

Separar hipótesis, comprobación y resultados por paso. Admitir literal, parámetro, resultado de llamada y desconocido; las fronteras de llamadas y los límites permanecen inconclusos. Conservar identificadores acotados y ubicaciones, sin valores literales, comentarios o fuente. No evaluar alcanzabilidad, confianza de entradas, sanitizadores o explotabilidad.

Añadir `ScanCase` 1.2 preservando la serialización 1.0/1.1 y una migración aditiva SQLite 6→7 con recibos UUID inmutables. Guardar revisión, recibo y evento atómicamente a partir del último expediente. Admitir una investigación por expediente y reintentos idempotentes. Compartir el motor entre web, API y CLI.

## Consecuencias

- Las hipótesis incorrectas quedan separadas de lo que el comprobador reproduce.
- Las señales y el contexto humano siguen sin verificar y el expediente permanece parcial.
- Las estrategias distintas aún comparten parser y supuestos de alcance; no constituyen verificación formal.
- La fuente se aporta de nuevo y se descarta. Los nombres de variables sí forman parte de los metadatos guardados.
- El análisis es conservador frente a control de flujo y operaciones opacas; puede quedar inconcluso aunque una persona resuelva el caso fácilmente.
- Límites: 64 KiB, 20 000 nodos, 100 señales, 128 sentencias previas, 32 pasos por señal, 512 en total y cinco segundos por proceso. No hay cuota dura de memoria ni sandbox de permisos.
- Ampliar a otras funciones, múltiples investigaciones o políticas de CI requiere una iteración posterior con evaluación representativa.
