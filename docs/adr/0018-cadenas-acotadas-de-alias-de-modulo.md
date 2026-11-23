# ADR 0018: cadenas acotadas de alias de módulo

- **Estado:** implementado y validado localmente
- **Fecha:** 2026-11-21

## Contexto

El desafío fijo conserva la omisión `two-hop-module-alias`. El motor 1.6 solo
resuelve una captura desde el import. Seguir nombres sin revisar cada enlace
podría atribuir al módulo estándar una función sustituida, y confundir el ámbito
de la captura con el de la llamada perdería alias válidos.

## Decisión

Aceptar hasta ocho capturas directas en el módulo, incluidas las anotadas
admitidas, desde un import original válido. La primera captura cuenta dentro
del límite; el import no. Exigir única escritura de cada destino, orden léxico
estricto y ausencia de enlaces competidores o mutaciones en toda la cadena.

El detector propaga referencias estables hacia adelante. El corroborador recorre
las declaraciones originales hacia atrás con tablas de símbolos, detección de
ciclos y un límite propio. No recibe el mapa del detector ni importa su resolver.
Contrastar el alias final en el ámbito de la llamada y los intermedios en el de
sus asignaciones, antes de los parámetros de la función llamada.

Cachear únicamente resoluciones positivas dentro de la invocación de verificación,
por alias y conjunto de funciones contenedoras, conservando el corte léxico de
la captura para cada llamada. No compartir esa caché entre fuentes o solicitudes.
Las pruebas incluyen afirmaciones desordenadas y otro ámbito con parámetro que
oculta al alias. No aumentar el timeout de cinco segundos.

No ampliar cadenas locales o mixtas, capturas condicionales, múltiples, alias
de módulos completos ni propiedades calculadas. Mantener bloqueos conservadores
incluso cuando una reasignación posterior pudiera ser válida en ejecución.

Emitir detector/corroborador 1.7 con lectura 1.0–1.6. Mantener trazadores 1.2,
evaluador 1.1, forma de contratos, SQLite 7 y los corpus intactos. Conservar la
medición e implementación 1.6 para contrastar fuentes, referencias y resultados.

## Consecuencias

- El vínculo de la función y el recorrido de su argumento siguen separados.
  La señal no acredita identidad efectiva del módulo ni explotabilidad.
- Más de ocho capturas dejan ese alias fuera de alcance, sin convertirlo en
  prueba de seguridad. El fallo técnico conserva un estado distinto.
- Cada implementación verifica todos los enlaces. Compartir parser y supuestos
  impide atribuirles independencia formal.
- Se comprueban reasignaciones intermedias, ciclos, orden, ámbitos, límite,
  afirmaciones inventadas, no ejecución, historia y adaptadores existentes.
- No hay dependencias, migraciones, proveedores, ejecución de artefactos ni
  publicación nuevos. Se conservan las capas locales 1.5 y 1.6.
- Challenge pasa de 11/13 a 12/13 señales y recorridos coincidentes sobre las
  mismas referencias; baseline conserva 19/19 y cuatro inconclusos, sin pérdidas
  observadas. Queda una omisión de desafío y las referencias siguen sin auditoría.
- La prueba de cien señales con ocho capturas detectó trabajo repetido que
  superaba el timeout. La caché acotada lo resolvió sin ampliar el límite; sus
  pruebas rechazan reutilización antes de la captura y en otro ámbito oculto.
- La suite final registra 700 pruebas aprobadas, dos omisiones de Windows y
  una advertencia de Pydantic en una prueba concurrente existente; Ruff pasa.
  La API recargada anuncia 1.7 y conserva el expediente histórico consultado.
  Las capas 1.5–1.7 siguen locales, sin commits ni publicación.

Evidencia y nota académica: [capa 23](../23_CADENAS_DE_ALIAS_DE_MODULO.md).
