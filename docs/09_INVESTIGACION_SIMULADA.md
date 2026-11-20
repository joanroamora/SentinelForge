# Investigación y verificación simuladas

## Problema y vocabulario

El ciclo persistente conservaba el progreso, pero sus fases eran marcadores. Esta capa introduce tres roles deterministas: detector ficticio, investigador ficticio y verificador de fixtures. Una **señal** plantea una sospecha. Una **hipótesis** cita la fuente que debería comprobarse. Una **decisión** registra lo que el verificador encontró al releer esa fuente.

Los componentes comparten proceso y código del proyecto, pero el verificador consulta el catálogo original y recalcula SHA-256 en vez de aceptar la explicación del investigador. Esto prueba separación de responsabilidades sobre datos controlados; no es un escáner ni una verificación de vulnerabilidades reales.

## Casos controlados

| Fixture | Fuente original | Resultado esperado |
|---|---|---|
| `auth-disabled` | JSON con `auth_required=false` | `supported_in_fixture` |
| `auth-enabled` | JSON con `auth_required=true` | `contradicted_in_fixture` |
| `source-missing` | Fuente ausente | `inconclusive` |

El detector ficticio emite la misma sospecha en los tres casos. El segundo caso permite mostrar una señal errónea controlada. No se presentan estos casos como una medición de falsos positivos o negativos de un detector real.

Las fuentes son cadenas JSON del catálogo cerrado de `simulation.py`; sus URI `sentinelforge://fixtures/...` no se resuelven en la red ni abren rutas del equipo.

## Integración con el ciclo

- Al entrar en `DETECTING`, se guarda la señal ficticia.
- En `INVESTIGATING`, se guarda la hipótesis con referencias y hash.
- En `VERIFYING`, se guarda la decisión, la fuente original y su hash recalculado.
- `REPORTING` conserva el resultado y `COMPLETED` publica el reporte.

Cada transición guarda checkpoint, traza y evento en una transacción. El cierre incluye además el reporte. Los reintentos devuelven el checkpoint histórico sin regenerar ni duplicar resultados. Un fallo al guardar la traza revierte todo el avance.

El reporte conserva el contrato `1.0`: añade evidencia `demo_fixture` y una limitación con la decisión y su alcance. Los hallazgos permanecen `inconclusive`, las evidencias `simulated` y las declaraciones humanas `unverified`. Al ensamblar el reporte se vuelve a comprobar que la decisión almacenada coincide con la fuente original.

## API local

Se conserva el POST sin cuerpo y su fixture predeterminada. También puede seleccionarse un caso:

```http
POST /v1/demo-workflows
Content-Type: application/json

{"fixture_id":"auth-enabled"}
```

Se avanza mediante los endpoints existentes con `expected_version`. La traza actual se consulta en `GET /v1/demo-workflows/{analysis_id}/investigation`, con contrato `SimulationTrace` versión `1.0`. Devuelve 404 `simulation_not_found` si no existe o pertenece a un ciclo anterior sin investigación.

Para correlacionar la investigación con un checkpoint leído previamente, se consulta `?checkpoint_version=3`. Devuelve la traza exacta de esa versión; una versión sin traza produce 404 y un número no válido, 422. Sin este parámetro se consulta el último snapshot y las lecturas de checkpoint/investigación son independientes: otra solicitud podría avanzar entre ambas.

Se rechazan fixtures desconocidas y campos adicionales con 422. El cliente no puede enviar decisiones, fuentes, instrucciones ni resultados arbitrarios.

## Ejemplo CLI en PowerShell

```powershell
$env:SENTINELFORGE_DATABASE_PATH = ".local\investigacion-demo.sqlite3"
$inicio = .\.venv\Scripts\python.exe -m sentinelforge.cli workflow-start --fixture-id auth-enabled | ConvertFrom-Json
$analysisId = $inicio.analysis_id
foreach ($version in 1..5) {
    .\.venv\Scripts\python.exe -m sentinelforge.cli workflow-advance $analysisId --expected-version $version
}
.\.venv\Scripts\python.exe -m sentinelforge.cli workflow-investigation $analysisId
```

El resultado esperado es `contradicted_in_fixture`. Los comandos son no interactivos y usan la `.venv` existente. La web sigue mostrando el reporte final y su evidencia; para consultar los componentes separados se usa CLI o Swagger local.

## Persistencia y compatibilidad

La migración aditiva de esquema 2 a 3 crea `workflow_simulations`, con snapshots inmutables enlazados por ID y versión al checkpoint. Las migraciones anteriores permiten abrir instalaciones con esquema 1. No se reescriben reportes, eventos ni checkpoints existentes.

Los ciclos antiguos sin traza siguen su recorrido anterior. Se evita atribuirles retrospectivamente una investigación que no realizaron. Solo los ciclos nuevos creados mediante el servicio reciben la investigación simulada.

## Límites y pruebas

La API permanece local y sin autenticación. No se ejecutan artefactos, no se reciben archivos ni se hacen llamadas LLM. Las pruebas de texto manipulador cubren esta lógica determinista; no acreditan resistencia general a prompt injection de un futuro modelo.

Las pruebas comprueban los tres casos, referencias y hashes alterados, fuentes ausentes, decisiones falsificadas, preservación de declaraciones humanas, reinicios, reintentos, migración, concurrencia e integridad transaccional. Se ejecutan con:

Validación local del 20 de noviembre de 2026: **72 pruebas aprobadas y Ruff limpio**, usando Python 3.14.10 de `.venv`. También se recorrieron los tres casos con Uvicorn local y se consultó su traza histórica de versión 2. La base real migró de 2 a 3, con copia previa y comparación que confirmó que los nueve reportes anteriores permanecían intactos. Esta capa no se ha publicado ni ejecutado en CI remota.

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
```

Preguntas de repaso: ¿por qué la señal no basta para concluir? ¿Qué fuente consulta el verificador? ¿Por qué los ciclos antiguos no reciben una traza inventada? ¿Qué diferencia hay entre respaldo en una fixture y evidencia de una vulnerabilidad real?
