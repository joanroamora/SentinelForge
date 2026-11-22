# ADR 0014: selección cerrada de corpus y desafío separado

- **Estado:** implementado localmente
- **Fecha:** 2026-11-21

## Contexto

El motor 1.3 coincide con las referencias del corpus original. Seguir usando
solo esos ejemplos puede ocultar fronteras que aún requieren trabajo. Mezclar
casos nuevos o reetiquetar los originales impediría comparar las mediciones
previas de forma directa.

## Decisión

Conservar `baseline` como opción predeterminada y añadir `challenge` como corpus
empaquetado separado, con identidad, versión, fuentes, etiquetas y hash propios.
Redactar referencias desde sintaxis y tokens antes de medirlas; declarar su
autoría de desarrollo y ausencia de auditoría independiente.

Usar un enum compartido y un registro cerrado de recursos e identidades. No
aceptar rutas arbitrarias. Validar tamaño, contrato e identidad al cargar.
Seleccionar desde CLI y `AnalysisService`, reutilizando el mismo evaluador sin
duplicar el motor ni crear expedientes. Los informes y tablas existentes ya
identifican el corpus y muestran las discrepancias.

Emitir componente evaluador 1.1 con lectura de 1.0, conservando forma de contrato
y semántica de métricas/gate. Mantener detector/corroborador 1.3, trazadores 1.1,
corpus original intacto y SQLite 7. No agregar dependencias, endpoints o escaneos
externos en esta iteración.

## Consecuencias

- Las seis omisiones del desafío son visibles junto a los casos resueltos.
- El `pass` de alcance no certifica que se resuelvan todas las fronteras.
- Se pueden comparar versiones del motor sobre cada corpus fijo, conservando
  los resultados históricos. Dos corpus distintos no constituyen esa comparación.
- Los 20 casos nuevos son sintéticos y no acreditan calidad representativa ni
  independencia de anotadores.
- Límites, no ejecución y protección de metadatos se mantienen. El empaquetado
  usa el patrón de package data existente; construir el wheel sigue pendiente.
- La suite local completa registra 450 pruebas aprobadas y dos omisiones de
  Windows. La CLI real reproduce 19/19 señales del original y 7/13 del desafío,
  conservando visibles sus seis fronteras.

Evidencia y nota académica: [capa 19](../19_CORPUS_DE_DESAFIO.md).
