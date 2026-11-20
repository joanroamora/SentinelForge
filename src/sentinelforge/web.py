"""Local demo interface; all report operations go through the HTTP API."""

WEB_PAGE = """<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>SentinelForge — historial local</title>
  <style>
    :root { color-scheme: dark; font-family: system-ui, sans-serif; background:#0c1420;
      color:#e6edf5; }
    body { margin:0; } main { max-width:1000px; margin:auto; padding:32px 20px; }
    h1 { margin-bottom:8px; } p { line-height:1.5; } a { color:#72dfc4; }
    section { border:1px solid #354256; background:#141f30; border-radius:14px;
      padding:22px; margin:20px 0; }
    label { display:block; margin:14px 0 8px; }
    input, textarea, button { font:inherit; border:1px solid #718198; border-radius:7px;
      padding:10px; box-sizing:border-box; }
    input, textarea { width:100%; color:inherit; background:#0c1420; }
    button { cursor:pointer; margin:8px 8px 8px 0; background:#8be2cc; color:#10241f; }
    button:disabled { opacity:.45; cursor:default; }
    button:focus-visible, input:focus-visible, textarea:focus-visible { outline:3px solid #b8a3ff; }
    #status { min-height:1.5em; color:#ffdd91; } pre { white-space:pre-wrap;
      overflow-wrap:anywhere; line-height:1.5; } .muted { color:#b8c6d6; }
    [hidden] { display:none; }
  </style>
</head>
<body><main>
  <h1>SentinelForge</h1>
  <p class="muted">Demo ficticia. No analiza ni ejecuta código. Expediente local con historial.</p>
  <section aria-labelledby="open-title">
    <h2 id="open-title">Abrir un análisis</h2>
    <button id="run">Crear análisis de demostración</button>
    <form id="open-form">
      <label for="analysis-id">ID de análisis existente</label>
      <input id="analysis-id" required maxlength="100" autocomplete="off">
      <button type="submit">Abrir análisis</button>
    </form>
  </section>
  <p id="status" role="status" aria-live="polite"></p>
  <section id="viewer" hidden aria-labelledby="report-title">
    <h2 id="report-title">Reporte</h2>
    <p id="version"></p>
    <button id="previous">Revisión anterior</button>
    <button id="next">Revisión siguiente</button>
    <button id="latest">Actualizar a la última revisión</button>
    <form id="note-form">
      <label for="note">Agregar limitación de demostración</label>
      <p class="muted">Esta nota no constituye evidencia verificada. Evita incluir secretos.</p>
      <textarea id="note" required maxlength="2000" rows="3"></textarea>
      <button id="save" type="submit">Guardar nueva revisión</button>
    </form>
    <p id="edit-hint" class="muted"></p>
    <pre id="result"></pre>
  </section>
  <a href="/docs">Documentación de la API</a>
</main>
<script>
  const el = id => document.getElementById(id);
  let current = null, latestNumber = 0, busy = false, conflicted = false;
  function controls() {
    document.querySelectorAll('button').forEach(button => button.disabled = busy);
    el('analysis-id').disabled = busy;
    el('note').disabled = busy;
    el('previous').disabled = busy || !current || current.revision <= 1;
    el('next').disabled = busy || !current || current.revision >= latestNumber;
    const canEdit = current && current.revision === latestNumber && !conflicted;
    el('save').disabled = busy || !canEdit;
    el('edit-hint').textContent = conflicted
      ? 'Hay cambios nuevos. Actualiza a la última revisión y revisa tu nota antes de guardar.'
      : canEdit ? '' : 'Para agregar una nota, abre la última revisión.';
  }
  function show(snapshot) {
    current = snapshot;
    el('viewer').hidden = false;
    el('version').textContent = `Análisis ${snapshot.report.analysis.id} · Revisión ` +
      `${snapshot.revision} de ${latestNumber}`;
    el('result').textContent = JSON.stringify(snapshot.report, null, 2);
    controls();
  }
  async function request(path, options) {
    const response = await fetch(path, options);
    if (!response.ok) {
      const error = new Error(response.status === 404 ? 'No se encontró el análisis o la revisión.'
        : response.status === 409 ? 'Otra solicitud guardó una revisión. Tu nota se conserva.'
        : response.status === 422 ? 'Revisa los datos enviados.' : 'Error al consultar el servidor.');
      error.status = response.status;
      throw error;
    }
    return response.json();
  }
  async function action(work) {
    if (busy) return;
    busy = true; controls(); el('status').textContent = 'Procesando…';
    try { await work(); el('status').textContent = 'Listo.'; }
    catch (error) {
      if (error.status === 409) conflicted = true;
      el('status').textContent = error.status ? error.message
        : 'No se pudo completar la solicitud. Tu nota se conserva; puedes reintentar.';
    } finally { busy = false; controls(); }
  }
  const base = id => '/v1/analyses/' + encodeURIComponent(id);
  async function openLatest(id, switching = false) {
    const snapshot = await request(base(id) + '/report-revisions/latest');
    latestNumber = snapshot.revision;
    conflicted = false;
    if (switching) el('note').value = '';
    el('analysis-id').value = snapshot.report.analysis.id;
    show(snapshot);
  }
  el('run').onclick = () => action(async () => {
    const report = await request('/v1/analyses', { method:'POST' });
    el('analysis-id').value = report.analysis.id;
    await openLatest(report.analysis.id, true);
  });
  el('open-form').onsubmit = event => {
    event.preventDefault();
    const id = el('analysis-id').value.trim();
    if (id) action(() => openLatest(id, !current || id !== current.report.analysis.id));
  };
  el('latest').onclick = () => action(() => openLatest(current.report.analysis.id));
  for (const [button, offset] of [['previous', -1], ['next', 1]]) {
    el(button).onclick = () => action(async () => {
      show(await request(base(current.report.analysis.id) + '/reports/' + (current.revision + offset)));
    });
  }
  el('note-form').onsubmit = event => {
    event.preventDefault();
    if (!current || conflicted || current.revision !== latestNumber) return;
    const note = el('note').value;
    if (!note.trim()) { el('status').textContent = 'Escribe una nota con texto visible.'; return; }
    action(async () => {
      const snapshot = await request(base(current.report.analysis.id) + '/report-revisions', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body:JSON.stringify({expected_revision:current.revision, limitation:note})
      });
      latestNumber = snapshot.revision;
      el('note').value = '';
      show(snapshot);
    });
  };
  controls();
</script></body></html>"""
