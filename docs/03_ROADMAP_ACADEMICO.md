# 03 — Roadmap académico y primeras iteraciones (v0.1)

## Cómo se estudia

En cada iteración: **concepto -> diseño -> implementación pequeña -> tests -> explicación propia -> ADR**. Codex debe explicar *por qué* existe cada componente. El usuario debe poder responder: ¿qué problema resuelve?, ¿qué recibe?, ¿qué produce?, ¿cómo falla?, ¿cómo lo pruebo?

## Hitos

| Fase | Conceptos que se aprenden | Entregable / condición de salida |
|---|---|---|
| 0. Contrato inicial | MVP, límites, riesgos, monolito modular, `venv` | Docs, `AGENTS.md`, `.gitignore`, estructura y entorno reproducible |
| 1. Vertical slice | Python packaging, Pydantic, CLI Typer, FastAPI, tests | Mismo servicio responde por CLI y HTTP con entrada de demo y reporte JSON |
| 2. Evidencia y dominio | Finding, Evidence, human statement, SQL, versiones | Expediente persistente + reporte con declaraciones humanas separadas de prueba técnica |
| 3. Orquestación | LangGraph, estado, nodos, subgrafos, paralelismo | Subgrafo investigador y verificador ejecutado con mocks deterministas |
| 4. Monitor | human-in-the-loop, interrupciones, reanudación, eventos | Pregunta web/API, respuesta, verificación, reporte revisado tras reinicio |
| 5. Detectores reales | SAST/SCA, normalización, SBOM, SARIF | Integración autorizada con scanner, fixture vulnerable y fixture segura |
| 6. Confiabilidad | observabilidad, límites, retries, evaluación de LLM | Métricas reproducibles FP/FN, precision, recall, latencia, costo |
| 7. Publicación | CI/CD, release, contenedores opcionales, seguridad de API | Demo pública de datos sintéticos, README claro, licencia revisada |
| 8. Escalado opcional | PostgreSQL, colas, aislamiento, Terraform/Cloud | Diseño de producción validado, no solo un despliegue de demostración |

## Iteración 1 — la primera tarea real de Codex

**Objetivo:** demostrar el principio «un motor, tres interfaces» sin gastar tokens ni ejecutar escáneres externos.

Cambios permitidos:

1. Revisar el repositorio actual y respetar sus archivos.
2. Crear paquete Python `src/sentinelforge/`, un servicio `AnalysisService` y contratos Pydantic.
3. Crear `sentinelforge` como CLI Typer, una API FastAPI y una web mínima (HTML servido por la misma API, sin Node).
4. `AnalysisService` crea un análisis con ID y reporte **de demostración** usando una fixture. Aclarar que no es un escaneo de seguridad.
5. Incluir una `HumanStatement` con verificación `unverified` en JSON y en la página web.
6. Añadir endpoints `/health`, `/v1/analyses` (crear demo), `/v1/analyses/{id}` y `/v1/analyses/{id}/reports/latest`.
7. Agregar pruebas de equivalencia del núcleo: CLI y API devuelven el mismo esquema de reporte. Sin credenciales, APIs externas ni instalaciones globales.
8. `.gitignore` debe ignorar `.venv`, `.env`, artefactos, caches, reports locales y bases SQLite.

**No hacer todavía:** LangGraph real, Docker, Kubernetes, API keys, upload de artefactos reales, acceso a internet, publicación o scanners activos. Primero comprender el esqueleto.

### Criterios de aceptación

- CLI y API importan el mismo `AnalysisService`, no duplican lógica.
- Endpoint health retorna 200; API y CLI presentan un reporte de demo con esquema consistente.
- Un reporte contiene hallazgo de demostración, evidencia, declaración humana y `verification_status` claramente diferenciados.
- `pytest` pasa dentro de `.venv`; reportar comandos exactos y resultados.
- El proyecto tiene instrucciones claras para levantar CLI, servidor HTTP y web sin instalar librerías globalmente.

## Iteración 2 — Persistencia y reanudación

Migrar la demo a expediente SQLite; crear eventos append-only, revisiones de reportes y test de reinicio. Ningún subagente se incorpora hasta que el estado sea entendible.

## Iteración 3 — Multiagente simulado

Agregar orquestador y subgrafos con proveedores falsos/deterministas. Comparar resultados con baseline sin LLM. Aprender tracing y políticas de concurrencia.

## Iteración 4 — Modo Monitor real

Preguntas acotadas, validación de aportes humanos, interrupción por hallazgo, reanudación después de reinicio y actualizaciones por SSE. Si la CLI corre en CI, crear pregunta y continuar con resultado parcial; nunca bloquear stdin.

