# ADR 0019: imports de ramas constantes de módulo

- **Estado:** implementado y validado localmente
- **Fecha:** 2026-11-22

## Contexto

El corpus de desafío mantiene `constant-true-conditional-import` como omisión.
Resolver cualquier import dentro de una condición daría por establecidos
vínculos que pueden no existir. Una prueba adversarial revela además que el
corroborador anterior podía aceptar un import directo con otro import condicional
competidor que el detector ya rechazaba.

## Decisión

Admitir imports dentro de `if True` directamente en el módulo, sin `else` y con
cuerpo formado solo por imports. Comparar sus posiciones reales, mantener las
comprobaciones existentes y no evaluar la condición. No ampliar otras ramas,
bloques anidados o imports condicionales de funciones.

El detector enumera declaraciones admitidas; el corroborador valida su ubicación
y padres AST y las tablas de símbolos por separado. Rechazar también imports
no admitidos que liguen el mismo nombre e imports estrella al resolver vínculos
de módulo, conservando los bloqueos aunque produzcan omisiones.

Emitir detector/corroborador 1.8 con lectura 1.0–1.7. Mantener trazadores 1.2,
evaluador 1.1, forma de contratos y SQLite 7. Conservar ambos corpus y sus
referencias, fuentes, categorías y hashes. Contrastar con la medición 1.7.

## Consecuencias

- La declaración y el patrón se contrastan sin probar carga efectiva del módulo,
  alcanzabilidad, explotabilidad o seguridad general.
- El trazado local por atributo desde el import nuevo puede quedar inconcluso;
  esa frontera se conserva y se prueba, sin extender los trazadores en esta capa.
- Referencias coincidentes de desarrollo no acreditan calidad general ni
  sustituyen una evaluación con ejemplos independientes.
- Se prueban condiciones y bloques fuera de alcance, imports competidores,
  órdenes, ámbitos, afirmaciones inventadas, no ejecución, historia y adaptadores.
- Se conservan las capas locales previas; no hay instalaciones, migraciones,
  proveedores nuevos, ejecución de artefactos ni publicación.
- Challenge pasa de 12/13 a 13/13 señales y recorridos coincidentes; baseline
  mantiene 19/19 y cuatro inconclusos. Se conservan hashes y etiquetas, sin
  pérdidas observadas; las referencias continúan sin auditoría independiente.
- La suite local registra 759 pruebas aprobadas, dos omisiones de Windows y
  Ruff limpio. La aplicación recargada anuncia 1.8 y conserva la huella del
  expediente histórico consultado. Las capas 1.5–1.8 permanecen locales.

Evidencia y nota académica: [capa 24](../24_IMPORTS_CONSTANTES_DE_MODULO.md).
