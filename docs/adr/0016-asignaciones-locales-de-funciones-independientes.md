# ADR 0016: asignaciones locales de funciones independientes

- **Estado:** implementado y validado localmente
- **Fecha:** 2026-11-21

## Contexto

El desafío fijo mantiene una omisión en `unrelated-local-assignment`: una
escritura local de otra función bloquea un import de módulo válido para la
llamada. Ignorar escrituras sin comprobar su ámbito permitiría atribuir al
módulo estándar llamadas a otros objetos.

## Decisión

Al resolver imports de módulo, omitir únicamente destinos de asignaciones
simples directas en funciones nombradas independientes de la llamada. Conservar
las escrituras de su propia función y de las funciones que la contienen. No
omitir el nombre si aparece una declaración global/nonlocal, una escritura de
forma no admitida u otro bloqueo conservador.

El detector identifica propietarios en el AST. El corroborador exige un símbolo
local del compilador y contrasta las escrituras originales, sin importar la
implementación del detector. Añadir comprobación AST de destinos de
comprensiones: las tablas de símbolos por sí solas no rechazaban una afirmación
inventada en el Python 3.14 local.

Emitir detector/corroborador 1.5 con lectura 1.0–1.4. Conservar trazadores 1.2,
evaluador 1.1, forma de contratos, SQLite 7 y los dos corpus sin modificaciones.
No ampliar las escrituras permitidas del destino de un alias por asignación.

## Consecuencias

- La mejora se contrasta con las mismas fuentes, referencias y categorías,
  conservando la medición 1.4 y las omisiones todavía pendientes.
- No se resuelven todos los ámbitos de Python. Persisten falsos negativos por
  bloqueos conservadores, sin afirmar identidad efectiva del módulo,
  alcanzabilidad o explotabilidad.
- Las declaraciones humanas no intervienen en la resolución del import ni se
  promueven a evidencia. Revisiones y recibos históricos se conservan.
- Los comprobadores comparten parser y supuestos; no son una prueba formal.
- Se comprueban afirmaciones falsas, ámbitos relevantes, historia, reintentos,
  no ejecución y adaptadores con las dependencias existentes del repositorio.
- La comparación local conserva baseline en 19/19 señales y recorridos y
  aumenta challenge de 9/13 a 10/13, sin pérdidas observadas. Quedan tres
  omisiones visibles; las referencias siguen sin auditoría independiente.
- La suite completa registra 563 pruebas aprobadas, dos omisiones de Windows
  y Ruff limpio. La API recargada anuncia 1.5 y conserva el expediente histórico
  consultado. Esta iteración permanece local, sin commit ni publicación.

Evidencia y nota académica: [capa 21](../21_ASIGNACIONES_EN_FUNCIONES_INDEPENDIENTES.md).
