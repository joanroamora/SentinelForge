# ADR 0013: alias de funciones por una asignación de módulo

- **Estado:** implementado localmente
- **Fecha:** 2026-11-21

## Contexto

La evaluación 1.2 conserva una omisión en `runner = subprocess.run` seguido de
una llamada a `runner(..., shell=True)`. Resolver nombres sin atender imports,
escrituras y ámbitos podría atribuir a `subprocess` una función diferente.

## Decisión

Admitir un único enlace por asignación directa en el módulo a una de las cinco
funciones ya reconocidas, desde un import válido anterior. La referencia puede
ser un atributo del módulo importado o un nombre de función importado. Exigir
una única escritura del destino, orden léxico anterior a la llamada y ausencia
de enlaces competidores o mutaciones visibles. Mantener los bloqueos
conservadores en el archivo y distinguir parámetros de ámbitos relevantes.

El origen del alias se resuelve en el contexto de la asignación del módulo;
la visibilidad del destino se comprueba para el ámbito de cada llamada.
Conservar el límite de bytes, nodos, señales y tiempo del worker.

El corroborador reconstruye desde las fuentes originales, tablas de símbolos
y escrituras, sin importar el resolver del detector. Reutilizar únicamente sus
propias comprobaciones de visibilidad, conservando el rechazo de nombres
locales y parámetros que realmente ocultan la referencia.

Emitir detector/corroborador 1.3 con lectura de metadatos 1.0/1.1/1.2. Mantener
trazadores 1.1, contratos existentes y SQLite 7. Conservar el corpus 1.0 intacto
y comparar con la ejecución 1.2 anterior al cambio.

## Consecuencias

- Una nueva forma de llamada se presenta con su nombre canónico y ubicación
  original mediante CLI/API/web, sin duplicar el motor.
- Cadenas, asignaciones locales, condicionales, múltiples/anotadas, alias de
  módulos y referencias calculadas quedan pendientes.
- Los bloqueos pueden omitir usos válidos. El patrón no prueba alcanzabilidad,
  explotabilidad ni veracidad de contexto humano.
- Se preservan revisiones y recibos; no se incorpora una migración de datos.
- Se prueban afirmaciones de escáner incorrectas y metadatos históricos. No hay
  nuevas dependencias, ejecución de artefactos ni servicios externos.
- La comparación intacta pasa de 18/19 a 19/19 señales y recorridos coincidentes
  con sus referencias; mantiene cuatro trazados inconclusos. La suite local
  completa registra 435 pruebas aprobadas, dos omisiones de Windows y Ruff limpio.

Evidencia y aprendizaje: [capa 18](../18_ALIAS_POR_ASIGNACION.md).
