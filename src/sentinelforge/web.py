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
    <button id="run-monitored">Crear demo con pregunta</button>
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
  <section id="monitor" hidden aria-labelledby="monitor-title">
    <h2 id="monitor-title">Monitor</h2>
    <p id="monitor-state"></p>
    <p id="monitor-prompt"></p>
    <p id="monitor-context" class="muted"></p>
    <p class="muted">El autor y el rol son declarados por quien responde. La respuesta queda
      sin verificar y no confirma hallazgos. No incluyas contraseñas, claves ni otros secretos.</p>
    <form id="monitor-form">
      <label for="monitor-actor">Autor de la respuesta</label>
      <input id="monitor-actor" required maxlength="120" autocomplete="off">
      <label for="monitor-role">Rol declarado</label>
      <input id="monitor-role" required maxlength="80" autocomplete="off">
      <label for="monitor-text">Respuesta de contexto</label>
      <textarea id="monitor-text" required maxlength="4000" rows="4"></textarea>
      <button id="monitor-submit" type="submit">Guardar respuesta sin verificar</button>
    </form>
    <p id="monitor-hint" class="muted"></p>
    <pre id="monitor-answer"></pre>
    <div id="monitor-unsent" hidden>
      <p class="muted">Tu borrador local no enviado se conserva aquí:</p>
      <pre id="monitor-unsent-text"></pre>
    </div>
  </section>
  <a href="/docs">Documentación de la API</a>
