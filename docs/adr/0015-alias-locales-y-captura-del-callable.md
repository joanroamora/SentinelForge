# ADR 0015: alias locales y captura acotada del callable corroborado

- **Estado:** implementado localmente
- **Fecha:** 2026-11-21

## Contexto

El desafío fijo contiene dos omisiones por alias definidos en funciones.
Ampliar solo el detector dejaría sin corroboración esos nombres; además, una
captura mediante atributo interrumpía el trazado del argumento.

## Decisión

Admitir una única asignación directa y anterior a la llamada en la misma función,
desde un import reconocido local o de módulo. Conservar bloqueos por parámetros,
escrituras, mutaciones y declaraciones competidoras. No resolver cadenas,
capturas condicionales/anotadas/múltiples ni alias de funciones exteriores.

El corroborador usa fuentes originales y tablas de símbolos locales sin importar
el resolver del detector. Mantener el prerrequisito de corroboración positiva
antes de investigar el argumento.

Para el trazado, omitir únicamente la captura del callable de esa llamada si
coinciden destino, atributo canónico e import anterior. El investigador relee
declaraciones al recorrer hacia atrás; el comprobador mantiene referencias al
recorrer hacia adelante. No extender la excepción a otras propiedades ni
promover valores de origen desconocido.

Emitir detector/corroborador 1.4 y trazadores 1.2, conservando versiones anteriores,
formas de contrato, SQLite 7 y ambos corpus intactos. Mantener el evaluador 1.1.

## Consecuencias

- Challenge pasa de 7/13 a 9/13 señales y recorridos coincidentes con la referencia.
  Las cuatro fronteras restantes siguen visibles; baseline conserva 19/19.
- Las capturas de callable y el origen del argumento se comprueban por separado.
- El alcance es estático y conservador; no certifica imports reales, alcanzabilidad
  o explotabilidad. Ambos comprobadores comparten parser y supuestos.
- Se conservan revisiones y recibos anteriores. Señales y declaraciones humanas
  mantienen su estado sin verificar.
- Se prueban afirmaciones/propuestas incorrectas, no ejecución, historia e
  integración de adaptadores, sin instalar dependencias ni añadir infraestructura.
- La suite local completa registra 513 pruebas aprobadas, dos omisiones de
  Windows y Ruff limpio. La API recargada anuncia 1.4/1.2 y conserva la huella del
  expediente histórico consultado.

Evidencia y nota académica: [capa 20](../20_ALIAS_LOCALES_DE_FUNCIONES.md).
