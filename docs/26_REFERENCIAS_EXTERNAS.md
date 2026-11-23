# Referencias externas locales: preparar una evaluación con casos nuevos

## Problema y vocabulario

El PR #6 consolidó el motor 1.8 y la validación local; quedó integrado en `dev`
mediante `6e2b3a2`. Sus cuatro combinaciones CI aprobaron Linux/Windows con Python
3.11 y 3.14.10. Los corpus incorporados siguen siendo referencias de desarrollo
conocidas por quienes construyeron el detector.

Esta capa permite recibir un **corpus** de ejemplos sintéticos aportado como
JSON local. Su **procedencia** (*provenance*) identifica quién declara haberlo
preparado, con qué rol, en qué fecha y bajo qué referencia. Estos datos no
autentican al autor ni convierten las etiquetas en verdad técnica.

Se prepara el mecanismo para que una revisión externa aporte casos y etiquetas
sin modificar los corpus incorporados. Todavía no se ha recibido ni auditado un
conjunto independiente o representativo. El ejemplo incluido es una demostración
del protocolo, no evidencia de calidad externa.

## Diseño simple y compatibilidad

`AnalysisService.evaluate_local_corpus` lee un JSON elegido por el operador y
reutiliza `evaluate_corpus`, detector, corroborador y trazadores existentes. La
CLI añade `evaluate-file`; `evaluate --corpus baseline|challenge` conserva su
comportamiento y continúa rechazando rutas arbitrarias en esa opción.

El lector interno comparte los controles de apertura con el adaptador de fuentes
Python. Las lecturas `.py` mantienen 64 KiB y sus diagnósticos anteriores; la
entrada de referencias permite únicamente `.json` y hasta **512 KiB**.

`ExternalEvaluationCorpus` conserva casos, referencias, pasos, unicidad y límites
del contrato anterior y exige una identidad `external-...`, tipo
`external_synthetic` y procedencia declarada. No puede suplantar las identidades
`sf-py-001-local` o `sf-py-001-challenge`, declarar una auditoría independiente,
autenticar la autoría o adjuntar campos de instrucciones arbitrarios.
Los dos tipos concretos comparten las invariantes de casos mediante
`ReferenceCorpus`; el contrato incorporado conserva su conjunto cerrado de IDs.

`ExternalEvaluationReceipt` 1.0 distingue esta operación con
`report_type=external_reference_evaluation`. Incluye la procedencia, etiqueta
relativa del archivo, tamaño y hash de sus bytes, resultado global y el
`EvaluationReport` existente dentro de `evaluation`. Los contratos de los reportes
incorporados se conservan, incluido evaluador 1.1. Detector/corroborador permanecen
en 1.8, trazadores en 1.2 y SQLite en 7.

La huella canónica usa el modelo en modo JSON para incluir fechas con zona
horaria. Las fuentes y etiquetas originales de ambos corpus incorporados mantienen
sus hashes. La huella del motor se amplía para identificar también el adaptador
nuevo; no representa por sí sola una mejora de detección.

## Formato y uso

Ejemplo mínimo de formato, sin referencias positivas:

```json
{
  "schema_version": "1.0",
  "id": "external-review-example",
  "version": "1.0",
  "corpus_type": "external_synthetic",
  "reference_review": "not_independently_audited",
  "provenance": {
    "actor": "example-reviewer",
    "role": "reviewer",
    "reference": "synthetic-example",
    "created_at": "2026-11-23T00:00:00Z"
  },
  "cases": [
    {
      "id": "negative",
      "scope": "in_scope",
      "rationale": "Ejemplo del formato; no mide cobertura general.",
      "source": "pass\n",
      "expected_signals": []
    }
  ]
}
```

Los casos positivos requieren las mismas llamadas, coordenadas UTF-8, origen,
pasos y verificación esperados del contrato incorporado. Las referencias deben
redactarse y revisarse antes de observar los resultados; copiar la salida del
motor como etiqueta no proporciona independencia.

Desde la raíz, usando el ejemplo incluido:

```powershell
.\.venv\Scripts\python.exe -m sentinelforge.cli --no-animation evaluate-file tests/fixtures/evaluation/external_reference.json --format pretty
.\.venv\Scripts\python.exe -m sentinelforge.cli evaluate-file tests/fixtures/evaluation/external_reference.json --format json
```

Para un conjunto aportado, usar por ejemplo `artifacts/evaluation/references.json`.
`artifacts/` está ignorado por Git. Se admiten únicamente rutas relativas al root
local autorizado, sin componentes ocultos: `.local/` no es una ruta de entrada
admitida por este lector. Los resultados sí pueden redirigirse a `.local/` con
las herramientas del operador. No usar rutas absolutas, URLs, ZIP o stdin.

La salida automática es JSON en pipes y tablas en terminales. El formato visual
muestra autoría no autenticada, procedencia y fecha declaradas, hashes y política
externa. No hay nuevos endpoints o pantallas en esta iteración.

## Política de aceptación externa

El resultado global del recibo exige **todas las referencias**, incluidas las
clasificadas como `boundary`. Una omisión no puede quedar fuera de la decisión
global por la categoría declarada del caso.