## Iteración 5 — Seguridad real, controlada

Conectar una herramienta de análisis estático desde entorno autorizado, fixture de proyecto vulnerable conocido, fixture segura, normalización y SARIF. Mantener prohibido ejecutar arbitrariamente el proyecto analizado.

## Estrategia de evaluación

Crear datasets con verdad conocida. Medir por severidad y familia de riesgo: TP, FP, TN, FN, precision=TP/(TP+FP), recall=TP/(TP+FN), tasa de inconclusos, tiempo por caso, preguntas útiles, costo y trazabilidad de hallazgos. Evitar prometer reducción de falsos positivos sin comparación controlada y ablation tests (sin verificador / con verificador / con monitor).

## Definition of Done de cada fase

- Código que cumple los contratos.
- Pruebas automáticas y evidencia del resultado.
- Threat-model actualizado si hay una nueva superficie de entrada.
- Explicación sencilla de arquitectura y decisiones.
- Una evaluación académica de 3-5 preguntas para el usuario.
- Notas sobre costos, riesgos y limitaciones.


## Avance local: origen del comando (20 nov 2026)

Ya existen detector Python acotado, corroboración de fuente original e investigación determinista del origen del comando dentro de una función, con comprobador separado. CLI/API/web comparten motor y expedientes versionados. Esta capa está documentada en [Origen del comando](14_ORIGEN_DEL_COMANDO.md); aún no cubre flujo entre funciones, sanitizadores o alcanzabilidad, ni mide precisión/recall con un dataset representativo.

Antes de ampliar el alcance, decidir la siguiente iteración: corpus etiquetado de casos positivos, negativos e inconclusos y métricas reproducibles; después evaluar qué ampliación aporta evidencia útil. GCP y la ejecución aislada de artefactos continúan como etapas posteriores que requieren diseño y autorización.

## Avance local: evaluación de desarrollo (21 nov 2026)

La [evaluación local](15_EVALUACION_LOCAL.md) incorpora 28 casos sintéticos con referencias fijas, sin auditoría independiente. Mide presencia por caso, localización por señal, cobertura/acuerdo de trazado, inconclusos y tiempo. Separa 23 casos del alcance actual, 3 fronteras con omisiones conocidas y 2 errores de entrada; un fallo técnico no cuenta como negativo. La CLI produce tablas o JSON y no crea expedientes.

La primera línea base reproduce 16 de 19 señales de referencia, con 3 omisiones visibles y 4 trazados inconclusos entre los 16 realizados. Revisar las etiquetas y ampliar el corpus con ejemplos independientes precede a cualquier afirmación de calidad general. El próximo cambio funcional puede seleccionarse entre las limitaciones observadas, sin ampliar todos los dominios simultáneamente.

## Avance local: primera mejora medida (21 nov 2026)

El motor 1.1 incorpora [imports directos dentro de funciones](16_IMPORTS_LOCALES.md), junto con corroboración independiente y trazado compatible. Sobre el corpus 1.0 intacto, se reproducen 17 de 19 señales y recorridos, frente a 16 anteriores; quedan dos omisiones y cuatro resultados inconclusos. Se conservan revisiones de componentes 1.0, sin migrar SQLite ni modificar el significado de las señales.

## Avance local: parámetros de funciones independientes (21 nov 2026)

El motor 1.2 distingue parámetros de otras funciones al resolver imports de módulo. El [resumen con guía de capas](17_AMBITO_DE_PARAMETROS_Y_GUIA.md) explica el cambio y el producto actual. El corpus intacto pasa a 18/19 señales y recorridos; conserva una omisión por alias asignado y cuatro trazados inconclusos. La nueva versión no amplía por sí sola la evaluación a proyectos completos ni valida seguridad general.

## Avance local: alias por asignación (21 nov 2026)

El motor 1.3 reconoce [alias de funciones por una asignación simple en el módulo](18_ALIAS_POR_ASIGNACION.md), con corroboración mediante tablas de símbolos y fuente original. El mismo corpus conserva sus fuentes, etiquetas y categorías: se localizan 19/19 señales y los 19 recorridos coinciden con sus referencias, incluidos cuatro inconclusos. Se resuelve la omisión `assignment-alias-gap` sin pérdidas entre las referencias antes coincidentes. Las cadenas de alias, asignaciones locales/condicionales y flujos entre funciones continúan pendientes. La lectura de expedientes 1.0/1.1/1.2 y SQLite 7 se conserva; no es una certificación de seguridad ni de cobertura sobre proyectos reales.

