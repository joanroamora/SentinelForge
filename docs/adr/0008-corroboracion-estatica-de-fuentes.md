# ADR 0008: corroboración de señales sobre fuente reaportada

- **Estado:** implementado localmente
- **Fecha:** 2026-11-20

## Contexto

El expediente conserva señales, hash y contexto humano, pero descarta el código. Para contrastar una observación sin convertir al detector en juez de su salida, se necesita recibir otra vez la fuente y comprobar su identidad antes de analizarla.

## Decisión

Añadir una corroboración por expediente mediante worker stdlib separado que recibe solo bytes y metadatos de señales. Comprobar hash, ubicación exacta, imports/tablas de símbolos y token literal. No llamar al detector ni ejecutar código del artefacto. Emitir decisiones con alcance `static_pattern_only` y limitaciones explícitas.

Guardar la corroboración como revisión `ScanCase` 1.1. Mantener el JSON 1.0 de las revisiones sin corroboración. Añadir recibos UUID inmutables mediante migración aditiva SQLite 5→6. Revisión, recibo y evento son transaccionales y se ensamblan desde la última revisión para preservar contexto humano concurrente.

## Consecuencias

- La fuente no se retiene; archivo distinto o fallo técnico no modifica el expediente.
- Corroborar un patrón no confirma vulnerabilidades ni declaraciones humanas. El expediente sigue parcial.
- Se comparte el parser de Python; la separación no elimina fallos comunes ni constituye verificación formal.
- No se investiga flujo de datos, identidad real del módulo importado, alcanzabilidad o controles del entorno. Nuevas corroboraciones/versiones del verificador requerirán otra iteración.
- Se mantienen límites y modo local sin instalaciones ni servicios externos.
