# ADR 0012: parámetros de funciones independientes y resolución conservadora

- **Estado:** implementado localmente
- **Fecha:** 2026-11-21

## Contexto

El corpus mantiene una omisión porque un parámetro de otra función oculta conservadoramente un import de módulo en todo el archivo. Ese parámetro no sustituye al nombre global en una función independiente. Ignorar todos los parámetros, sin considerar los de la propia función o sus funciones exteriores, produciría señales injustificadas.

## Decisión

Para imports de módulo, el detector consulta mediante AST la función propietaria del parámetro y las funciones que contienen la llamada. Solo ignora declaraciones de parámetros de otras funciones nombradas; los demás enlaces y mutaciones mantienen las restricciones anteriores. Cachear la resolución por conjunto de funciones contenedoras dentro de los límites del worker.

El comprobador usa tablas de símbolos y declaraciones originales, sin importar el resolver del detector. Omite únicamente parámetros de funciones independientes sin otros enlaces asignados/importados/namespace. Conservar las comprobaciones de ámbitos relevantes, mutaciones y escrituras globales.

Emitir detector/corroborador 1.2, aceptando metadatos 1.0 y 1.1. Mantener trazadores 1.1, contratos con la misma forma y esquema SQLite 7. Guardar nuevos análisis con fingerprints nuevos; no modificar revisiones antiguas.

Medir con el corpus 1.0 intacto. La mejora se observa en `unrelated-shadow-gap`; la omisión por alias asignado permanece. No reclasificar ni cambiar referencias para subir las métricas.

## Consecuencias

- Se reproducen 18/19 señales y recorridos, frente a 17/19 en 1.1, sin pérdidas observadas entre las referencias antes coincidentes.
- El alcance sigue siendo pequeño y conservador. No hay resolución general de todos los enlaces de Python ni de flujos de ejecución.
- Las referencias no están auditadas de forma independiente y no representan seguridad en repositorios reales.
- Las implementaciones comparten parser, aunque utilizan estrategias distintas. No es verificación formal.
- No se añaden instalaciones, migraciones, ejecución de artefactos, LLM, infraestructura o publicación remota.
