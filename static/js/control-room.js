/* Right-hand control room: pipeline, Agent Pay comparison, verdict, checks, receipt, liability. */

const STAGES = [
  ['Agent Pay check', '<rect x="3" y="6" width="18" height="12" rx="2"/><path d="M3 10h18"/>'],
  ['Provenance', '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>'],
  ['Mandate verifier', '<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="3.500"/>'],
  ['Risk & patterns', '<path d="M3 12h4l3-7 4 14 3-7h4"/>'],
  ['Sense check · Azure', '<path d="M12 3a6 6 0 00-4 10.500V16h8v-2.500A6 6 0 0012 3zM9 20h6"/>'],
  ['Route + receipt', '<rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V8a4 4 0 018 0v3"/>'],
];
const CHECK_KEYS = {provenance: 'prov', verifier: 'ver', risk_signals: 'risk', sense_check: 'sense'};
const CHECK_LOG = {provenance: 'PROVENANCE', verifier: 'VERIFIER', risk_signals: 'RISK', sense_check: 'AZURE OPENAI'};
const ROUTE_NODE = STAGES.length - 1;

function buildPipe() {
  $('#pipe').innerHTML = STAGES.map((s, i) =>
    `<div class="nd" id="n${i}"><div class="ci"><svg viewBox="0 0 24 24">${s[1]}</svg></div><b>${s[0]}</b><small>Waiting</small></div>`
  ).join('');
}

function setNode(i, st, txt) {
  const n = $('#n' + i);
  if (!n) return;
  n.className = 'nd ' + st;
  n.querySelector('small').textContent = txt;
}

function resetPanel() {
  buildPipe();
  $('#garc').style.stroke = '#35d07f';
  $('#garc').style.strokeDashoffset = '157.1';
  $('#gnum').textContent = '–';
  $('#vd').className = 'verdict';
  $('#vd').textContent = 'Waiting for an agent transaction…';
  ['kroute', 'kliable', 'ksettle'].forEach(id => $('#' + id).textContent = '–');
  $('#rsn').innerHTML = '<li>Signals appear here as soon as a purchase is scored.</li>';
  Object.values(CHECK_KEYS).forEach(k => {
    $('#badge-' + k).className = 'bd nt';
    $('#badge-' + k).textContent = '–';
    $('#bar-' + k).style.width = '0%';
    $('#risk-' + k).textContent = 'risk: –';
    $('#reasons-' + k).innerHTML = '<li>Waiting…</li>';
  });
  $('#lane-ap').className = 'lane';
  $('#lane-jl').className = 'lane';
  $('#ap-verdict').textContent = $('#jl-verdict').textContent = '–';
  $('#ap-why').textContent = 'credential · spending limit · category';
  $('#jl-why').textContent = 'provenance · verifier · seller & pattern risk';
  $('#vs-note').innerHTML = '';
  $('#led').innerHTML = 'No receipt yet.';
  $('#receiptPre').textContent = 'No receipt generated yet.';
  routeClear();
}

function routeClear() {
  Object.keys(PARTY_MAP).filter(k => k !== 'none').forEach(k => {
    $('#p-' + k)?.setAttribute('class', 'pill');
    $('#l-' + k)?.setAttribute('class', '');
  });
  $('#rtx').innerHTML = 'Run a scenario or file a dispute to see who bears the loss.';
}

function showRoute(party, why = '') {
  routeClear();
  if (party === 'none') {
    $('#rtx').innerHTML = `<b>No one is liable.</b> ${esc(why)}`;
    return;
  }
  $('#p-' + party)?.setAttribute('class', 'pill pri');
  $('#l-' + party)?.setAttribute('class', 'pri');
  $('#rtx').innerHTML = `Liable party: <b>${esc(PARTY_MAP[party] || party)}</b><br>${esc(why)}`;
}

async function countTo(el, target) {
  const start = performance.now();
  for (let p = 0; p < 1; await sleep(16)) {
    p = Math.min(1, (performance.now() - start) / 800);
    el.textContent = Math.round(target * (1 - Math.pow(1 - p, 3)));
  }
}

