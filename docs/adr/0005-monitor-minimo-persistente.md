# ADR 0005: Monitor optativo con respuestas inmutables

- **Estado:** implementado localmente
- **Fecha:** 2026-11-20

## Contexto

La investigación simulada conserva fuentes y decisiones, pero no admite contexto humano real. El producto requiere registrar aportes humanos sin promoverlos a evidencia y terminar los procesos de CI sin esperar entrada interactiva.

## Decisión

Activar una pregunta por análisis con `monitored=true`. Guardar pregunta y respuesta por separado, de forma inmutable. Usar UUID de envío para idempotencia. La respuesta puede recibirse antes del reporte o generar una nueva revisión después del cierre, en una transacción con los eventos.

La pregunta puede quedar pendiente mientras el ciclo termina. Los informes del Monitor permanecen `PARTIAL`, también después de responder, porque la declaración está `unverified`. Conservar los estados y contratos anteriores de checkpoint y reporte.

## Consecuencias

- La migración aditiva de esquema 3 a 4 conserva los datos anteriores sin inventar preguntas.
- CLI, API y web llaman al mismo servicio. No se añaden dependencias ni servicios externos.
- El autor y rol son metadatos declarados; no existe autenticación todavía.
- Una primera respuesta queda inmutable. Las correcciones y múltiples preguntas requerirán otra iteración.
- La revisión contrasta de nuevo la fixture original, pero no investiga ni verifica semánticamente la declaración humana.
- No hay reanudación de subgrafos reales ni SSE; el ciclo ya terminado conserva su checkpoint y añade una revisión del informe.
