(() => {

  const el = id => document.getElementById(id);
  let current = null, latestNumber = 0, busy = false, conflicted = false;
  let monitorQuestion = null, monitorDraft = null, monitorBlocked = false;
  let pendingWorkflow = null;
  function controls() {
    document.querySelectorAll('#lab button').forEach(button => button.disabled = busy);
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

})();
