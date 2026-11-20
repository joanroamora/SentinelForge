# Confiabilidad HTTP y validación continua

## Problema y vocabulario

SQLite usa llamadas síncronas: la función espera a que termine la operación. Ejecutarlas directamente dentro de un handler `async def` retiene el **event loop**, el bucle que coordina las solicitudes asíncronas. Una espera del almacenamiento podía retrasar también `/health`.

**CI (Continuous Integration)** ejecuta comprobaciones automáticas sobre cambios compartidos. Esta capa prepara esas comprobaciones y corrige la espera del almacenamiento en las rutas originales.

## Diseño y decisión

Todos los endpoints que acceden al servicio SQLite se declaran con `def`. FastAPI los ejecuta mediante su thread pool. `/health` y la página HTML siguen siendo asíncronos porque no esperan almacenamiento. No se cambia el contrato HTTP ni la estructura de la base.

El intercambio es acotado: usar hilos permite que una llamada síncrona en espera no retenga el event loop, pero no elimina la serialización de escrituras de SQLite ni la capacidad finita del pool. Véase [ADR 0002](adr/0002-http-sin-bloqueo-y-ci.md).

## Prueba de comportamiento

`tests/test_http_responsiveness.py` retiene una operación del servicio con eventos de sincronización y consulta `/health` en la misma aplicación. Antes de liberar el servicio, health debe responder y la operación debe seguir pendiente. Luego se libera y se comprueba la respuesta original.

La prueba cubre crear análisis, consultar análisis y consultar el reporte latest. Un temporizador de seguridad libera el servicio incluso si una regresión bloquea el event loop, haciendo que el test falle en vez de quedar colgado. Los tiempos son guardas del test, no una medición de rendimiento. El almacenamiento retenido es simulado; no demuestra tolerancia a saturación ni a corrupción de SQLite.

Resultado local del 20 de noviembre de 2026: **14 pruebas aprobadas y Ruff sin errores**, ejecutadas con Python 3.14.10 dentro de `.venv`.

## Workflow validado

`.github/workflows/ci.yml` ejecuta Ruff y pytest en una matriz de Ubuntu 24.04 y Windows 2022, con Python 3.11 y 3.14.10. El primero comprueba el mínimo declarado; el segundo coincide con la versión local validada. La CI crea una `.venv` efímera e invoca su Python para instalar y ejecutar herramientas.

El workflow responde a PR hacia `dev`/`main` y a push en esas ramas. Solo tiene permiso de lectura de contenido, no conserva credenciales en el checkout y fija las acciones oficiales a sus SHA. No realiza despliegues ni necesita secretos. `workflow_dispatch` podrá usarse normalmente cuando el archivo exista en la rama predeterminada.

La [primera ejecución remota](https://github.com/joanroamora/SentinelForge/actions/runs/44798059792) del 20 de noviembre de 2026 terminó con éxito en las cuatro combinaciones para el commit `18bc4e3`, dentro del PR #3. Aún no hay lockfile: las dependencias se resuelven desde los rangos de `pyproject.toml`.

## Validar localmente en Windows

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
```

## Límites y repaso

Esta capa no añade readiness de la base, migraciones, respaldo, autenticación ni escáneres. `/health` sigue indicando que la aplicación responde; no certifica que SQLite pueda escribir.

Preguntas: ¿por qué `async def` puede bloquear? ¿Qué demuestra health durante una espera del servicio? ¿Qué diferencia hay entre definir una CI y observar que pasa en los runners remotos?
