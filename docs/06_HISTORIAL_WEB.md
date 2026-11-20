# Historial de reportes en la web local

La página `/` permite crear una demo o abrir un análisis existente por su ID. Muestra el JSON y el número de revisión; los botones anterior/siguiente consultan el historial sin reemplazarlo.

## Diseño y uso

El HTML/CSS/JavaScript vive en `src/sentinelforge/web.py`. No requiere Node ni nuevas dependencias. La web llama a los endpoints existentes, que siguen usando `AnalysisService`. La interfaz presenta datos y estados; el servicio y SQLite controlan las escrituras.

Para agregar una limitación, abre la última revisión, escribe una nota y guarda. Una versión histórica permite consulta; guardar requiere volver a la última. Si otra sesión cambió el reporte, la web muestra el conflicto y conserva la nota. Actualiza a la última revisión, revisa el contexto y vuelve a guardar.

Las notas solo agregan limitaciones de demo: no verifican declaraciones humanas ni modifican evidencia. Los reportes se muestran con `textContent`, evitando interpretar su contenido como HTML. Las rutas codifican el ID del análisis.

Cuando crear devuelve un ID, la página lo conserva inmediatamente en el campo de apertura. Si falla la consulta posterior del reporte, se puede recuperar con «Abrir análisis» usando ese ID.

## Evidencia de comportamiento

Verificado en navegador local el 20 de noviembre de 2026:

- Crear demo, guardar revisión 2 y volver a revisión 1, donde guardar queda deshabilitado.
- Abrir el mismo ID en una segunda sesión.
- Guardar desde la primera y provocar conflicto desde la segunda: la nota se conserva, guardar queda bloqueado hasta actualizar.
- Actualizar y guardar la nota conservada como nueva revisión.
- Una nota con `<b>nota literal</b>` aparece como texto dentro del reporte.

## Límites y aprendizaje

No hay listado general de análisis: se necesita conservar el ID. El borrador de nota vive en la página; cerrar o recargar pierde el texto no guardado. Cambiar a otro análisis o crear uno nuevo limpia el borrador tras abrir correctamente el destino. Un fallo de red permite reintentar, pero no garantiza que la solicitud anterior no se haya guardado; el backend evita duplicar la última revisión idéntica. No hay autenticación ni exposición pública autorizada.

Preguntas de repaso: ¿por qué se envía `expected_revision`? ¿Por qué una nota humana no es evidencia confirmada? ¿Qué diferencia hay entre el historial SQLite y un borrador que todavía vive en el navegador?
