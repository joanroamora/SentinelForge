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
