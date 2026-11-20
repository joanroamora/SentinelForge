# ADR 0002: llamadas SQLite fuera del event loop y CI mínima

- **Estado:** implementado en PR #3; primera ejecución remota de CI aprobada
- **Fecha:** 2026-11-20

## Contexto

Las tres rutas HTTP originales llamaban a SQLite síncrono dentro de handlers asíncronos. Una espera podía bloquear el event loop y retrasar solicitudes independientes. Las comprobaciones de calidad se ejecutaban manualmente.

## Decisión

Declarar con `def` los handlers que llaman al servicio SQLite y conservar `async def` donde no se hace I/O síncrono. Validar con una operación retenida mientras `/health` responde. Preparar GitHub Actions con Python 3.11 y 3.14.10 en Ubuntu y Windows; cada job usa una `.venv` y ejecuta Ruff/pytest.

## Consecuencias y límites

- No se añaden dependencias al proyecto ni cambia el contrato HTTP.
- La capacidad del pool de hilos es finita; SQLite conserva sus restricciones de escritura.
- El workflow tiene permisos de solo lectura y acciones fijadas por SHA. No despliega.
- La [primera corrida remota](https://github.com/joanroamora/SentinelForge/actions/runs/44798059792) aprobó las cuatro combinaciones del workflow para `18bc4e3`.
- Los rangos de dependencias siguen sin un archivo de bloqueo; no se garantiza resolución idéntica entre fechas.

## Referencias

- [FastAPI: concurrencia y handlers síncronos](https://fastapi.tiangolo.com/async/).
- [actions/checkout v7.0.1](https://github.com/actions/checkout/releases/tag/v7.0.1): SHA `3d3c42e5aac5ba805825da76410c181273ba90b1`.
- [actions/setup-python v7.1.0](https://github.com/actions/setup-python/releases/tag/v7.1.0): SHA `6d4fd22b20465ccc0f7354476588e8df7c9ca0e0`.