</main>
<script>
  const el = id => document.getElementById(id);
  let current = null, latestNumber = 0, busy = false, conflicted = false;
  let monitorQuestion = null, monitorDraft = null, monitorBlocked = false;
  let pendingWorkflow = null;
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
    const canAnswer = current && current.revision === latestNumber &&
      monitorQuestion && monitorQuestion.status === 'pending' && !monitorBlocked;
    for (const id of ['monitor-actor', 'monitor-role', 'monitor-text', 'monitor-submit']) {
      el(id).disabled = busy || !canAnswer;
    }
    el('monitor-hint').textContent = monitorBlocked
      ? 'Actualiza la última revisión para consultar la respuesta guardada. Tu borrador se conserva.'
      : monitorQuestion && monitorQuestion.status === 'answered'
        ? 'Respuesta guardada como declaración unverified. El informe sigue PARTIAL.'
        : current && current.revision !== latestNumber
          ? 'Para responder, abre la última revisión del reporte.' : '';
    el('run-monitored').textContent = pendingWorkflow
      ? 'Continuar demo con pregunta' : 'Crear demo con pregunta';
  }
  function renderMonitor() {
    const question = monitorQuestion;
    el('monitor').hidden = !question;
    if (!question) return;
    el('monitor-state').textContent = 'Estado actual de la pregunta: ' +
      (question.status === 'pending' ? 'pendiente' : 'respondida');
    el('monitor-prompt').textContent = question.prompt;
    el('monitor-context').textContent = `${question.reason} ${question.requested_evidence}`;
    el('monitor-form').hidden = question.status !== 'pending';
    el('monitor-answer').textContent = question.answer
      ? JSON.stringify(question.answer, null, 2) : '';
    const unsent = question.status === 'answered' && monitorDraft && el('monitor-text').value;
    el('monitor-unsent').hidden = !unsent;
    el('monitor-unsent-text').textContent = unsent
      ? JSON.stringify({actor:el('monitor-actor').value, role:el('monitor-role').value,
        text:el('monitor-text').value}, null, 2) : '';
  }
  function show(snapshot) {
    current = snapshot;
    el('viewer').hidden = false;
    el('version').textContent = `Análisis ${snapshot.report.analysis.id} · Revisión ` +
      `${snapshot.revision} de ${latestNumber}`;
    el('result').textContent = JSON.stringify(snapshot.report, null, 2);
    renderMonitor();
    controls();
  }
  async function request(path, options) {
    const response = await fetch(path, options);
    if (!response.ok) {
      let detail;
      try { detail = (await response.json()).detail; } catch { /* Keep a generic error. */ }
      const messages = {
        report_revision_conflict: 'Otra solicitud guardó una revisión. Tu nota se conserva.',
        monitor_submission_conflict: 'La clave de envío ya corresponde a otra respuesta. Actualiza el reporte.',
        monitor_question_already_answered: 'Otra solicitud ya respondió esta pregunta. Tu borrador se conserva.'
      };
      const error = new Error(messages[detail] || (response.status === 404
        ? 'No se encontró el análisis, la pregunta o la revisión.'
        : response.status === 409 ? 'El estado cambió. Actualiza el reporte antes de reintentar.'
        : response.status === 422 ? 'Revisa los datos enviados.' : 'Error al consultar el servidor.'));
      error.status = response.status;
      error.detail = detail;
      throw error;
    }
    return response.json();
  }
  async function action(work) {
    if (busy) return;
    busy = true; controls(); el('status').textContent = 'Procesando…';
    try { await work(); el('status').textContent = 'Listo.'; }
    catch (error) {
      if (error.detail === 'report_revision_conflict') conflicted = true;
      if (error.detail === 'monitor_submission_conflict' ||
          error.detail === 'monitor_question_already_answered') monitorBlocked = true;
      el('status').textContent = error.status ? error.message
        : 'No se pudo completar la solicitud. Tus borradores se conservan; puedes reintentar.';
    } finally { busy = false; controls(); }
  }
  const base = id => '/v1/analyses/' + encodeURIComponent(id);
  async function openLatest(id, switching = false) {
    const [snapshot, questions] = await Promise.all([
      request(base(id) + '/report-revisions/latest'), request(base(id) + '/questions')
    ]);
    const changedAnalysis = !current || current.report.analysis.id !== snapshot.report.analysis.id;
    if (switching || changedAnalysis) {
      el('note').value = '';
      for (const field of ['monitor-actor', 'monitor-role', 'monitor-text']) el(field).value = '';
      monitorDraft = null;
    }
    latestNumber = snapshot.revision;
    conflicted = false;
    monitorBlocked = false;
    monitorQuestion = questions[0] || null;
    el('analysis-id').value = snapshot.report.analysis.id;
    show(snapshot);
  }
  async function finishMonitoredWorkflow() {
    const pending = pendingWorkflow;
    el('analysis-id').value = pending.analysis_id;
    while (pending.version < 6) {
      const checkpoint = await request('/v1/demo-workflows/' +
        encodeURIComponent(pending.analysis_id) + '/advance', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body:JSON.stringify({expected_version:pending.version})
      });
      pending.version = checkpoint.version;
    }
    await openLatest(pending.analysis_id, true);
    pendingWorkflow = null;
  }
  async function openAnalysis(id) {
    try { await openLatest(id); }
    catch (error) {
      if (error.status !== 404) throw error;
      const checkpoint = await request('/v1/demo-workflows/' + encodeURIComponent(id));
      const questions = await request(base(id) + '/questions');
      if (!questions.length) throw error;
      pendingWorkflow = {analysis_id:id, version:checkpoint.version};
      await finishMonitoredWorkflow();
    }
  }
  el('run').onclick = () => action(async () => {
    const report = await request('/v1/analyses', { method:'POST' });
    el('analysis-id').value = report.analysis.id;
    await openLatest(report.analysis.id, true);
  });
  el('run-monitored').onclick = () => action(async () => {
    if (!pendingWorkflow) {
      const checkpoint = await request('/v1/demo-workflows', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body:JSON.stringify({monitored:true})
      });
      pendingWorkflow = {analysis_id:checkpoint.analysis_id, version:checkpoint.version};
      el('analysis-id').value = checkpoint.analysis_id;
    }
    await finishMonitoredWorkflow();
  });
  el('open-form').onsubmit = event => {
    event.preventDefault();
    const id = el('analysis-id').value.trim();
    if (id) action(() => openAnalysis(id));
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
  el('monitor-form').onsubmit = event => {
    event.preventDefault();
    if (!current || !monitorQuestion || monitorQuestion.status !== 'pending' ||
        monitorBlocked || current.revision !== latestNumber) return;
    const body = {text:el('monitor-text').value, actor:el('monitor-actor').value,
      role:el('monitor-role').value};
    if (Object.values(body).some(value => !value.trim())) {
      el('status').textContent = 'Completa autor, rol y respuesta con texto visible.';
      return;
    }
    const questionId = monitorQuestion.id;
    const fingerprint = JSON.stringify({analysis_id:current.report.analysis.id,
      question_id:questionId, ...body});
    if (!monitorDraft || monitorDraft.fingerprint !== fingerprint) {
      monitorDraft = {fingerprint, submission_id:crypto.randomUUID()};
    }
    action(async () => {
      await request(base(current.report.analysis.id) + '/questions/' +
        encodeURIComponent(questionId) + '/answers', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body:JSON.stringify({...body, submission_id:monitorDraft.submission_id})
      });
      await openLatest(current.report.analysis.id);
      monitorDraft = null;
      for (const field of ['monitor-actor', 'monitor-role', 'monitor-text']) el(field).value = '';
      renderMonitor();
    });
  };
  controls();
</script></body></html>"""
