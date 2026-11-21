# ADR 0011: imports locales con corroboración y compatibilidad histórica

- **Estado:** implementado localmente
- **Fecha:** 2026-11-21

## Contexto

El corpus de evaluación expone una omisión por imports dentro de una función. Corregir solo la detección dejaría sin corroborar el vínculo o cortaría incorrectamente el trazado del parámetro al encontrar el import. Existen además revisiones y recibos de componentes 1.0 que deben seguir recuperándose sin cambios.

## Decisión

Aceptar imports directos anteriores a la llamada en el cuerpo de la misma función, incluidos alias, métodos y funciones asíncronas. Conservar las restricciones conservadoras ante nombres ambiguos y mantener sin cambios el resolver de imports de módulo. No ampliar a imports condicionales o cierres.

Corroborar con tablas de símbolos y declaraciones originales en una implementación separada. Rechazar imports condicionales que compitan con el nombre. En el trazado, omitir imports ajenos al nombre seguido y cortar el origen cuando el import lo sustituye; contrastarlo con propagación hacia adelante.

Emitir versiones de componente 1.1 y aceptar también 1.0 al leer contratos existentes. Mantener el esquema SQLite 7 y sus filas. La versión del detector produce fingerprints nuevos; nunca sobrescribir una observación histórica para incorporar la mejora.

Medir sobre el corpus 1.0 sin cambiar fuentes, etiquetas ni grupo de los casos. Conservar la línea base y las discrepancias pendientes.

## Consecuencias

- Se reproduce una señal y su recorrido antes omitidos; las otras dos fronteras siguen visibles.
- La comparación muestra 17/19 señales frente a 16/19, sin nuevos FP observados en este corpus de desarrollo.
- Se comparte el parser de Python y no se resuelve la identidad efectiva de módulos en ejecución. La corroboración no es verificación formal.
- Imports opacos o ambiguos pueden generar falsos negativos; reconocer una llamada no confirma alcanzabilidad ni explotabilidad.
- No hay nuevas dependencias, migraciones, ejecución de fuentes, proveedores LLM o despliegues.
