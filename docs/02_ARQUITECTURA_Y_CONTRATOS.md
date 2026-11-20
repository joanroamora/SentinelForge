# 02 — Arquitectura y contratos (v0.1)

## 1. Decisión fundacional

**Monolito modular inicialmente**: un núcleo de dominio y ejecución compartido por CLI, API y web. Separar servicios solo si la carga y el aislamiento lo justifican. Python 3.11+, FastAPI para API/web, Typer para CLI, Pydantic para esquemas y LangGraph como orquestador sujeto a evaluación de versiones.

```text
Local CLI / CI Runner -----> [Application Service] <----- FastAPI / Web UI
          |                           |
          |                [Job & Event Service]
          |                           |
          +----------------> [Orchestrator / LangGraph]
                                      |
         +----------------------------+----------------------------+
         |                            |                            |
 [Detectors: code, deps]      [Finding Investigators]      [Monitor / Questions]
 [IaC, Docker, CI/CD]          [context, exposure, impact]   [human statements]
         |                            |                            |
         +----------------------------+----------------------------+
                                      |
                        [Independent Verification]
                                      |
                           [Report / Export Engine]
                                      |
                 [Persistence: audit, evidence, checkpoints]
```

### Regla de capas

- **Interfaces**: CLI/API/web, sin lógica propia de valoración de seguridad.
- **Application service**: inicia, reanuda, consulta y exporta ejecuciones.
- **Domain**: entidades, políticas, estados, invariantes, clasificación.
- **Orchestration**: coordinación de agentes/subgrafos, nunca el único custodio de evidencia.
- **Adapters**: detectores, herramientas MCP, LLMs, almacenamiento, notificaciones.

## 2. Agentes y subagentes

**Detection coordinators** por dominio: Code Security, Dependencies, Infrastructure, CI/CD. Priorizan señales de herramientas y artefactos; no dictaminan por sí solos.

**Finding Investigation Subgraph** (reutilizable por cada hallazgo):
- Context Investigator: rastrea origen, recurso y controles relevantes.
- Reachability Investigator: distingue exposición, rutas posibles y límites de análisis estático.
- Impact Investigator: examina impacto potencial y supuestos.

**Independent Verification Subgraph**:
- Evidence Verifier: verifica que archivos, reglas, ubicaciones, versiones y trazas soporten la afirmación.
- Challenge Verifier: busca controles compensatorios, explicaciones alternativas y contraejemplos.

**Reporting service**: sintetiza; no altera evidencias originales y asigna referencias únicas a cada elemento.

No es obligatorio crear un LLM distinto por cada subagente: cada subgrafo puede utilizar el mismo proveedor con prompts, herramientas, roles y acceso limitados. La independencia se mide por evidencia y procesos, no por número de llamadas al LLM.

## 3. Secuencia del análisis

1. `RECEIVED` -> validar artefacto, autorización, límites y registrar hash.
2. `DETECTING` -> invocar herramientas locales autorizadas y normalizar findings.
3. `INVESTIGATING` -> ejecutar subgrafos paralelos con límite de concurrencia.
4. `QUESTIONS_PENDING` (por hallazgo) -> publicar preguntas relevantes; no detener hallazgos independientes.
5. `VERIFYING` -> dos vías de verificación con acceso a fuentes originales.
6. `REPORTING` -> producir reporte inicial con estados confirmados / probables / inconclusos / descartados por evidencia.
7. `COMPLETED` o `PARTIAL` -> incluir limitaciones, preguntas abiertas y eventos de auditoría.
8. Respuesta humana posterior -> revisar solo subgrafo afectado y emitir `report_revision+1`.

Los estados son orientativos; el código debe modelar estados del análisis **y** estados por hallazgo, sin conflarlos.

## 4. Monitor: protocolo de interacción

