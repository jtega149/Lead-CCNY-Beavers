/* Shared helpers, display constants and session state. Loaded first. */

const API = location.protocol.startsWith('http') ? '' : 'http://127.0.0.1:8000';

const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];
const sleep = ms => new Promise(r => setTimeout(r, ms));
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
const money = n => '$' + Number(n || 0).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2});
const list = s => s.split(',').map(x => x.trim()).filter(Boolean);
const ts = () => new Date().toLocaleTimeString('en-US', {hour12: false});

const ROUTE_CONFIG = {
  auto_approve: {tone: 'ok', label: 'Auto-approved', color: '#35d07f'},
  human_approve: {tone: 'ok', label: 'Approved by owner', color: '#35d07f'},
  hold: {tone: 'warn', label: 'Held for a human', color: '#ffb020'},
  block: {tone: 'bad', label: 'Blocked', color: '#ff4d4f'},
};

const PARTY_MAP = {
  none: 'No one',
  seller: 'Seller',
  owner: 'Owner',
  verifier: 'Verifier provider',
  agent_developer: 'Agent developer',
};

const toneOf = status => status === 'block' ? 'bad' : status === 'flag' ? 'warn' : 'ok';
const topRisk = res => Math.max(...res.checks.map(c => c.risk));
const routeLabel = route => (ROUTE_CONFIG[route] || {label: route}).label;

/** First reason from the riskiest check — the "why" behind a hold or block. */
function worstReason(res) {
  const worst = res.checks.reduce((a, c) => (c.risk > a.risk ? c : a), res.checks[0]);
  return worst.reasons[0] || '';
}

/** GET (no body) or POST JSON to the backend; throws with FastAPI's error detail. */
async function api(path, body) {
  const opts = body === undefined ? {} : {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(body),
  };
  const r = await fetch(API + path, opts);
  const data = await r.json().catch(() => ({}));
  if (!r.ok) {
    const d = data.detail;
    throw new Error(Array.isArray(d) ? d.map(x => `${x.loc.slice(1).join('.')}: ${x.msg}`).join('; ') : (d || `${r.status} ${r.statusText}`));
  }
  return data;
}

function log(svc, txt, tone = '') {
  const d = document.createElement('div');
  if (tone) d.className = tone;
  d.innerHTML = `<i>${ts()}</i><b>${esc(svc)}</b>${esc(txt)}`;
  $('#log').prepend(d);
  while ($('#log').children.length > 50) $('#log').lastChild.remove();
}

// Session state. A run is {payload, result, wasHeld}; newest first.
let S = {runs: [], disputes: [], busy: false, playing: false, seq: 100};
