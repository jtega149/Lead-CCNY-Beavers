/* Entry point: scenarios, request inspector, /judge + /decision calls, feed, story mode. Loaded last. */

let scenarios = [];
let activeIdx = 0;

async function health() {
  try {
    await api('/health');
    $('#hdot').className = 'dot up';
    $('#htxt').textContent = 'server connected';
  } catch {
    $('#hdot').className = 'dot down';
    $('#htxt').textContent = 'server offline';
  }
}

async function loadScenarios() {
  try {
    scenarios = await api('/demo/scenarios');
  } catch {
    $('#tabs').innerHTML = '<div class="offline">Server offline. Start it with <code>uvicorn app:app</code>, then reload.</div>';
    msg('sys', 'Cannot reach the Judgment Layer server.');
    return;
  }
  $('#tabs').innerHTML = scenarios.map((s, i) =>
    `<button data-i="${i}">${esc(s.label)}<small>${esc(s.expect)}</small></button>`).join('');
  $$('#tabs button').forEach(b => b.onclick = () => {
    if (!S.playing && !S.busy) pickScenario(+b.dataset.i);
  });
  pickScenario(0);
}

function pickScenario(i) {
  activeIdx = i;
  $$('#tabs button').forEach((b, j) => b.classList.toggle('on', j === i));
  const sc = scenarios[i], {purchase: p, mandate: m, history, delivered} = sc.payload;

  $('#m_task').value = m.task;
  $('#m_max').value = m.max_amount;
  $('#m_owner').value = m.owner_id;
  $('#m_cats').value = m.allowed_categories.join(', ');
  $('#m_trusted').value = (m.trusted_instruction_sources || []).join(', ');
  $('#p_seller_name').value = p.seller_name;
  $('#p_seller_id').value = p.seller_id;
  $('#p_amount').value = p.amount;
  $('#p_category').value = p.category;
  $('#p_source').value = p.instruction_source;
  $('#p_agent').value = p.agent_id;
  $('#p_itext').value = p.instruction_text;
  $('#p_just').value = p.justification;
  $('#h_json').value = JSON.stringify(history || [], null, 1);
  $('#delivered').checked = delivered !== false;
  $('#inspectorErr').textContent = '';

  resetChat(sc.payload);
  log('SYSTEM', `Loaded scenario: ${sc.label}`);
}

/** The payload sent to /judge: the active scenario as edited in the inspector. */
function readInspectorForm() {
  let history;
  try {
    history = JSON.parse($('#h_json').value || '[]');
    if (!Array.isArray(history)) throw 0;
  } catch {
    throw new Error('History must be a JSON array of {seller_id, amount, timestamp}.');
  }
  const base = scenarios[activeIdx].payload;
  return {
    mandate: {
      ...base.mandate,
      owner_id: $('#m_owner').value,
      task: $('#m_task').value,
      max_amount: +$('#m_max').value,
      allowed_categories: list($('#m_cats').value),
      trusted_instruction_sources: list($('#m_trusted').value),
    },
    purchase: {
      ...base.purchase,
      request_id: `${base.purchase.request_id}-${++S.seq}`,
      agent_id: $('#p_agent').value,
      seller_id: $('#p_seller_id').value,
      seller_name: $('#p_seller_name').value,
      amount: +$('#p_amount').value,
      category: $('#p_category').value,
      instruction_source: $('#p_source').value,
      instruction_text: $('#p_itext').value,
      justification: $('#p_just').value,
    },
    history,
    delivered: $('#delivered').checked,
  };
}

async function handleUserPrompt(text) {
  if (S.busy || !scenarios.length) return;
  let payload;
  try {
    payload = readInspectorForm();
  } catch (err) {
    msg('sys', esc(err.message));
    return;
  }
  S.busy = true;
  showView('chat');
  msg('u', esc(text));
  $('#inp').value = '';
  await typing();
  await narrate(payload);
  S.busy = false;
  await executePipeline(payload);
}

async function executePipeline(payload) {
  if (S.busy) return;
  S.busy = true;
  $('#play').disabled = true;
  resetPanel();
  const p = payload.purchase;
  log('GATEWAY', `POST /judge ${p.request_id} · ${money(p.amount)} to ${p.seller_name} from ${p.agent_id}`);

  try {
    const res = await api('/judge', payload);
    await animatePipeline(res);
    renderDecision(payload, res);
    const run = {payload, result: res, wasHeld: res.route === 'hold'};
    S.runs.unshift(run);
    showOutcome(run);
    renderFeed(0);
  } catch (err) {
    log('GATEWAY', `/judge failed: ${err.message}`, 'bad');
    msg('sys', `Judgment Layer error: ${esc(err.message)}`);
  } finally {
    S.busy = false;
    $('#play').disabled = false;
  }
}

