# 01 — Visión de producto y requisitos (v0.1)

## 1. Problema

Los escáneres de seguridad producen alertas fragmentadas por capa (código, dependencias, contenedores, IaC y CI/CD). Los equipos invierten tiempo en correlacionarlas, investigar su contexto, descartar falsos positivos y redactar un informe defendible. El contexto humano —por ejemplo, «nuestra API usa API Gateway con IAM»— suele quedar fuera de la evidencia estructurada.

## 2. Propuesta de valor

**SentinelForge AI** recibe un artefacto de software autorizado, genera y normaliza señales de herramientas técnicas, asigna investigación contextual a subagentes, exige revisión independiente, incorpora preguntas/respuestas humanas verificables y crea informes trazables. No sustituye un pentest ni garantiza ausencia de vulnerabilidades.

## 3. Usuarios y canales

| Usuario | Canal | Valor |
|---|---|---|
| DevOps / DevSecOps | CLI local, runners y pipelines | Validaciones reproducibles y reporte automatizado |
| AppSec / auditor | Interfaz web | Revisión de hipótesis, evidencia y aportes humanos |
| Developer | CLI + web | Acción correctiva contextualizada |
| Equipo de plataforma | API | Integración programática con otros sistemas |

El **mismo ID de análisis** se podrá abrir por CLI, API o web cuando la ejecución sea remota. La ejecución enteramente local conserva su expediente local salvo publicación autorizada.

## 4. Dos modos de interacción

### Autónomo

No requiere preguntas. La información faltante queda documentada como `unknown` / `needs_context`; no se transforma en hallazgo descartado.

### Monitor (Human-in-the-Loop)

El orquestador formula preguntas específicas cuando la respuesta puede cambiar el análisis. El usuario responde desde la web o API; la CLI interactiva también podrá hacerlo en una terminal local. Un pipeline sin TTY crea preguntas pendientes y registra el estado; no queda bloqueado esperando entrada. Las respuestas tardías crean una nueva revisión del informe después de reanudar el flujo afectado.

**Una declaración humana forma parte obligatoria del informe, aunque esté sin verificar.** Cada declaración debe incluir texto original, autor/rol, fecha, fuente, pregunta asociada, recursos afectados, evidencia adjunta o referenciada, clasificación `unverified | supported | contradicted | not_verifiable` e influencia en la conclusión. El informe conserva la declaración aunque una verificación posterior la contradiga; la rectificación se registra como nueva revisión, no se borra silenciosamente.

## 5. Ejemplo canónico

Hallazgo: endpoint aparentemente sin autenticación. Usuario: «la API usa IAM y controles biométricos».

Se investiga: (a) IAM aplicado a invocaciones del Gateway o solo al backend; (b) método de autenticación y dónde se exige biometría/MFA; (c) autorización por endpoint; (d) rutas alternativas; (e) restricciones reales del entorno. Se solicita configuración no secreta, no credenciales ni biometría. Resultado: `confirmed`, `likely`, `inconclusive` o `refuted_by_evidence`; se explicita alcance de lo probado. La afirmación humana se cita como **declaración**, no como prueba técnica automática.

## 6. Requisitos funcionales

- RF-01: CLI escanea un directorio de proyecto local; API acepta artefacto autorizado limitado en tamaño; ambas usan el mismo motor.
- RF-02: Normalizar señales de escáneres y asociarlas a archivo, ubicación, herramienta, versión, huella y fuente.
- RF-03: Delegar hallazgos a subagentes de investigación contextual con resultados estructurados.
- RF-04: Verificadores independientes comprueban evidencias e intentan refutar conclusiones.
- RF-05: Monitor formula preguntas acotadas, registra respuestas y permite reanudar con persistencia.
- RF-06: Guardar el historial de estados, eventos, decisiones, preguntas y revisiones del informe.
- RF-07: Reportes JSON (canónico), HTML para web y SARIF cuando los hallazgos tengan ubicaciones adecuadas; PDF posterior.
- RF-08: CLI para CI no interactiva; estados y códigos de salida previsibles.
- RF-09: Diferenciar seguridad detectada, exposición observada, explotabilidad inferida y riesgo de negocio.
- RF-10: Evidencia humana incluida en informes y audit trail, con control de acceso y datos minimizados.

## 7. Requisitos no funcionales

- Privacidad: sin enviar código a LLM externos por defecto; requerir opt-in/consentimiento y permitir proveedores configurables.
- Seguridad: artefactos no confiables; no ejecución de código de terceros en MVP; sin pruebas activas contra servicios externos sin autorización.
- Confiabilidad: reintentos limitados, idempotencia, persistencia y recuperación de análisis parciales.
- Observabilidad: cada tarea/agente deja eventos, latencia, costo cuando aplique y correlación con analysis_id.
- Costos: fixtures locales y adaptadores simulados para iteraciones sin consumo LLM.

## 8. MVP acotado (primera versión publicable)

Entrada: repositorio Python de demostración + `requirements.txt`/`pyproject.toml`, Dockerfile opcional. La detección inicial utiliza una fixture con hallazgo conocido y posteriormente integración real con una herramienta SAST/SCA. Resultado: un recorrido completo en CLI/API/web básico con pregunta humana, verificación y reporte versionado. No prometer «análisis profundo de todas las capas» en la primera versión.

## 9. Hipótesis a medir

- La verificación independiente reduce falsos positivos **sin empeorar el recall** más allá de un umbral preacordado.
- Preguntas humanas pertinentes mejoran la clasificación de casos ambiguos.
- Compartir el motor entre CLI y web evita divergencias de resultados.
- El costo/latencia de subagentes se justifica frente a un baseline determinista.

## 10. Límites comerciales

El diferencial no es «tener muchos agentes», sino entregar evidencia verificable, historial auditable y la colaboración humana integrada. Antes de vender: validar dataset, precisión, privacidad, licencias de escáneres, costos de modelos, SLA y responsabilidades legales.
