(() => {
  'use strict';
  const el = id => document.getElementById(id);
  const names = {overview:'Vista general',new:'Nuevo análisis',history:'Expedientes',case:'Expediente',lab:'Laboratorio demo'};
  const states = {COMPLETED:['Inspección terminada','teal'],PARTIAL:['Revisión pendiente','amber'],ERROR:['Error técnico','red']};
  let rows = [], offset = 0, selected = null, current = null, latestRevision = 0, busy = false, draft = null, activeView='overview';
  let reviewFile=null, reviewDraft=null, traceFile=null, traceDraft=null;
  const make = (tag, text, cls) => { const node=document.createElement(tag); if(text!==undefined) node.textContent=text; if(cls)node.className=cls; return node; };
  const short = id => id.replace('scan-','').slice(0,12);
  const date = value => new Intl.DateTimeFormat('es',{dateStyle:'medium',timeStyle:'short'}).format(new Date(value));
  function badge(status) { const [label,cls]=states[status]; return make('span',label,'badge '+cls); }
  function notice(message,error=false) { el('app-status').hidden=!message; el('app-status').textContent=message; el('app-status').className='notice'+(error?' error':''); }
  async function request(path,options) {
    const response=await fetch(path,options);
    if(!response.ok) {
      let code=''; try { code=(await response.json()).detail; } catch { /* Generic error below. */ }
      const messages={source_too_large:'El archivo supera los 64 KiB permitidos.',source_path_invalid:'Selecciona un nombre de archivo Python válido.',unsupported_file_type:'Solo se admiten archivos .py.',scanner_busy:'El motor está ocupado. Reintenta en unos segundos.',monitor_submission_conflict:'La clave de envío corresponde a otro contenido. Tu borrador se conserva.',monitor_question_already_answered:'La pregunta ya fue respondida. Actualiza el expediente; tu borrador se conserva.'};
      Object.assign(messages,{source_hash_mismatch:'La huella del archivo no coincide con la fuente original. No se modificó el expediente.',source_review_already_recorded:'Ya se guardó una corroboración. Actualiza a la última revisión.',source_review_submission_conflict:'Esta clave de envío corresponde a otro expediente.',source_verifier_timeout:'La comprobación superó su tiempo límite. Puedes reintentar.',source_verifier_failed:'El verificador no pudo terminar. No se creó una revisión.',source_verifier_invalid_python:'El verificador no pudo interpretar esta fuente. El expediente conserva su estado.'});
      Object.assign(messages,{lineage_review_required:'Primero corrobora todas las señales con la fuente original.',lineage_already_recorded:'Ya se guardó una investigación. Actualiza a la última revisión.',lineage_submission_conflict:'Esta clave de envío corresponde a otro expediente.',lineage_worker_timeout:'La investigación superó su tiempo límite. Puedes reintentar.',lineage_worker_failed:'La investigación no pudo terminar. No se creó una revisión.',lineage_invalid_output:'No se obtuvo un resultado válido. El expediente conserva su estado.'});
      const error=new Error(messages[code] || (response.status===404?'No se encontró el expediente o la revisión.':response.status===422?'Revisa los datos enviados.':'No se pudo completar la operación. Puedes reintentar.'));
      error.code=code; throw error;
    }
    return response.json();
  }
  function controls() {
    document.querySelectorAll('.view:not(#view-lab) button').forEach(button=>button.disabled=busy);
    el('scan-file').disabled=busy; el('scan-submit').disabled=busy||!selected;
    el('scan-submit').textContent=busy?'Analizando y guardando…':'Analizar y guardar expediente ↗';
    el('history-previous').disabled=busy||offset===0; el('history-next').disabled=busy||rows.length<25;
    el('case-previous').disabled=busy||!current||current.revision<=1;
    el('case-next').disabled=busy||!current||current.revision>=latestRevision;
    const canAnswer=current&&current.revision===latestRevision&&current.question?.status==='pending';
    for(const id of ['case-actor','case-role','case-text','case-answer-submit']) el(id).disabled=busy||!canAnswer;
    const canReview=current&&current.revision===latestRevision&&current.report.status==='COMPLETED'&&current.report.signals.length&&!current.source_review;
    el('case-review-file').disabled=busy||!canReview;
    el('case-review-submit').disabled=busy||!canReview||!reviewFile;
    const canTrace=current&&current.revision===latestRevision&&!current.argument_investigation&&current.source_review?.decisions.every(item=>item.result==='pattern_reproduced');
    el('case-trace-file').disabled=busy||!canTrace;
    el('case-trace-submit').disabled=busy||!canTrace||!traceFile;
  }
  async function action(work) { if(busy)return; busy=true;controls();notice('Procesando en el entorno local…'); try {await work();notice('Operación completada.');}catch(error){notice(error instanceof TypeError?'No se pudo conectar con el servidor. Tu borrador se conserva.':error.message,true);}finally{busy=false;controls();} }
  function view(name) {
    document.querySelectorAll('.view').forEach(section=>section.hidden=section.id!=='view-'+name);
    document.querySelectorAll('[data-view]').forEach(link=>link.classList.toggle('active',link.dataset.view===(name==='case'?'history':name)));
    el('view-name').textContent=names[name];
    if(activeView!==name)window.scrollTo(0,0);activeView=name;
  }
  function empty(container,title,description) { container.replaceChildren(); const box=make('div',undefined,'empty-state');box.append(make('strong',title),make('p',description));container.append(box); }
  function renderDashboard(items) {
    el('metric-total').textContent=items.length; el('metric-signals').textContent=items.reduce((n,item)=>n+item.report.signals.length,0);
    el('metric-pending').textContent=items.filter(item=>item.question?.status==='pending').length;
    el('metric-errors').textContent=items.filter(item=>item.status==='ERROR').length; el('nav-count').textContent=items.length+(items.length===25?'+':'');
    const recent=el('recent-list'); recent.replaceChildren();
    if(!items.length)empty(recent,'Tu primer expediente empieza aquí.','Selecciona Nuevo análisis o prueba uno de los ejemplos controlados.');
    for(const item of items.slice(0,5)) {
      const row=make('div',undefined,'recent-item'), label=make('div',item.report.source.relative_path,'recent-name');
      label.append(make('small',`${short(item.id)} · ${item.report.signals.length} señales`));
      const open=make('button','↗');open.type='button';open.setAttribute('aria-label','Abrir '+item.report.source.relative_path);open.onclick=()=>{location.hash='case/'+item.id;};
      row.append(make('span','py','file-icon'),label,badge(item.status),open);recent.append(row);
    }
    const palette={COMPLETED:'#39b899',PARTIAL:'#e5ba6f',ERROR:'#d98178'},segments=[];let start=0;
    el('chart-total').textContent=items.length;el('chart-legend').replaceChildren();
    for(const state of Object.keys(palette)) {
      const count=items.filter(item=>item.status===state).length,end=start+(items.length?count/items.length*100:0);
      segments.push(`${palette[state]} ${start}% ${end}%`); start=end;
      const row=make('div',undefined,'legend-row'),dot=make('span',undefined,'legend-dot');dot.style.background=palette[state];row.append(dot,make('span',state==='COMPLETED'?'Terminados':state==='PARTIAL'?'Por revisar':'Errores'),make('strong',count));el('chart-legend').append(row);
    }
    el('status-chart').style.background=items.length?'conic-gradient('+segments.join(',')+')':'#edf1f5';
    el('status-chart').setAttribute('role','img');el('status-chart').setAttribute('aria-label',items.length+' expedientes. '+items.filter(x=>x.status==='PARTIAL').length+' por revisar.');
  }
  function renderHistory() {
    const term=el('history-search').value.toLowerCase(),body=el('history-body');body.replaceChildren();
    const filtered=rows.filter(item=>(item.report.source.relative_path+' '+item.id).toLowerCase().includes(term));
    for(const item of filtered) {
      const tr=make('tr'),file=make('td',item.report.source.relative_path);file.append(make('small',short(item.id),'mono'));
      const status=make('td');status.append(badge(item.status));const open=make('button','Abrir ↗');open.onclick=()=>{location.hash='case/'+item.id;};
      const link=make('td');link.append(open);tr.append(file,status,make('td',item.report.signals.length),make('td',item.question?(item.question.status==='pending'?'Pendiente':'Sin verificar'):'—'),make('td',date(item.created_at)),link);body.append(tr);
    }
    if(!filtered.length){const tr=make('tr'),td=make('td',rows.length?'No hay coincidencias en esta página.':'Todavía no hay expedientes en esta página.','empty-state');td.colSpan=6;tr.append(td);body.append(tr);}
    el('history-page').textContent=`Página ${offset/25+1} · ${rows.length} expedientes`;controls();
  }
  async function loadHistory(pageOffset=offset){const loaded=await request('/v1/local-scans?limit=25&offset='+pageOffset);rows=loaded;offset=pageOffset;renderHistory();}
  function refreshCounts(){request('/v1/local-scans?limit=25').then(renderDashboard).catch(()=>{el('nav-count').textContent='—';});}
  function renderSourceReview(item) {
    const review=item.source_review,historical=item.revision!==latestRevision;
    el('case-review').hidden=!item.report.signals.length;
    el('case-review-form').hidden=!!review||historical;
    el('case-review-state').textContent=review?'Hash coincidente':'Pendiente';
    el('case-review-state').className='badge '+(review?'teal':'amber');
    el('case-review-explanation').textContent=review?'La comprobación usó bytes con el hash original. No se conservó el código aportado.':'Aporta el archivo original para contrastar su hash, la llamada y el literal shell=True. El código no se ejecuta ni se conserva.';
    el('case-review-hint').textContent=historical&&!review?'Esta revisión todavía no incluye corroboración. Abre la última para aportarla.':review?'SHA-256 coincidente · '+date(review.checked_at)+' · riesgo sin verificar':'';
    const results=el('case-review-results');results.replaceChildren();
    const labels={pattern_reproduced:'Patrón reproducido',not_reproduced:'No reproducido',inconclusive:'Inconcluso'};
    const reasons={literal_shell_true_observed:'La llamada y el literal shell=True están presentes.',location_does_not_match:'La ubicación no corresponde a la llamada reportada.',call_does_not_match:'La llamada no coincide con la señal.',shell_true_not_observed:'No se observó el literal True esperado.',binding_not_established:'No se pudo establecer el vínculo del nombre importado en este alcance.'};
    for(const [index,decision] of (review?.decisions||[]).entries()) {
      const signal=item.report.signals[index],card=make('article',undefined,'signal'),head=make('div',undefined,'signal-head');
      head.append(make('span','SF-PY-001','tag'),make('strong',labels[decision.result]),make('span',`Línea ${signal.line}:${signal.column}`,'muted'));
      card.append(head,make('p',reasons[decision.reason]));results.append(card);
    }
  }
  function renderArgumentTrace(item) {
    const investigation=item.argument_investigation,historical=item.revision!==latestRevision;
    const ready=item.source_review?.decisions.every(decision=>decision.result==='pattern_reproduced');
    el('case-trace').hidden=!item.report.signals.length;
    el('case-trace-form').hidden=!!investigation||historical||!ready;
    el('case-trace-state').textContent=investigation?'Recorrido guardado':historical?'Sin investigación en esta revisión':ready?'Listo para investigar':'Requiere corroboración';
    el('case-trace-state').className='badge '+(investigation?'teal':'amber');
    el('case-trace-hint').textContent=historical&&!investigation?'Esta revisión aún no incluye investigación. Abre la última para continuar.':!ready?'Primero corrobora la fuente y sus señales en el paso anterior.':investigation?'Hash original coincidente · '+date(investigation.checked_at)+' · comprobación independiente por paso':'Vuelve a aportar el archivo original. Solo seguimos asignaciones simples dentro de una función.';
    const container=el('case-trace-results');container.replaceChildren();
    const kinds={literal:'Literal',parameter:'Parámetro',call_result:'Resultado de llamada',assignment:'Asignación',sink:'Llamada con shell=True',unknown:'Origen desconocido'};
    const results={steps_reproduced:'Pasos reproducidos',inconclusive:'Inconcluso',not_reproduced:'No reproducido'};
    const stepResults={reproduced:'Paso reproducido',inconclusive:'Sin resolver',not_reproduced:'No reproducido'};
    const reasons={straight_line_bindings:'Se reprodujo la cadena de asignaciones en la fuente original.',callee_not_followed:'El recorrido termina en el resultado de otra llamada; su implementación no se sigue.',binding_out_of_scope:'El nombre no tiene una asignación local que podamos seguir.',expression_out_of_scope:'La expresión queda fuera del alcance de las asignaciones simples.',control_flow_or_opaque_statement:'Una rama, bucle u otra operación impide resolver el recorrido.',function_out_of_scope:'La llamada queda fuera del alcance de una sola función y sus asignaciones simples.',dynamic_arguments:'Los argumentos dinámicos impiden identificar el comando en este alcance.',trace_limit:'Se alcanzó el límite de pasos o sentencias. El origen queda sin resolver.',argument_missing:'No se encontró un argumento de comando explícito.'};
    for(const [index,trace] of (investigation?.traces||[]).entries()) {
      const {hypothesis,verification}=trace,card=make('article',undefined,'trace-card'),head=make('div',undefined,'trace-heading');
      head.append(make('strong','Señal '+(index+1)),make('span',results[verification.result],'badge '+(verification.result==='steps_reproduced'?'teal':'amber')));
      const chain=make('ol',undefined,'trace-chain');chain.setAttribute('aria-label','Recorrido del argumento, desde su origen hasta la llamada');
      for(const [position,step] of hypothesis.steps.entries()) {
        const node=make('li',undefined,'trace-node '+(verification.step_results[position]==='reproduced'?'reproduced':'unresolved'));
        node.append(make('span',String(position+1).padStart(2,'0'),'trace-number'),make('strong',kinds[step.kind]));
        node.append(make('code',step.symbol||(step.kind==='literal'?'valor omitido':step.kind==='call_result'?'función no seguida':'sin resolver')));
        node.append(make('small',`Línea ${step.line}:${step.column} → ${step.end_line}:${step.end_column}`));
        node.append(make('span',stepResults[verification.step_results[position]],'trace-check'));chain.append(node);
      }
      card.append(head,chain,make('p',verification.result==='not_reproduced'?'El comprobador no reprodujo la propuesta. Conservamos la discrepancia para revisión.':reasons[hypothesis.reason],'trace-reason'));container.append(card);
    }
  }
  function renderCase(item) {
    const changed=!current||current.id!==item.id;current=item;
    if(changed){draft=null;reviewFile=null;reviewDraft=null;el('case-review-file').value='';el('case-review-file-info').textContent='Puede tener otro nombre; los bytes deben coincidir con el archivo analizado. Hasta 64 KiB.';for(const id of ['case-actor','case-role','case-text'])el(id).value='';}
    if(changed){traceFile=null;traceDraft=null;el('case-trace-file').value='';el('case-trace-file-info').textContent='Archivo .py de hasta 64 KiB, con los mismos bytes del análisis.';}
    el('case-title').textContent=item.report.source.relative_path;el('case-id').textContent=item.id;
    const [label,cls]=states[item.status];el('case-status').textContent=label;el('case-status').className='badge '+cls;
    el('case-version').textContent=`Revisión ${item.revision} de ${latestRevision} · ${date(item.created_at)}`;
    el('case-size').textContent=`${item.report.source.size_bytes.toLocaleString('es')} bytes · Python ${item.report.python_version}`;
    el('case-hash').textContent=item.report.source.sha256;el('case-signal-count').textContent=item.report.signals.length+(item.report.signals.length===1?' señal':' señales');
    el('case-errors').hidden=!item.report.errors.length;el('case-errors').textContent=item.report.errors.map(error=>error.code+' · '+error.message).join('\n');
    const signals=el('case-signals');signals.replaceChildren();
    if(!item.report.signals.length)empty(signals,item.status==='ERROR'?'La inspección no se completó.':'Sin coincidencias para esta regla.',item.status==='ERROR'?'Consulta el error técnico antes de volver a intentarlo.':'Este resultado no garantiza que el archivo sea seguro.');
    for(const signal of item.report.signals) {const card=make('article',undefined,'signal'),head=make('div',undefined,'signal-head');head.append(make('span',signal.rule_id,'tag'),make('strong',signal.call),make('span','Sin verificar','badge amber'));card.append(head,make('p',signal.message),make('div',`Línea ${signal.line}:${signal.column} → ${signal.end_line}:${signal.end_column} · warning`,'signal-location'));signals.append(card);}
    el('case-context').hidden=!item.question;el('case-answer-display').replaceChildren();
    if(item.question) {
      el('case-question').textContent=item.question.prompt;el('case-question-state').textContent=item.question.status==='pending'?'Pendiente':'Recibido · sin verificar';el('case-question-state').className='badge '+(item.question.status==='pending'?'amber':'teal');
      const historical=item.revision!==latestRevision;el('case-answer-form').hidden=historical||item.question.status==='answered';
      el('case-answer-hint').textContent=historical?'Revisión histórica. Abre la última revisión para aportar contexto.':item.question.status==='answered'?'El contexto se conserva; las señales siguen sin verificar.':'';
      for(const statement of item.human_statements)el('case-answer-display').append(make('blockquote',statement.text),make('p',`${statement.actor} · ${statement.role} · ${date(statement.created_at)} · unverified`));
      if(draft&&item.question.status==='answered'&&el('case-text').value&&item.human_statements[0]?.id!=='statement-'+draft.id){const saved=make('details');saved.append(make('summary','Borrador local conservado'),make('pre',el('case-text').value));el('case-answer-display').append(saved);}
    }
    renderSourceReview(item);
    renderArgumentTrace(item);
    el('case-json').textContent=JSON.stringify(item,null,2);view('case');controls();
  }
  async function openCase(id,revision) {
    const result=await request('/v1/local-scans/'+encodeURIComponent(id)+(revision?'?revision='+revision:''));
    if(!revision)latestRevision=result.revision;renderCase(result);
  }
  async function route() {
    const [name,id]=location.hash.slice(1).split('/');notice('');
    try {if(name==='case'&&/^scan-[a-f0-9]{64}$/.test(id||'')){await openCase(id);return;}
      const active=Object.hasOwn(names,name)&&name!=='case'?name:'overview';view(active);
      if(active==='overview')renderDashboard(await request('/v1/local-scans?limit=25'));
      if(active==='history')await loadHistory();
    }catch(error){notice(error.message,true);}
  }
  function choose(file) {
    if(!file||!file.name.toLowerCase().endsWith('.py')||file.size>65536){selected=null;el('file-label').textContent='Elige un archivo .py de hasta 64 KiB';el('file-meta').textContent='UTF-8 · hasta 64 KiB · un archivo a la vez';notice('No se seleccionó un archivo válido.',true);}
    else{selected=file;el('file-label').textContent=file.name;el('file-meta').textContent=file.size.toLocaleString('es')+' bytes · listo para analizar';notice('');}controls();
  }
  el('scan-file').onchange=event=>choose(event.target.files[0]);
  el('drop-zone').ondragover=event=>{event.preventDefault();el('drop-zone').classList.add('dragging');};
  el('drop-zone').ondragleave=()=>el('drop-zone').classList.remove('dragging');
  el('drop-zone').ondrop=event=>{event.preventDefault();el('drop-zone').classList.remove('dragging');if(!busy)choose(event.dataTransfer.files.length===1?event.dataTransfer.files[0]:null);};
  async function submitFile(file) {
    const result=await request('/v1/local-scans?filename='+encodeURIComponent(file.name),{method:'POST',headers:{'Content-Type':'application/octet-stream'},body:file});
    latestRevision=result.revision;history.replaceState(null,'','#case/'+result.id);renderCase(result);refreshCounts();
  }
  el('scan-form').onsubmit=event=>{event.preventDefault();if(selected)action(()=>submitFile(selected));};
  for(const [id,enabled] of [['example-positive',true],['example-negative',false]])el(id).onclick=()=>action(()=>submitFile(new File([`# Ejemplo controlado; se analiza sin ejecutar.\nimport subprocess\nsubprocess.run('demo', shell=${enabled?'True':'False'}, check=False)\n`],enabled?'example_shell_enabled.py':'example_shell_disabled.py')));
  el('history-search').oninput=renderHistory;el('refresh-history').onclick=()=>action(loadHistory);
  el('history-previous').onclick=()=>action(()=>loadHistory(Math.max(0,offset-25)));
  el('history-next').onclick=()=>action(()=>loadHistory(offset+25));
  el('case-previous').onclick=()=>action(()=>openCase(current.id,current.revision-1));el('case-next').onclick=()=>action(()=>openCase(current.id,current.revision+1));el('case-latest').onclick=()=>action(()=>openCase(current.id));
  el('case-answer-form').onsubmit=event=>{event.preventDefault();if(!current||current.revision!==latestRevision||current.question?.status!=='pending')return;
    const body={actor:el('case-actor').value,role:el('case-role').value,text:el('case-text').value};if(Object.values(body).some(value=>!value.trim())){notice('Completa autor, rol y contexto con texto visible.',true);return;}
    const fingerprint=JSON.stringify({id:current.id,...body});if(!draft||draft.fingerprint!==fingerprint)draft={id:crypto.randomUUID(),fingerprint};
    const id=current.id;action(async()=>{await request('/v1/local-scans/'+encodeURIComponent(id)+'/answers',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...body,submission_id:draft.id})});await openCase(id);draft=null;for(const key of ['case-actor','case-role','case-text'])el(key).value='';refreshCounts();});
  };
  el('case-review-file').onchange=event=>{
    const file=event.target.files[0];reviewDraft=null;
    reviewFile=file&&file.name.toLowerCase().endsWith('.py')&&file.size<=65536?file:null;
    el('case-review-file-info').textContent=reviewFile?`${file.name} · ${file.size} bytes · listo para contrastar`:'Selecciona un .py de hasta 64 KiB.';controls();
  };
  el('case-review-form').onsubmit=event=>{
    event.preventDefault();if(!current||!reviewFile||current.source_review||current.revision!==latestRevision)return;
    if(!reviewDraft)reviewDraft={id:crypto.randomUUID()};
    const id=current.id,file=reviewFile,key=reviewDraft.id;
    action(async()=>{await request('/v1/local-scans/'+encodeURIComponent(id)+'/verify?submission_id='+encodeURIComponent(key),{method:'POST',headers:{'Content-Type':'application/octet-stream'},body:file});await openCase(id);reviewFile=null;reviewDraft=null;el('case-review-file').value='';});
  };
  el('case-trace-file').onchange=event=>{
    const file=event.target.files[0];traceDraft=null;
    traceFile=file&&file.name.toLowerCase().endsWith('.py')&&file.size<=65536?file:null;
    el('case-trace-file-info').textContent=traceFile?`${file.name} · ${file.size} bytes · listo para investigar`:'Selecciona un .py de hasta 64 KiB.';controls();
  };
  el('case-trace-form').onsubmit=event=>{
    event.preventDefault();if(!current||!traceFile||current.argument_investigation||current.revision!==latestRevision||!current.source_review?.decisions.every(item=>item.result==='pattern_reproduced'))return;
    if(!traceDraft)traceDraft={id:crypto.randomUUID()};
    const id=current.id,file=traceFile,key=traceDraft.id;
    action(async()=>{await request('/v1/local-scans/'+encodeURIComponent(id)+'/trace?submission_id='+encodeURIComponent(key),{method:'POST',headers:{'Content-Type':'application/octet-stream'},body:file});await openCase(id);traceFile=null;traceDraft=null;el('case-trace-file').value='';});
  };
  el('download-case').onclick=()=>{if(!current)return;const url=URL.createObjectURL(new Blob([JSON.stringify(current,null,2)],{type:'application/json'})),link=make('a');link.href=url;link.download=`sentinelforge-${short(current.id)}-r${current.revision}.json`;link.click();URL.revokeObjectURL(url);};
  window.addEventListener('hashchange',route);
  request('/health').then(()=>{el('connection').textContent='Conectado · local';}).catch(()=>{el('connection').textContent='Sin conexión';});
  controls();route();
})();