/** Owner approves (after Face ID) or rejects a held payment via POST /judge/{id}/decision. */
async function resolveHold(run, approve) {
  if (S.busy || run.result.route !== 'hold') return;
  S.busy = true;
  try {
    if (approve) await triggerBiometricAuth();
    const id = run.payload.purchase.request_id;
    log('GATEWAY', `POST /judge/${id}/decision · approve=${approve}`, approve ? 'ok' : 'warn');
    run.result = await api(`/judge/${encodeURIComponent(id)}/decision`, {approve});
    setRouteNode(run.result);
    renderDecision(run.payload, run.result);
    showView('chat');
    showOutcome(run);
    renderFeed(S.runs.indexOf(run));
  } catch (err) {
    log('GATEWAY', `decision failed: ${err.message}`, 'bad');
    msg('sys', `Could not record your decision: ${esc(err.message)}`);
  } finally {
    S.busy = false;
  }
}

function renderFeed(selected = -1) {
  const runs = S.runs, by = k => runs.filter(r => r.result.route === k);
  const stopped = [...by('block'), ...by('hold')].reduce((a, r) => a + r.payload.purchase.amount, 0);

  $('#metrics').innerHTML = [
    [runs.length, 'payments judged'],
    [by('auto_approve').length, 'auto-approved'],
    [runs.filter(r => r.wasHeld).length, 'sent to a human'],
    [by('block').length, 'blocked'],
    [money(stopped), 'kept from moving'],
    [runs.filter(r => r.result.receipt.liable_party === 'seller').length, 'seller liable'],
  ].map(([v, l]) => `<div class="metric"><b>${v}</b><span>${l}</span></div>`).join('');

  $('#feed').innerHTML = runs.length ? runs.map((r, i) => {
    const p = r.payload.purchase, res = r.result, top = topRisk(res);
    const tone = (ROUTE_CONFIG[res.route] || {tone: 'nt'}).tone;
    return `
      <tr data-i="${i}" class="${i === selected ? 'sel' : ''}">
        <td style="font-family:var(--mono);font-size:11.5px">${esc(p.request_id)}</td>
        <td><b>${esc(p.seller_name)}</b></td>
        <td>${money(p.amount)}</td>
        <td>${esc(p.instruction_source)}</td>
        <td>${r.result.agent_pay.permitted ? 'would pay' : 'declined'}</td>
        <td><span class="bd ${tone}">${esc(routeLabel(res.route))}</span></td>
        <td style="font-weight:700;color:${top >= 70 ? 'var(--bad)' : top >= 40 ? 'var(--warn)' : 'var(--ok)'}">${top}</td>
        <td>${esc(res.settlement ? res.settlement.status.replace('_', ' ') : '—')}</td>
        <td style="color:${res.receipt.liable_party === 'none' ? 'var(--mu)' : 'var(--org)'}">${esc(PARTY_MAP[res.receipt.liable_party] || res.receipt.liable_party)}</td>
      </tr>`;
  }).join('') : '<tr><td colspan="9" class="empty-tr">No transactions yet. Run a scenario to inspect.</td></tr>';

  $$('#feed tr[data-i]').forEach(tr => tr.onclick = () => {
    const i = +tr.dataset.i;
    $$('#feed tr').forEach((x, j) => x.classList.toggle('sel', j === i));
    renderDecision(S.runs[i].payload, S.runs[i].result);
  });
}

async function typeInto(el, txt) {
  el.value = '';
  for (const c of txt) {
    el.value += c;
    await sleep(24);
  }
  await sleep(250);
}

/** Plays the active scenario end to end; a held payment is approved after a pause. */
async function playStory() {
  if (S.playing || S.busy || !scenarios.length) return;
  S.playing = true;
  $('#play').disabled = true;
  try {
    const text = ownerRequest(scenarios[activeIdx].payload);
    showView('chat');
    await typeInto($('#inp'), text);
    await handleUserPrompt(text);
    const run = S.runs[0];
    if (run && run.result.route === 'hold') {
      await sleep(1400);
      $('#msgs .acts [data-act="approve"]')?.click();
    }
  } finally {
    S.playing = false;
    $('#play').disabled = false;
  }
}

function resetAll() {
  if (S.busy) return;
  closeSheet();
  S = {runs: [], disputes: [], busy: false, playing: false, seq: 100};
  resetPanel();
  renderAct();
  renderDis();
  renderFeed();
  if (scenarios.length) pickScenario(activeIdx);
}

// ── Wiring ──
$$('#modeToggle button').forEach(b => b.onclick = () => {
  $$('#modeToggle button').forEach(x => x.classList.toggle('on', x === b));
  const inspector = b.dataset.m === 'inspector';
  $('#phoneContainer').style.display = inspector ? 'none' : 'flex';
  $('#inspectorCard').classList.toggle('on', inspector);
});

$('#runInspector').onclick = () => {
  try {
    $('#inspectorErr').textContent = '';
    executePipeline(readInspectorForm());
  } catch (err) {
    $('#inspectorErr').textContent = err.message;
  }
};

$$('#phoneTabs button').forEach(b => b.onclick = () => {
  closeSheet();
  showView(b.dataset.v);
});

$('#cmp').onsubmit = ev => {
  ev.preventDefault();
  const v = $('#inp').value.trim();
  if (v) handleUserPrompt(v);
};

$('#play').onclick = playStory;
$('#reset').onclick = resetAll;

resetPanel();
renderAct();
renderDis();
renderFeed();
health();
loadScenarios();
