/* Customer phone: chat, hold approve/reject, Face ID step-up, activity and disputes. */

const REASONS = {
  unauthorized: 'I never approved this',
  agent_exceeded_mandate: 'Agent went beyond my limits',
  not_received: 'Paid but never received',
  not_as_described: 'Not as described',
  duplicate: 'Duplicate charge',
  other: 'Other',
};

const ACT_BADGE = {
  auto_approve: '<span class="bd ok">Paid · verified</span>',
  human_approve: '<span class="bd ok">Approved by you</span>',
  hold: '<span class="bd warn">Needs your OK</span>',
  block: '<span class="bd bad">Blocked</span>',
};

function msg(k, html) {
  const d = document.createElement('div');
  d.className = 'm ' + k;
  d.innerHTML = html;
  $('#msgs').appendChild(d);
  $('#msgs').scrollTop = 1e6;
  return d;
}

async function typing(ms = 600) {
  const d = msg('a', '<span class="dots"><i></i><i></i><i></i></span>');
  await sleep(ms);
  d.remove();
}

function showView(v) {
  $$('.view').forEach(x => x.classList.toggle('on', x.id === 'v-' + v));
  $$('#phoneTabs button').forEach(b => b.classList.toggle('on', b.dataset.v === v));
}

function sheet(html) {
  $('#sheet').innerHTML = '<div class="grip"></div>' + html;
  $('#sheet').classList.add('on');
}

const closeSheet = () => $('#sheet').classList.remove('on');

/** What the owner would type to kick off this scenario. */
function ownerRequest(payload) {
  const {purchase: p, mandate: m} = payload;
  if (p.instruction_source === 'owner') return p.instruction_text;
  return m.task.charAt(0).toUpperCase() + m.task.slice(1);
}

function resetChat(payload) {
  const m = payload.mandate;
  $('#msgs').innerHTML = '';
  $('#ph-mandate').innerHTML = `Mandate: <b>${esc(m.allowed_categories.join(', '))}</b> · up to <b>${money(m.max_amount)}</b> · <b>pays without asking</b>`;
  msg('a', `Hi ${esc(m.owner_id)}! I pay for things on my own, up to ${money(m.max_amount)}. I only check with you if something looks off.`);
  renderChips([ownerRequest(payload)]);
}

function renderChips(items) {
  $('#chips').innerHTML = items.map(c => `<button data-q="${esc(c)}">${esc(c)}</button>`).join('');
  $$('#chips button').forEach(b => b.onclick = () => handleUserPrompt(b.dataset.q));
}

/** Chat lead-up before the payment hits the Judgment Layer: what the agent read and decided. */
async function narrate(payload) {
  const {purchase: p, mandate: m, history} = payload;

  if (p.instruction_source !== 'owner') {
    msg('sys', `Agent is reading a ${esc(p.instruction_source)}…`);
    await sleep(500);
    msg('a wide', `<div class="inj"><small>Content the agent read · ${esc(p.instruction_source)}</small>“${esc(p.instruction_text)}”</div>`);
    await sleep(600);
  }

  const prior = (history || []).filter(h => h.seller_id === p.seller_id);
  if (prior.length) {
    msg('sys', `Agent already paid ${esc(p.seller_name)} ${prior.length}× recently (${prior.map(h => money(h.amount)).join(', ')})`);
    await sleep(500);
  }

  const within = p.amount <= m.max_amount;
  msg('a wide', `
    <div class="tkt">
      <div class="tk-h"><div><small>Agent is paying</small><b>${esc(p.seller_name)}</b></div><span class="tag">Sent to Agent Pay</span></div>
      <div style="height:6px"></div>
      <div class="li"><span>Category</span><span>${esc(p.category)}</span></div>
      <div class="li"><span>Instruction from</span><span>${esc(p.instruction_source)}</span></div>
      <div class="li t"><span>Total</span><span>${money(p.amount)}</span></div>
      <div class="${within ? 'okp' : 'warnp'}">${within ? '✓ Within your ' + money(m.max_amount) + ' limit' : '⚠ Over your ' + money(m.max_amount) + ' limit'}</div>
      <div class="cn">Agent's reason: “${esc(p.justification)}”</div>
    </div>`);
  await sleep(400);
}