- **0 / `pass`:** todas las comparaciones coinciden y la evaluación termina.
- **1 / `fail`:** al menos una referencia no coincide, incluida una frontera.
- **2 / `error`:** entrada rechazada, error técnico o evaluación incompleta.

El informe anidado `evaluation` conserva la política histórica del componente,
que separa casos en alcance y fronteras. Para este comando deben consultarse
`acceptance` y `reference_failures` del **recibo exterior**. El renderizador usa
esa decisión global sin alterar los datos del componente. El contrato rechaza
una decisión exterior contradictoria con sus resultados por caso.

Los errores esperados de una fixture se comparan con su referencia; no son por
sí mismos fallos técnicos. Un fallo inesperado de proceso o presupuesto conserva
la prioridad de error técnico y no se convierte en un negativo de seguridad.

## Superficie de entrada, privacidad y límites

El JSON y sus fuentes son no confiables. Se rechazan rutas ambiguas, traversal,
symlinks/reparse points, archivos no regulares, cambios observados durante la
lectura y errores de apertura. El operador debe controlar el root: esta validación
no es un sandbox del sistema operativo ni resuelve toda carrera posible de rutas.

Se acepta UTF-8 con o sin BOM. Se rechazan claves duplicadas en cualquier objeto,
JSON mal formado o excesivamente anidado, números no finitos, contratos inválidos
y campos extra. Los diagnósticos de entrada son estables y no copian el payload,
la ruta absoluta ni el detalle del parser o del sistema operativo.

Continúan los límites de 64 casos, 100 referencias por caso, hasta 32 pasos,
65 537 bytes por fuente para probar el rechazo de tamaño y 120 s por evaluación.
Los workers conservan sus límites propios. No se importa ni ejecuta el código
incluido en el JSON, no se consultan URLs y no se crean expedientes SQLite.

El recibo no copia fuentes, comentarios, literales ni razones textuales de los
casos; conserva metadatos técnicos y procedencia declarada. No introducir secretos
en fuentes o campos de autoría. El hash de bytes identifica el archivo recibido;
el canónico identifica su contenido validado, incluida la procedencia. Cambiar
indentación o BOM cambia el primero sin cambiar el segundo.

Las referencias pueden ser incorrectas o manipuladas. Coincidir con ellas no
demuestra precisión sobre proyectos reales, ausencia de falsos negativos o
explotabilidad. `not_independently_audited` y `declared_not_authenticated`
permanecen explícitos. El aporte no se convierte en una declaración humana
verificada ni cambia decisiones de expedientes de seguridad.

## Pruebas, evidencia y nota académica

Las pruebas cubren carga y no ejecución, invariantes heredadas, referencias
omitidas en fronteras, errores técnicos, contrato y formatos CLI, procedencia
falsa, JSON ambiguo/corrupto, tamaño, rutas, reparse points, cambios durante la
lectura, privacidad, hashes y recuperación por JSON del recibo. Las pruebas del
lector Python anterior siguen verificando sus controles y límites.

Validación final local del 23 de noviembre de 2026 con Python 3.14.10 de `.venv`:
**845 pruebas aprobadas, 2 omitidas por capacidades de Windows y Ruff limpio**.
Se añaden 56 casos de prueba. La suite final tardó 202,39 s y el gate completo
218,05 s. Las pruebas HTTP se ejecutaron con permiso para sockets locales.

Ambos corpus incorporados conservaron sus fuentes, etiquetas, categorías y
hashes: baseline localizó 19/19 señales con cuatro trazados inconclusos;
challenge localizó 13/13, sin inconclusos. La huella del motor actual es
`ed935b986ffe9bc359e809dca501558902d7e059599108910622e877ca56ddb7`.
La captura de fuentes coincide al inicio y al final:
`40160834c86dd754481cc1382c28a8f4b6cfbb153c6c89ba0b87c2afa505d0c1`.

La evidencia final del gate está en
`.local/validation/20261123T222056Z-b81830a1/`. La primera pasada precede a la
separación final de contratos y no se usa como comprobante de esta versión.
La CLI real terminó con código 0 en JSON, terminal y ayuda, usando el ejemplo
de protocolo. Sus archivos están en
`.local/evaluation/external-references-final-20261123T222259Z-55ce1f47/`.
El recibo identifica el mismo motor y conserva autoría declarada no autenticada;
no copia la fuente que contiene la excepción de protección de la fixture.

Se comprobó la sintaxis de los archivos principales nuevos con la gramática de
Python 3.11. Esto no sustituye una ejecución remota de esa versión. No se añaden
dependencias o instalaciones globales, no se publica esta rama ni se construye
el wheel durante esta implementación. La CI remota de esta capa queda pendiente.

Lo aprendido: una herramienta puede comparar referencias externas sin conocer
su corrección. Procedencia declarada, integridad del archivo y validez de una
etiqueta son propiedades distintas. Una categoría de frontera debe hacer visible
el límite; no debe ocultarlo en la decisión global externa.

Preguntas de repaso: ¿por qué un autor declarado no está autenticado? ¿Qué cambia
entre el hash de bytes y el canónico? ¿Por qué una frontera omitida devuelve 1?
¿Qué decisión hay que consultar en el recibo? ¿Qué falta para llamar independiente
a una evaluación recibida?

Decisión: [ADR 0021](adr/0021-referencias-externas-locales.md).
