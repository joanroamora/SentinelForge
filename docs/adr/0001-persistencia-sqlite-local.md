# ADR 0001: persistencia local con SQLite

- **Estado:** aceptado para desarrollo local
- **Fecha:** 2026-11-19

## Contexto

Los reportes de la vertical slice vivían en memoria y no podían consultarse después de reiniciar el proceso. El proyecto requiere persistencia recuperable en desarrollo y PostgreSQL en un despliegue posterior.

## Decisión

Usar SQLite de la biblioteca estándar para guardar JSON de reportes, revisiones inmutables y eventos append-only. Crear nuevas revisiones requiere informar la revisión esperada para evitar que una escritura concurrente sobrescriba cambios. La base vive por defecto en `.sentinelforge/analyses.sqlite3`; la ruta puede configurarse con `SENTINELFORGE_DATABASE_PATH`. El servicio de aplicación mantiene una única interfaz para CLI y API.

## Consecuencias

- No se agrega ni instala ninguna dependencia.
- Un reinicio del proceso conserva reportes.
- Repetir la escritura del reporte más reciente es seguro; intentar cambiar contenido sin una revisión esperada actual falla explícitamente.
- SQLite sirve para desarrollo local. No resuelve autenticación, control de acceso multiusuario, respaldo, retención, migraciones de producción ni ejecución paralela a escala.
- La reanudación real requiere primero un flujo de análisis pausable; la demo actual solo registra el evento inicial del reporte.