async function triggerBiometricAuth() {
  sheet(`
    <h4>Confirm it's you</h4>
    <p>Approving a held payment needs step-up verification.</p>
    <button class="bio" id="bioBtn">
      <svg viewBox="0 0 24 24"><path d="M12 11v3m0-8a5 5 0 00-5 5v3m10-3a5 5 0 00-7-4.500M5 15c0 3 1 5 3 7m8-1c1-2 2-4 2-6v-2m-6 4c0 2-.5 3.500-1.500 5"/></svg>
    </button>
    <p style="text-align:center">Tap to verify with Face ID</p>`);
  return new Promise(res => {
    const scan = async () => {
      const b = $('#bioBtn');
      b.onclick = null;
      b.classList.add('scan');
      await sleep(900);
      b.classList.replace('scan', 'done');
      await sleep(400);
      closeSheet();
      res();
    };
    $('#bioBtn').onclick = scan;
    if (S.playing) setTimeout(scan, 700);
  });
}

/** Phone message for a /judge or /decision result. Holds get Approve / Reject buttons. */
function showOutcome(run) {
  const {payload, result: res} = run, p = payload.purchase;

  if (res.route === 'auto_approve' || res.route === 'human_approve') {
    const st = res.settlement;
    msg('a wide', `
      <div class="rcpt">
        <div class="ok"><i>✓</i>${res.route === 'human_approve' ? 'Approved by you' : 'Paid'} · ${money(p.amount)}</div>
        <div style="font-size:12.5px;color:var(--pmu);margin-top:4px">${esc(p.seller_name)} · ${esc(st ? st.note : '')}</div>
        <div class="seal">🔒 Decision receipt sealed · HMAC ${esc(res.receipt.signature.slice(0, 16))}…</div>
      </div>`);
    if (!payload.delivered) {
      msg('a', `⚠️ <b>${esc(p.seller_name)} never delivered.</b> The receipt names the <b>seller</b> liable, so the refund comes from them.`);
    } else if (res.route === 'human_approve') {
      msg('a', 'You overrode the hold, so the receipt records <b>you</b> as responsible if this goes wrong.');
    }
  } else if (res.route === 'block') {
    msg('a wide', `
      <div class="warnbox">
        <b>${run.wasHeld ? 'Rejected. No money moved.' : 'I stopped this payment'}</b>
        <span style="font-size:12.5px;color:var(--pmu)">${run.wasHeld ? 'You rejected the held payment.' : esc(worstReason(res)) + ' No money moved.'}</span>
      </div>`);
  } else if (res.route === 'hold') {
    const flagged = res.checks.filter(c => c.status !== 'pass').flatMap(c => c.reasons);
    const el = msg('a wide', `
      <div class="warnbox hold">
        <b>Needs your OK · ${money(p.amount)} to ${esc(p.seller_name)}</b>
        <span style="font-size:12.5px;color:var(--pmu)">Something looked off, so I haven't paid yet.</span>
        <ul>${flagged.map(r => `<li>${esc(r)}</li>`).join('')}</ul>
      </div>
      <div class="acts"><button class="p" data-act="approve">Approve</button><button data-act="reject">Reject</button></div>`);
    el.querySelectorAll('[data-act]').forEach(b => b.onclick = () => {
      el.querySelector('.acts').remove();
      resolveHold(run, b.dataset.act === 'approve');
    });
  }
  renderAct();
}

function renderAct() {
  const seeds = [
    {mname: 'Kroger Store #412', amount: 54.20, date: '2 days ago'},
    {mname: 'Chipotle Mexican Grill', amount: 18.40, date: '4 days ago'},
    {mname: 'Shell Oil', amount: 41.00, date: 'last week'},
  ];
  const rows = S.runs.map(run => {
    const p = run.payload.purchase, id = p.request_id, route = run.result.route;
    const disputed = S.disputes.some(d => d.run === run);
    const action = disputed ? '' : route === 'hold'
      ? `<button class="lk" data-review="${esc(id)}">Review</button>`
      : ['auto_approve', 'human_approve'].includes(route) ? `<button class="lk" data-dispute="${esc(id)}">Dispute</button>` : '';
    return `<div class="row"><div class="ic">${esc(p.seller_name[0] || '·')}</div>
      <div class="mid"><b>${esc(p.seller_name)}</b><span>Just now</span><br>${disputed ? '<span class="bd nt">Dispute filed</span>' : ACT_BADGE[route] || ''}</div>
      <div class="amt">${money(p.amount)}<br>${action}</div></div>`;
  });
  const seedRows = seeds.map(t => `<div class="row"><div class="ic">${esc(t.mname[0])}</div>
      <div class="mid"><b>${esc(t.mname)}</b><span>${t.date}</span><br><span class="bd ok">Paid · verified</span></div>
      <div class="amt">${money(t.amount)}</div></div>`);
  $('#actList').innerHTML = [...rows, ...seedRows].join('');

  const runById = id => S.runs.find(r => r.payload.purchase.request_id === id);
  $$('#actList [data-dispute]').forEach(b => b.onclick = () => openDispute(runById(b.dataset.dispute)));
  $$('#actList [data-review]').forEach(b => b.onclick = () => openReview(runById(b.dataset.review)));
}