## Avance local: desafío de evaluación separado (21 nov 2026)

El evaluador 1.1 añade [selección de corpus y un desafío de 20 casos](19_CORPUS_DE_DESAFIO.md). El original permanece intacto y predeterminado. El desafío localiza 7/13 señales con el mismo motor 1.3 y hace visibles seis omisiones: alias locales, cadenas, capturas anotadas, imports condicionales y asignaciones locales de otras funciones. Las referencias se fijaron antes de medir y siguen sin auditoría independiente. La siguiente ampliación del motor puede elegirse por estas omisiones; no se agregan dominios, infraestructura o dependencias en esta capa.

## Avance local: alias dentro de funciones (21 nov 2026)

El [motor 1.4 y los trazadores 1.2](20_ALIAS_LOCALES_DE_FUNCIONES.md) reconocen una captura directa del callable dentro de su función, la corroboran con tablas de símbolos y conservan el recorrido del argumento en los casos admitidos. Sobre los mismos corpus, challenge pasa de 7/13 a 9/13 señales y recorridos coincidentes, y baseline mantiene 19/19 con cuatro inconclusos. Quedan cuatro omisiones de desafío. Se conservan historia, contratos y SQLite 7. La suite local registra 513 pruebas aprobadas, dos omisiones de Windows y Ruff limpio; los corpus siguen siendo sintéticos y sin auditoría independiente.

## Integración y avance local: ámbitos independientes (21 nov 2026)

El PR #5 quedó integrado en `dev` mediante `2f0c241`. Su [CI del commit ad9ff04](https://github.com/joanroamora/SentinelForge/actions/runs/44975193972) aprobó Linux/Windows con Python 3.11 y 3.14.10; esa ejecución corresponde al motor 1.4.

La siguiente iteración local, en `codex/unrelated-local-bindings`, añade el [motor 1.5](21_ASIGNACIONES_EN_FUNCIONES_INDEPENDIENTES.md): distingue asignaciones simples de funciones independientes al resolver imports de módulo y refuerza el corroborador ante comprensiones que ocultan nombres. Sobre los corpus intactos, challenge pasa de 9/13 a 10/13 señales y recorridos coincidentes; baseline mantiene 19/19 y cuatro inconclusos, sin pérdidas observadas. Quedan cadenas de alias, capturas anotadas e import condicional. La suite local registra 563 pruebas aprobadas, dos omisiones de Windows y Ruff limpio. SQLite 7, contratos e historia se conservan; esta iteración todavía no tiene commit, publicación ni CI remota.

## Avance local: capturas anotadas de módulo (21 nov 2026)

El [motor 1.6](22_ALIAS_ANOTADOS_DE_MODULO.md) reconoce `runner: object = subprocess.run` y capturas equivalentes admitidas en el módulo, con corroboración separada y sin evaluar la anotación. Challenge pasa de 10/13 a 11/13 señales y recorridos coincidentes sobre las mismas referencias; baseline conserva 19/19, incluidos cuatro inconclusos. Quedan `two-hop-module-alias` y `constant-true-conditional-import`. No se amplían capturas anotadas locales ni expresiones de anotación opacas.

La suite local registra 628 pruebas aprobadas, dos omisiones de Windows y Ruff limpio. Los trazadores siguen en 1.2, el evaluador en 1.1 y SQLite en 7. La aplicación recargada anuncia 1.6 y conserva la huella del expediente histórico consultado. La rama `codex/annotated-module-aliases` conserva también la capa 1.5, todavía sin commits ni publicación de estas dos iteraciones. La CI remota de 1.6 y la auditoría independiente de las referencias siguen pendientes.

## Avance local: cadenas de alias de módulo (21 nov 2026)

El [motor 1.7](23_CADENAS_DE_ALIAS_DE_MODULO.md) reconoce hasta ocho capturas de callable en módulo, con propagación hacia adelante en el detector y reconstrucción hacia atrás en el corroborador. Mantiene comprobaciones por enlace y distingue el ámbito de captura del de la llamada. Una caché de pruebas positivas por fuente y ámbito evita repetir el trabajo para cien señales sin aumentar el timeout.

Sobre los corpus intactos, challenge pasa de 11/13 a 12/13 señales y recorridos coincidentes; baseline conserva 19/19 y cuatro inconclusos. Queda `constant-true-conditional-import` como única omisión del desafío, sin afirmar cobertura general. La suite final registra 700 pruebas aprobadas, dos omisiones de Windows, una advertencia de Pydantic en una prueba concurrente existente y Ruff limpio. SQLite 7, trazadores 1.2, evaluador 1.1 e historia se conservan. Las capas 1.5–1.7 siguen locales en `codex/module-alias-chains`, sin commits ni publicación; falta CI remota de estas capas y auditoría independiente de las referencias.