/** Steps through the pipeline nodes using the real /judge result. */
async function animatePipeline(res) {
  const ap = res.agent_pay;
  setNode(0, 'run', 'Screening…');
  await sleep(400);
  setNode(0, ap.permitted ? 'ok' : 'bad', ap.permitted ? 'Would approve' : 'Declined');
  log('AP4M', ap.reason, ap.permitted ? 'ok' : 'bad');

  for (const [i, name] of [[1, 'provenance'], [2, 'verifier'], [3, 'risk_signals'], [4, 'sense_check']]) {
    const c = res.checks.find(x => x.check_name === name);
    if (!c) continue;
    setNode(i, 'run', 'Checking…');
    await sleep(450);
    setNode(i, toneOf(c.status), `${c.status} · ${c.risk}/100`);
    log(CHECK_LOG[name], `${c.status.toUpperCase()}: ${c.reasons[0] || 'checked'}`, toneOf(c.status));
  }

  setNode(ROUTE_NODE, 'run', 'Routing…');
  await sleep(400);
  setRouteNode(res);
}

function setRouteNode(res) {
  const cfg = ROUTE_CONFIG[res.route] || {tone: 'warn'};
  setNode(ROUTE_NODE, cfg.tone, routeLabel(res.route));
  log('RECEIPTS', `${res.route} · liable=${res.receipt.liable_party} · sig ${res.receipt.signature.slice(0, 12)}…`, cfg.tone);
}

function renderVersus(payload, res) {
  const ap = res.agent_pay, cfg = ROUTE_CONFIG[res.route] || {tone: 'warn'};
  $('#ap-verdict').textContent = ap.permitted ? `✓ Would pay ${money(payload.purchase.amount)}` : '✗ Declined';
  $('#ap-why').textContent = ap.reason;
  $('#lane-jl').className = 'lane ' + cfg.tone;
  $('#jl-verdict').textContent = routeLabel(res.route);
  $('#jl-why').textContent = ['block', 'hold'].includes(res.route) ? worstReason(res) : res.receipt.liability_reason;

  let note = '';
  if (ap.permitted && res.route === 'block') note = '<b>Caught.</b> Every Agent Pay rule was satisfied. Only the Judgment Layer stopped this payment.';
  else if (ap.permitted && res.route === 'hold') note = '<b>Escalated.</b> Agent Pay would have paid instantly. The layer asked the owner first.';
  else if (res.route === 'human_approve') note = 'The owner overrode the hold, so the receipt makes the owner liable.';
  $('#vs-note').innerHTML = note;
}

function renderDecision(payload, res) {
  const cfg = ROUTE_CONFIG[res.route] || {tone: 'warn', color: '#ffb020'};
  const top = topRisk(res), rc = res.receipt;

  $('#garc').style.stroke = cfg.color;
  $('#garc').style.strokeDashoffset = (157.1 * (1 - top / 100)).toFixed(1);
  countTo($('#gnum'), top);

  $('#vd').className = 'verdict ' + cfg.tone;
  $('#vd').textContent = `${routeLabel(res.route)} · ${money(payload.purchase.amount)} to ${payload.purchase.seller_name}`;
  $('#kroute').textContent = res.route.replace('_', ' ');
  $('#kliable').textContent = PARTY_MAP[rc.liable_party] || rc.liable_party;
  $('#ksettle').textContent = res.settlement ? res.settlement.status.replace('_', ' ') : 'none';
  $('#rsn').innerHTML = res.checks.flatMap(c => c.reasons).map(r => `<li>${esc(r)}</li>`).join('');

  res.checks.forEach(c => {
    const k = CHECK_KEYS[c.check_name];
    if (!k) return;
    $('#badge-' + k).className = 'bd ' + toneOf(c.status);
    $('#badge-' + k).textContent = c.status.toUpperCase();
    $('#bar-' + k).style.width = Math.min(100, c.risk) + '%';
    $('#risk-' + k).textContent = `risk: ${c.risk} / 100`;
    $('#reasons-' + k).innerHTML = c.reasons.map(r => `<li>${esc(r)}</li>`).join('');
  });

  renderVersus(payload, res);

  $('#led').innerHTML = `
    <span class="lock">🔒 sealed</span> · request <b>${esc(rc.request_id)}</b><br>
    HMAC-SHA256 <b>${esc(rc.signature.slice(0, 24))}…</b><br>
    mandate <b>"${esc(payload.mandate.task)}"</b> · max <b>${money(payload.mandate.max_amount)}</b><br>
    route <b>${esc(res.route)}</b> · liable <b style="color:${rc.liable_party === 'none' ? 'var(--ok)' : 'var(--org)'}">${esc(PARTY_MAP[rc.liable_party] || rc.liable_party)}</b><br>
    reason: <span>${esc(rc.liability_reason)}</span>`;
  $('#receiptPre').textContent = JSON.stringify(rc, null, 2);

  showRoute(rc.liable_party, rc.liability_reason);
}