function openReview(run) {
  const p = run.payload.purchase;
  const flagged = run.result.checks.filter(c => c.status !== 'pass').flatMap(c => c.reasons);
  sheet(`
    <h4>Review held payment</h4>
    <p>${esc(p.seller_name)} · ${money(p.amount)}</p>
    <p>${flagged.map(esc).join('<br>')}</p>
    <button class="big" id="revApprove">Approve</button>
    <button class="lk" style="width:100%;margin-top:6px;text-align:center" id="revReject">Reject</button>`);
  $('#revApprove').onclick = () => { closeSheet(); resolveHold(run, true); };
  $('#revReject').onclick = () => { closeSheet(); resolveHold(run, false); };
}

let DR = null;
function openDispute(run) {
  showView('act');
  DR = {run, reason: 'unauthorized'};
  const p = run.payload.purchase;
  sheet(`
    <h4>Dispute this purchase</h4>
    <p>${esc(p.seller_name)} · ${money(p.amount)}</p>
    <div class="rs" id="rsButtons">
      ${Object.entries(REASONS).map(([k, v]) => `<button data-r="${k}" class="${k === 'unauthorized' ? 'on' : ''}">${v}</button>`).join('')}
    </div>
    <textarea id="disputeNotes" placeholder="Tell us what happened…"></textarea>
    <button class="big" id="submitDisputeBtn">Submit dispute</button>
    <button class="lk" style="width:100%;margin-top:6px;color:var(--pmu);text-align:center" id="cancelDisputeBtn">Not now</button>`);
  $$('#rsButtons button').forEach(b => b.onclick = () => {
    DR.reason = b.dataset.r;
    $$('#rsButtons button').forEach(x => x.classList.toggle('on', x === b));
  });
  $('#submitDisputeBtn').onclick = submitDispute;
  $('#cancelDisputeBtn').onclick = closeSheet;
}

/**
 * Routes a dispute using the signed receipt as evidence. Merchant-performance
 * reasons go to the seller and mandate overreach to the agent developer;
 * anything else goes to whoever the receipt already names, defaulting to the
 * owner (the receipt shows the owner's mandate authorized the payment).
 * Note: this routing runs in the browser; there is no dispute endpoint yet.
 */
function disputeParty(reason, receipt) {
  if (reason === 'not_received' || reason === 'not_as_described') return 'seller';
  if (reason === 'agent_exceeded_mandate') return 'agent_developer';
  return receipt.liable_party !== 'none' ? receipt.liable_party : 'owner';
}

function submitDispute() {
  const {run, reason} = DR, rc = run.result.receipt;
  const party = disputeParty(reason, rc);
  const caseId = 'CASE-' + (1001 + S.disputes.length);
  const why = `Routed with signed receipt ${rc.signature.slice(0, 10)}… as evidence (${REASONS[reason]}).`;
  S.disputes.unshift({id: caseId, run, reason, party});

  log('DISPUTES', `${caseId} · reason=${reason} → ${party}`, 'warn');
  showRoute(party, why);
  renderAct();
  renderDis();
  sheet(`
    <h4>Dispute filed</h4>
    <p>Case <b>${caseId}</b> was routed to <b>${esc(PARTY_MAP[party] || party)}</b>.</p>
    <p>The signed decision receipt was attached as evidence.</p>
    <button class="big" id="disputeDoneBtn">Done</button>`);
  $('#disputeDoneBtn').onclick = () => { closeSheet(); showView('dis'); };
}

function renderDis() {
  $('#disList').innerHTML = S.disputes.length ? S.disputes.map(d => `
    <div class="row"><div class="ic">⚖</div>
      <div class="mid"><b>${d.id} · ${esc(d.run.payload.purchase.seller_name)}</b><span>${REASONS[d.reason]}</span><br>
        <span class="bd nt">With: ${esc(PARTY_MAP[d.party] || d.party)}</span></div>
      <div class="amt">${money(d.run.payload.purchase.amount)}</div></div>`).join('')
    : '<div style="color:var(--pmu);padding:14px;font-size:13px">No disputes filed yet.</div>';
}
