# ADR 0020: validación local con evidencia vinculada al código

- **Estado:** implementado y validado localmente
- **Fecha:** 2026-11-22

## Contexto

Las capas 1.5–1.8 están locales y sus pruebas y evaluaciones se ejecutaron por
separado. Consolidarlas requiere identificar qué código se probó, evitar mezclar
reportes anteriores y mantener explícitas las fases todavía no verificadas.

## Decisión

Agregar una herramienta de desarrollo que exija la `.venv` del repositorio y
ejecute Ruff, pytest y ambas evaluaciones CLI con sus referencias intactas.
Reutilizarla en la matriz CI existente, sin cambiar el motor de dominio ni sus
contratos, sumar dependencias o publicar resultados automáticamente.

Guardar cada ejecución en una carpeta nueva de `.local/validation/` con logs,
evaluaciones y manifiesto. Verificar identidades, referencias y consistencia de
métricas; exigir el mismo hash de motor y comparar el snapshot de fuentes al
inicio y final. Bloquear por fallo, error técnico o cambio observado; marcar
como `not_run` los pasos que no llegaron a iniciarse.

## Consecuencias

- Hay un comando común para comprobar la integración local y ejecutarla en CI.
- Las comprobaciones de evidencia complementan las pruebas; reutilizar métricas
  del evaluador no constituye una segunda auditoría del algoritmo.
- Los hashes no son firmas ni detectan cambios transitorios revertidos entre
  las dos capturas. No se promete reproducibilidad completa de dependencias.
- El gate acredita solo sus comprobaciones: wheel, matriz remota y auditoría
  independiente permanecen explícitamente sin verificar.
- No hay instalaciones locales, migraciones SQLite, llamadas a LLM, ejecución
  de artefactos recibidos, recursos cloud ni publicación en esta capa.

Evidencia, límites y nota académica: [consolidación local](../25_CONSOLIDACION_LOCAL.md).
