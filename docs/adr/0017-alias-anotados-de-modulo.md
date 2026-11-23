# ADR 0017: alias anotados de módulo con valor explícito

- **Estado:** implementado y validado localmente
- **Fecha:** 2026-11-21

## Contexto

El desafío fijo conserva una omisión en `annotated-module-capture`:
`runner: object = subprocess.run`. La resolución previa solo admite `Assign`.
Una anotación es una expresión de intención, no prueba de identidad del callable;
interpretarla podría introducir ejecución o afirmaciones de tipos injustificadas.

## Decisión

Admitir `AnnAssign` directo en el módulo, con destino `Name`, `simple=1`, valor
presente y anotación `Name` o cadena literal. Resolver el valor desde un import
original anterior a una función canónica, manteniendo el único enlace y los
bloqueos por escrituras, ámbitos y mutaciones. No evaluar ni comprobar el tipo.

El detector selecciona candidatos; el corroborador relee declaraciones y símbolos
del compilador por separado, sin importar su resolver. Conservar el trazado de
argumentos existente: no se añaden asignaciones anotadas en funciones ni se
inventan recorridos de llamadas del módulo.

Emitir detector/corroborador 1.6 con lectura 1.0–1.5. Mantener trazadores 1.2,
evaluador 1.1, formas de contratos, SQLite 7 y los dos corpus intactos. Conservar
la medición 1.5 para comparar referencias, fuentes, categorías y omisiones.

## Consecuencias

- El significado de la señal, la separación de contexto humano y la historia
  no cambian. Identificar el callable no acredita vulnerabilidad ni seguridad.
- Capturas anotadas locales, condicionales, sin valor, con anotación opaca o
  referencias encadenadas permanecen fuera de alcance. Pueden producir omisiones.
- Las cadenas de anotación son datos y no se emiten en informes. Se prueban
  instrucciones aparentes y una anotación que delataría evaluación accidental.
- Se comprueban afirmaciones incorrectas, compatibilidad histórica, no ejecución,
  CLI/API, reintentos y conservación de la primera revisión.
- No se añaden dependencias, migraciones, proveedores, ejecución de artefactos
  ni publicación. La capa anterior 1.5 se conserva en la misma rama local.
- Sobre las referencias intactas, challenge pasa de 10/13 a 11/13 señales y
  recorridos coincidentes; baseline mantiene 19/19 y cuatro inconclusos, sin
  pérdidas observadas. Permanecen dos omisiones de desafío.
- La suite registra 628 pruebas aprobadas, dos omisiones de Windows y Ruff limpio.
  La API recargada anuncia 1.6 y conserva la huella del expediente histórico
  consultado. No hay commit ni publicación de esta iteración.

Evidencia y nota académica: [capa 22](../22_ALIAS_ANOTADOS_DE_MODULO.md).