## Avance local: imports constantes de módulo (22 nov 2026)

El [motor 1.8](24_IMPORTS_CONSTANTES_DE_MODULO.md) admite imports en un `if True` directo del módulo, sin `else` y formado solo por imports. El corroborador contrasta la ubicación de la declaración y rechaza también imports competidores fuera del alcance admitido; una prueba con señal inventada detectó esa carencia previa.

Sobre los corpus intactos, challenge pasa de 12/13 a 13/13 señales y recorridos coincidentes; baseline conserva 19/19 y cuatro inconclusos. Las omisiones de esos dos conjuntos quedan resueltas sin reetiquetar ni cambiar categorías. Las 759 pruebas locales pasan, con dos omisiones de Windows y Ruff limpio. SQLite 7, trazadores 1.2 y evaluador 1.1 se conservan, incluida una frontera inconclusa de trazado local por atributo desde el nuevo import.

La aplicación anuncia 1.8 y conserva la huella del expediente histórico consultado. Las capas 1.5–1.8 siguen locales, sin commits ni publicación, en `codex/constant-true-module-imports`. Completar estos casos sintéticos de desarrollo no acredita calidad general: la próxima decisión debe priorizar consolidación y CI remota, revisión independiente de referencias y casos nuevos antes de atribuir cobertura en proyectos reales. El wheel y la auditoría independiente continúan pendientes.

## Avance local: consolidación y evidencia de calidad (22 nov 2026)

La [capa de consolidación](25_CONSOLIDACION_LOCAL.md) añade un comando que exige
la `.venv` del repositorio y ejecuta Ruff, la suite y ambas evaluaciones CLI.
Guarda evidencia en una carpeta nueva ignorada por Git, valida identidades y
consistencia de los reportes y compara las fuentes al inicio y al final. Fallos,
errores técnicos y cambios observados bloquean el gate; los pasos pendientes
quedan explícitos. La matriz CI existente reutiliza este comando.

La ejecución completa registra 789 pruebas aprobadas, 2 omitidas por Windows y
Ruff limpio. Baseline conserva 19/19 señales y cuatro trazados inconclusos;
challenge conserva 13/13. Las referencias y el motor 1.8 mantienen sus huellas.
Las capas 1.5–1.8 y esta validación se agrupan en `codex/local-quality-gate`.
No se añadieron instalaciones, migraciones o recursos cloud. Quedan publicación
y CI remota, construcción del wheel, revisión externa de etiquetas y evaluación
con casos reservados representativos. El gate es evidencia local de integración,
no una auditoría independiente ni una nueva capacidad de detección.

## Avance local: preparación de referencias externas (23 nov 2026)

El PR #6 quedó integrado en `dev` mediante `6e2b3a2`; su
[CI del commit 4eca847](https://github.com/joanroamora/SentinelForge/actions/runs/45265555387)
aprobó las cuatro combinaciones Linux/Windows con Python 3.11 y 3.14.10.

La [capa de referencias externas](26_REFERENCIAS_EXTERNAS.md), en
`codex/external-reference-evaluation`, permite aportar un JSON local limitado,
con identidad separada y procedencia declarada, y compararlo con el motor actual.
El recibo distingue el resultado global de todas las referencias de la política
histórica del benchmark incorporado. No se permite declarar auditoría o autoría
verificadas desde el archivo. Se conservan corpus, etiquetas, detector 1.8,
trazadores 1.2, evaluador 1.1 y SQLite 7.

Esto prepara la recepción de casos nuevos: la revisión externa y un conjunto
reservado representativo aún deben aportarse y verificarse. No se atribuye
independencia al ejemplo de formato ni se amplían reglas o proyectos completos.
La construcción del wheel permanece pendiente. No se instalan dependencias,
se publican cambios o se crean recursos cloud durante esta iteración local.

La validación final registra 845 pruebas aprobadas, dos omisiones de Windows y
Ruff limpio, con 56 casos de prueba nuevos. Baseline conserva 19/19 señales y
cuatro inconclusos; challenge conserva 13/13. Se mantienen sus hashes originales
y la huella de fuentes coincide al inicio y al final del gate. La CLI JSON,
terminal y ayuda funcionan con la fixture de protocolo; esta fixture no es una
evaluación externa independiente. La publicación y CI remota de esta capa siguen
pendientes.