- Preguntas `id`, `finding_id`, `prompt`, `reason`, `requested_evidence`, `priority`, `created_at`, `status`.
- Respuestas `id`, `question_id`, `actor_id`, `actor_role`, `text`, `created_at`, `attachments_metadata`, `verification_status`.
- Persistir el estado del grafo y un expediente SQL por separado; checkpoints no reemplazan el audit trail.
- Respuesta recibida -> validación de permisos -> append-only audit event -> reanudar nodo -> verificación -> nueva versión de informe.
- CI sin terminal interactiva: registrar pregunta y retornar un informe `PARTIAL` con referencia al panel web; la política de CI decide `pass | warn | fail` de forma determinista.
- Nunca pedir secretos, claves privadas o muestras biométricas.

## 5. Modelo de datos mínimo

- `Analysis` (`id`, `artifact_hash`, `mode`, `status`, `created_at`, `version`)
- `Artifact` (`id`, `analysis_id`, `origin`, `sha256`, `type`, `retention_policy`)
- `Finding` (`id`, `analysis_id`, `rule_id`, `location`, `severity`, `confidence`, `verification_status`)
- `Evidence` (`id`, `finding_id`, `kind`, `source`, `locator`, `sha256`, `collected_at`)
- `Question`, `HumanStatement`, `VerificationDecision`, `ReportRevision`, `AuditEvent`
- `AgentRun` (`id`, `analysis_id`, `finding_id`, `agent_type`, `model`, `cost`, `latency`, `status`, `trace_id`)

Tipos de evidencia explícitos: `scanner_output`, `source_file`, `configuration`, `authorized_test`, `human_statement`, `external_advisory`. Toda conclusión enlaza a `evidence_ids` y define limitaciones.

## 6. Contratos externos propuestos

```http
POST /v1/analyses             # artefacto + mode + policy
GET  /v1/analyses/{id}        # estado y progreso
GET  /v1/analyses/{id}/events # eventos SSE
GET  /v1/analyses/{id}/questions
POST /v1/analyses/{id}/answers
GET  /v1/analyses/{id}/reports/latest
GET  /v1/analyses/{id}/reports/{revision}
```

La API posterior debe añadir autentificación, autorización por análisis, cuotas, idempotency keys, validación de archivos, retención y limpieza. No exponer una API pública sin esos controles.

```text
sentinelforge scan ./my-project --mode autonomous --format json
sentinelforge scan ./my-project --mode monitored --server https://example.invalid
sentinelforge status <analysis-id> --server https://example.invalid
sentinelforge report <analysis-id> --format sarif --server https://example.invalid
```

**Estos comandos describen la interfaz objetivo; aún no están implementados.** Para CI, usar instalación efímera en `.venv` y ejecución no interactiva. Salidas recomendadas: 0 = ejecución exitosa sin bloqueo de política, 1 = bloqueo de política de hallazgos, 2 = error técnico, 3 = ejecución incompleta según política. Documentar explícitamente antes de implementar.

## 7. Persistencia

- Desarrollo: SQLite y checkpointer persistente compatible, con pruebas de pausa/reanudación tras reiniciar el proceso.
- Producción: PostgreSQL para entidades y checkpoints, migraciones, respaldos y control de acceso.
- Evidencias y artefactos: almacén de objetos con hashes y política de retención en producción; carpetas locales protegidas en dev.
- Reports append-only o versionados; no reescribir una declaración humana original.

## 8. Seguridad y confianza

- Sin ejecución de código de terceros, sin network scanning, sin SSRF y sin acceso libre al filesystem del host.
- Bloquear traversal, symlinks, zip bombs; limitar tamaño, profundidad y cantidad de archivos.
- Separación de permisos para agentes; LLM output siempre no confiable, validado con esquemas.
- Prompt injection en README/comentarios es dato no confiable, no instrucción operativa.
- No exfiltrar código o secretos a modelos externos sin configuración/consentimiento explícito.
- No rebajar hallazgos sin evidencia técnica independiente; registrar también contradicciones y falsos negativos detectados.

## 9. DevOps y observabilidad

- Pruebas unitarias, integración y golden fixtures en CI.
- Logs JSON con `analysis_id`, `finding_id`, `agent_run_id`, sin datos sensibles.
- OpenTelemetry para latencia, traces y fases; métricas de tokens/costo cuando haya LLM.
- Generación SARIF 2.1.0 para hallazgos adecuados, con fingerprints estables; JSON canónico interno.
- Infraestructura en código más adelante, no durante la primera fase académica.
