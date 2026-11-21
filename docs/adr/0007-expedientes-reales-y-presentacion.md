# ADR 0007: expedientes reales y adaptadores de presentación

- **Estado:** implementado localmente
- **Fecha:** 2026-11-20

## Contexto

El detector local necesitaba conservar su resultado y ofrecerlo en la web sin confundirlo con la demo ni permitir que HTTP leyera rutas arbitrarias del host. La presentación JSON directa dificultaba revisar señales y contexto.

## Decisión

Crear `ScanCase` discriminado, con revisiones y respuestas inmutables en tablas propias del esquema SQLite 5. Mantener el resultado técnico separado del contexto humano. La identidad determinista del resultado permite deduplicar creaciones y UUID de envío permite reintentar respuestas.

Recibir un archivo elegido explícitamente como bytes limitados, analizarlo con el mismo worker del servicio y descartar el código fuente tras la solicitud. No aceptar rutas del servidor. Mantener la API local y el alcance de una regla y una pregunta por expediente.

La web usa assets del paquete Python y visualiza datos estructurados. La CLI usa Rich ya disponible, ahora declarado directamente, con JSON limpio para pipes y formato explícito. Los gráficos describen estados y límites reales, no una puntuación de seguridad.

## Consecuencias

- Las declaraciones humanas y señales siguen `unverified`; los expedientes con señales permanecen `PARTIAL`.
- No se introduce framework frontend, instalación, servicio externo ni proveedor LLM.
- Sin fuente retenida, verificar después necesita reingreso de bytes y contraste del hash. Esta entrega no implementa investigación independiente real.
- No se resuelven autenticación, aislamiento duro de memoria, multiusuario, SSE, edición de respuestas o retención/limpieza de producción. La API sigue ligada a loopback.
