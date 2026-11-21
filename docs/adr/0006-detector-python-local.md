# ADR 0006: detector Python acotado y reporte separado

- **Estado:** implementado localmente
- **Fecha:** 2026-11-20

## Contexto

La demo persistente y Monitor usan contratos expresamente ficticios. La siguiente capa debe producir una señal sobre bytes reales sin ejecutar código ni confundirla con evidencia de explotabilidad. Abrir rutas del host desde HTTP ampliaría la superficie de entrada antes de disponer de autorización y cuotas.

## Decisión

Añadir `scan-file` y `AnalysisService.scan_local_file` para un archivo `.py` relativo a una raíz local confiable, con límite de 64 KiB. Usar AST de la biblioteca estándar para observar `shell=True` literal en llamadas reconocidas de subprocess. Un lector dedicado rechaza rutas especiales y enlaces y comprueba cambios detectables del archivo.

Ejecutar el parser en un proceso hijo confiable con `-I -S`, límite de tiempo y salidas estructuradas. El artefacto se transmite por stdin, sin ejecutarlo. Un fallo produce un error explícito, nunca un escaneo exitoso sin señales.

Crear `LocalScanReport` discriminado y versionado, con hash, ubicación y señal `unverified`. Mantener sin cambios los contratos y el esquema SQLite de la demo. No incorporar todavía persistencia, API de archivos ni Monitor a este reporte.

## Consecuencias

- No hay nuevas dependencias, instalaciones, procesos de shell, proveedores LLM ni escáneres externos.
- El resultado es determinista para la misma entrada y versiones; los errores técnicos se distinguen de las señales.
- La regla es incompleta e intencionalmente conservadora con alias; no prueba flujos de datos ni explotabilidad.
- El proceso contiene fallos del parser, pero no es un sandbox de recursos o permisos. La lectura tampoco elimina todas las carreras de filesystem en Windows.
- La próxima integración necesita diseñar almacenamiento de resultados reales, su investigación independiente y un contrato de reporte compatible antes de conectarlos al historial web.
