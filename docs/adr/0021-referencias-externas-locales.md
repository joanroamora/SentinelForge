# ADR 0021: referencias externas locales sin atribuirles auditoría

- **Estado:** implementado y validado localmente
- **Fecha:** 2026-11-23

## Contexto

El motor coincide con los corpus de desarrollo incorporados. La siguiente
evaluación necesita casos nuevos aportados y revisados fuera de su desarrollo,
sin permitir que un archivo recibido dicte instrucciones o afirme una auditoría
que SentinelForge no puede acreditar.

## Decisión

Añadir `evaluate-file` sobre un servicio compartido que acepte JSON local de
hasta 512 KiB. Reutilizar los controles de lectura existentes con límites
configurados por el adaptador, sin alterar los 64 KiB de fuentes Python.
Rechazar claves JSON duplicadas, entradas inválidas, identidades incorporadas
y metadatos que se atribuyan autenticación o auditoría.

Mantener los corpus incorporados, sus referencias y la forma de sus reportes.
Compartir invariantes en `ReferenceCorpus` con identidades separadas en los
tipos concretos; el contrato incorporado conserva sus dos IDs permitidos.
Usar un corpus separado `external_synthetic` con procedencia declarada y un
recibo 1.0 que envuelva el resultado del evaluador existente. Serializar fechas
en el hash canónico mediante el modo JSON e incluir el adaptador en la huella
de implementación.

La decisión global externa compara todas las referencias, incluidas fronteras.
Conservar la política histórica en el resultado anidado y distinguirla en el
contrato, CLI y documentación. Dar prioridad al error técnico ante resultados
parciales. Una referencia coincidente nunca verifica por sí sola una conclusión
de seguridad o una declaración humana.

## Consecuencias

- Se prepara un mecanismo para recibir referencias; no se entrega un corpus
  independiente auditado ni una medida representativa de proyectos reales.
- Autor, rol, fecha y procedencia se conservan como declaraciones no autenticadas.
- No se retienen fuentes o literales en la salida ni se ejecutan las fuentes.
  Los metadatos declarados sí aparecen en el recibo.
- Se mantienen detector/corroborador 1.8, trazadores 1.2, evaluador 1.1 y SQLite 7.
- No se añaden dependencias, LLM, endpoints, persistencia o infraestructura.
  Wheel, revisión externa, casos reservados y análisis de proyectos siguen aparte.

Evidencia, límites y nota académica: [referencias externas](../26_REFERENCIAS_EXTERNAS.md).
