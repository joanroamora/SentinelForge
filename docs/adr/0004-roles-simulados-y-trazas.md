# ADR 0004: roles simulados con trazas persistentes

- **Estado:** implementado localmente
- **Fecha:** 2026-11-20

## Contexto

Los checkpoints conservan las fases, pero falta separar sus resultados. El producto requiere que los investigadores no sean jueces de su propia explicación y que una afirmación humana no se convierta automáticamente en evidencia.

## Decisión

Introducir un catálogo cerrado de tres fixtures y funciones deterministas separadas para señal, hipótesis y verificación. El verificador relee el JSON original, valida referencias y recalcula el hash. Los resultados se guardan en una tabla de trazas independiente del checkpoint y del evento de auditoría, dentro de la misma transacción.

El esquema SQLite 3 añade esa tabla y conserva el recorrido de los ciclos anteriores sin traza. El reporte mantiene su contrato y añade evidencia calificada como simulada. El cierre vuelve a comprobar la decisión antes de publicarla.

## Consecuencias

- No se añaden dependencias, red, procesos de escaneo ni proveedores LLM.
- Los tres casos permiten demostrar respaldo, contradicción y falta de evidencia de forma reproducible.
- La ejecución es secuencial y breve dentro de la transacción. Herramientas lentas o externas requerirán otro diseño de ejecución y confirmación de resultados.
- No hay Monitor real ni verificación de declaraciones humanas. Los hallazgos del reporte siguen inconclusos.
- Esta capa no incorpora LangGraph ni demuestra mejoras de precisión o recall sobre software real.
