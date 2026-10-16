/* LinuSetup UI core: helpers, backend bridge, store, router, overlays, effects.
   Classic script (not a module) so it works over file:// in WebKitGTK. */
'use strict';
const LS = window.LS = {};

/* ------------------------------------------------------------- helpers */
LS.$ = (s, r = document) => r.querySelector(s);
LS.$$ = (s, r = document) => [...r.querySelectorAll(s)];
LS.h = function h(tag, attrs, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === 'class') e.className = v;
    else if (k === 'style' && typeof v === 'object') Object.assign(e.style, v);
    else if (k.startsWith('on') && typeof v === 'function') e.addEventListener(k.slice(2), v);
    else if (k === 'html') e.innerHTML = v;
    else e.setAttribute(k, v === true ? '' : v);
  }
  for (const k of kids.flat(Infinity)) if (k != null && k !== false) e.append(k.nodeType ? k : document.createTextNode(String(k)));
  return e;
};
const h = LS.h;
LS.gb = n => n >= 1e12 ? (n / 1e12).toFixed(2) + ' TB' : n >= 1e9 ? (n / 1e9).toFixed(n >= 1e11 ? 0 : 1) + ' GB' : Math.max(1, Math.round(n / 1e6)) + ' MB';
LS.debounce = (fn, ms) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };
LS.clone = o => JSON.parse(JSON.stringify(o));
LS.sleep = ms => new Promise(r => setTimeout(r, ms));
LS.stagger = el => { LS.$$('.st', el).forEach((e, i) => e.style.setProperty('--i', Math.min(i, 14))); return el; };

const ICONS = {
  check: 'M20 6 9 17l-5-5', x: 'M18 6 6 18M6 6l12 12', arrow: 'M5 12h14M12 5l7 7-7 7', back: 'M19 12H5M12 19l-7-7 7-7',
  globe: 'M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20ZM2 12h20M12 2a15 15 0 0 1 0 20 15 15 0 0 1 0-20',
  keyboard: 'M3 6h18a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1ZM6 10h.01M10 10h.01M14 10h.01M18 10h.01M8 14h8',
  clock: 'M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20ZM12 6v6l4 2',
  wifi: 'M5 12.5a10 10 0 0 1 14 0M8.5 16a5 5 0 0 1 7 0M2 9a15 15 0 0 1 20 0M12 20h.01',
  server: 'M4 3h16a1 1 0 0 1 1 1v5a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1ZM4 14h16a1 1 0 0 1 1 1v5a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1v-5a1 1 0 0 1 1-1ZM7 6.5h.01M7 17.5h.01',
  disk: 'M22 12H2M5.5 5.1 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.5-6.9A2 2 0 0 0 16.8 4H7.2a2 2 0 0 0-1.7 1.1ZM6 16h.01M10 16h.01',
  lock: 'M5 11h14a1 1 0 0 1 1 1v8a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1v-8a1 1 0 0 1 1-1ZM8 11V7a4 4 0 0 1 8 0v4',
  rocket: 'M4.5 16.5c-1.5 1.26-2 5-2 5s3.74-.5 5-2c.71-.84.7-2.13-.09-2.91a2.18 2.18 0 0 0-2.91-.09ZM12 15l-3-3a22 22 0 0 1 2-3.95A12.88 12.88 0 0 1 22 2c0 2.72-.78 7.5-6 11a22.35 22.35 0 0 1-4 2ZM9 12H4s.55-3.03 2-4c1.62-1.08 5 0 5 0M12 15v5s3.03-.55 4-2c1.08-1.62 0-5 0-5',
  user: 'M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2M12 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8Z',
  users: 'M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8ZM22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75',
  monitor: 'M4 3h16a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2ZM8 21h8M12 17v4',
  package: 'm7.5 4.27 9 5.15M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16ZM3.3 7 12 12l8.7-5M12 22V12',
  sliders: 'M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3M1 14h6M9 8h6M17 16h6',
  terminal: 'm4 17 6-6-6-6M12 19h8',
  shield: 'M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1Z',
  save: 'M15.2 3a2 2 0 0 1 1.4.6l3.8 3.8a2 2 0 0 1 .6 1.4V19a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2ZM17 21v-7a1 1 0 0 0-1-1H8a1 1 0 0 0-1 1v7M7 3v4a1 1 0 0 0 1 1h7',
  upload: 'M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M17 8l-5-5-5 5M12 3v12',
  plus: 'M12 5v14M5 12h14',
  trash: 'M3 6h18M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2',
  edit: 'M12 20h9M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z',
  warn: 'M12 9v4M12 17h.01M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z',
  info: 'M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20ZM12 16v-4M12 8h.01',
  refresh: 'M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8M21 3v5h-5M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16M8 16H3v5',
  power: 'M12 2v10M18.4 6.6a9 9 0 1 1-12.77.04',
  leaf: 'M11 20A7 7 0 0 1 9.8 6.1C15.5 5 17 4.48 19 2c1 2 2 4.18 2 8 0 5.5-4.78 10-10 10ZM2 21c0-3 1.85-5.36 5.08-6C9.5 14.52 12 13 13 12',
  gaming: 'M6 12h4m-2-2v4M15 13h.01M18 11h.01M17.3 5H6.7a4 4 0 0 0-3.9 3.2l-1.3 6A3 3 0 0 0 4.4 18c1 0 1.9-.5 2.4-1.4L8 15h8l1.2 1.6c.5.9 1.4 1.4 2.4 1.4a3 3 0 0 0 2.9-3.8l-1.3-6A4 4 0 0 0 17.3 5Z',
  code: 'M16 18l6-6-6-6M8 6l-6 6 6 6',
  palette: 'M12 3a9 9 0 1 0 0 18c1.1 0 2-.9 2-2 0-.5-.2-1-.5-1.3-.3-.4-.5-.8-.5-1.3 0-1.1.9-2 2-2h2.4A3.6 3.6 0 0 0 21 10.8C21 6.5 17 3 12 3ZM7.5 11h.01M10.5 7.5h.01M15 7.5h.01',
  briefcase: 'M4 7h16a1 1 0 0 1 1 1v11a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V8a1 1 0 0 1 1-1ZM16 7V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v2',
  sparkles: 'M12 3l1.9 5.8L20 11l-6.1 2.2L12 19l-1.9-5.8L4 11l6.1-2.2ZM19 3v4M21 5h-4',
  wrench: 'M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76Z',
  eye: 'M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7ZM12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z',
  search: 'M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16ZM21 21l-4.35-4.35',
  cpu: 'M5 5h14v14H5ZM9 9h6v6H9ZM9 2v3M15 2v3M9 19v3M15 19v3M2 9h3M2 15h3M19 9h3M19 15h3',
  layers: 'm12 2 10 5-10 5L2 7ZM2 17l10 5 10-5M2 12l10 5 10-5',
  zap: 'M13 2 3 14h9l-1 8 10-12h-9Z',
  grid: 'M3 3h7v7H3ZM14 3h7v7h-7ZM14 14h7v7h-7ZM3 14h7v7H3Z',
  windows: 'M3 5.5 10 4.5v7H3ZM12 4.2 21 3v8.5h-9ZM3 13h7v7l-7-1ZM12 13h9v8l-9-1.3Z',
  logo: 'M12 3 3.5 20c2.8-1.6 5.6-2.4 8.5-2.4s5.7.8 8.5 2.4ZM12 9.5l-3 6.2',
  download: 'M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3',
  copy: 'M9 9h11a1 1 0 0 1 1 1v11a1 1 0 0 1-1 1H9a1 1 0 0 1-1-1V10a1 1 0 0 1 1-1ZM5 15H4a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v1',
};
LS.icon = function icon(name, cls) {
  const s = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  s.setAttribute('viewBox', '0 0 24 24'); s.setAttribute('class', 'i' + (cls ? ' ' + cls : ''));
  const p = document.createElementNS('http://www.w3.org/2000/svg', 'path');
  p.setAttribute('d', ICONS[name] || ICONS.info); s.append(p); return s;
};

/* ------------------------------------------------------------- backend */
LS.call = async function call(name, ...args) {
  if (window.pywebview) {
    const api = window.pywebview.api || {};
    if (typeof api[name] !== 'function') throw new Error('Backend method not available: ' + name);
    return await api[name](...args);
  }
  const r = await fetch('/api/' + name, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ args }) });
  const data = await r.json();
  if (!r.ok) throw new Error(data.error || ('HTTP ' + r.status));
  return data;
};

/* ------------------------------------------------------------- store */
const S = LS.S = {
  boot: null, cfg: null, disks: [], fps: {}, check: null, mode: 'easy', checking: false,
  uses: ['everyday'], ntfs: {}, finish: 'none', installed: null,
};
const listeners = {};
LS.on = (ev, fn) => { (listeners[ev] = listeners[ev] || []).push(fn); return () => { listeners[ev] = listeners[ev].filter(f => f !== fn); }; };
LS.emit = (ev, data) => (listeners[ev] || []).slice().forEach(fn => { try { fn(data); } catch (e) { console.error(e); } });

/* Change the config. The callback mutates S.cfg; validation runs debounced. */
LS.set = function set(fn) { fn(S.cfg); LS.emit('cfg'); runCheck(); };
let checkSeq = 0;
const runCheckNow = async () => {
  const seq = ++checkSeq; S.checking = true; LS.emit('checking');
  try {
    const res = await LS.call('check', S.cfg);
    if (seq === checkSeq) { S.check = res; S.checking = false; LS.emit('checked', res); }
  } catch (e) { S.checking = false; console.error(e); }
};
const runCheck = LS.debounce(runCheckNow, 220);
LS.checkNow = runCheckNow;
LS.issues = (section, kind = 'errors') => ((S.check && S.check[kind]) || []).filter(i => !section || i.section === section);

LS.loadDisks = async function loadDisks() {
  S.disks = await LS.call('disks');
  S.fps = Object.fromEntries(S.disks.map(d => [d.path, d.fingerprint]));
  LS.emit('disks'); return S.disks;
};
LS.disk = path => S.disks.find(d => d.path === path);

/* ------------------------------------------------------------- router */
const view = () => LS.$('#view');
const screens = LS.screens = {};
let current = null, busy = false, history = [];
LS.current = () => current;
LS.isBusy = () => busy;

LS.go = function go(name, opts = {}) {
  if (busy && !opts.force) return false;
  const def = screens[name];
  if (!def) { console.error('no screen', name); return false; }
  busy = true;
  const dir = opts.dir || 'r';
  const old = current;
  if (old) {
    if (!opts.replace && !opts.back) history.push(old.name);
    old.cleanups.forEach(f => { try { f(); } catch (e) { console.error(e); } });
    if (LS.fx.at('balanced')) {
      old.el.classList.add(dir === 'r' ? 'out-l' : 'out-r');
      setTimeout(() => old.el.remove(), 240);
    } else old.el.remove();          // minimal: no exit animation, swap instantly
  }
  const el = h('section', { class: 'screen fresh ' + (def.center ? 'center ' : '') + (dir === 'up' ? 'in-up' : 'in-' + dir), 'data-screen': name });
  setTimeout(() => el.classList.remove('fresh'), 1400);
  const wrap = h('div', { class: 'wrap' });
  el.append(wrap);
  const ctx = { name, el, wrap, cleanups: [], footer: null, params: opts.params || {} };
  ctx.on = (ev, fn) => ctx.cleanups.push(LS.on(ev, fn));
  ctx.every = (ms, fn) => { const t = setInterval(fn, ms); ctx.cleanups.push(() => clearInterval(t)); };
  current = ctx;
  try { def.render(wrap, ctx); } catch (e) { console.error(e); wrap.append(errorBox(e)); }
  LS.stagger(wrap);
  view().append(el);
  LS.renderChrome();
  setTimeout(() => { busy = false; }, 260);
  return true;
};
LS.back = function back() {
  const prev = history.pop();
  if (prev) LS.go(prev, { dir: 'l', back: true });
};
LS.resetHistory = (stack = []) => { history = stack; };
function errorBox(e) { return h('div', { class: 'note err' }, LS.icon('warn'), 'Something broke while drawing this screen: ' + e.message); }

/* Footer and header for the current screen. Screens set ctx.footer = {back, next, hint}. */
LS.renderChrome = function renderChrome() {
  const ctx = current; if (!ctx) return;
  const def = screens[ctx.name];
  const f = (typeof def.footer === 'function' ? def.footer(ctx) : def.footer) || {};
  const bar = LS.$('#bar'); bar.textContent = '';
  const back = h('button', { class: 'btn ghost', id: 'btn-back', onclick: () => (f.back && f.back.action ? f.back.action() : LS.back()) },
    LS.icon('back'), (f.back && f.back.label) || 'Back');
  if (!f.back) back.style.visibility = 'hidden';
  const hint = h('div', { class: 'hint' }, f.hint || '');
  bar.append(back, hint);
  if (f.extra) bar.append(f.extra);
  if (f.next) {
    const n = f.next;
    const btn = h('button', { class: 'btn ' + (n.kind || ''), id: 'btn-next', onclick: () => { if (!btn.disabled) n.action(); } },
      n.label || 'Continue', LS.icon(n.icon || 'arrow'));
    btn.disabled = !!(n.disabled && n.disabled());
    bar.append(btn);
  }
  // header
  const dots = LS.$('#dots'); dots.textContent = '';
  if (def.step != null && S.mode === 'easy') {
    dots.className = 'dots';
    for (let i = 0; i < LS.EASY_STEPS; i++) dots.append(h('div', { class: 'dot' + (i === def.step ? ' on' : i < def.step ? ' done' : '') }));
  } else {
    dots.className = 'crumbs';
    if (def.crumb) dots.append(...def.crumb(ctx).flatMap((c, i, a) => i < a.length - 1 ? [h('span', {}, c), LS.icon('arrow')] : [h('b', {}, c)]));
  }
};
LS.refreshFooter = () => LS.renderChrome();

LS.renderBadges = function renderBadges() {
  const b = LS.$('#badges'); b.textContent = '';
  if (!S.boot) return;
  if (S.boot.dry_run) b.append(h('span', { class: 'badge warn', title: 'Nothing on this computer will be changed' }, h('span', { class: 'pulse' }), S.boot.fixture ? 'Demo hardware · dry run' : 'Dry run'));
  b.append(h('span', { class: 'badge ' + (S.online ? 'ok' : 'bad') }, LS.icon('wifi'), S.online ? 'Online' : 'Offline'));
  const fx = LS.fx.tier;
  b.append(h('button', { class: 'badge fxbadge', id: 'fx-badge', title: 'Animation level: ' + (LS.fx.why || fx), onclick: LS.fx.menu },
    LS.icon('sparkles'), 'Effects: ' + fx[0].toUpperCase() + fx.slice(1) + (LS.fx.manual ? '' : ' (auto)')));
};

/* ------------------------------------------------------------- overlays */
LS.dialog = function dialog({ title, lead, body, actions = [], wide, onClose }) {
  const ov = h('div', { class: 'overlay' });
  const box = h('div', { class: 'dlg' + (wide ? ' wide' : ''), role: 'dialog' });
  const close = () => { ov.remove(); document.removeEventListener('keydown', esc, true); onClose && onClose(); };
  const esc = e => { if (e.key === 'Escape') { e.stopPropagation(); close(); } };
  document.addEventListener('keydown', esc, true);
  if (title) box.append(h('h2', {}, title));
  if (lead) box.append(h('p', { class: 'lead' }, lead));
  if (body) box.append(typeof body === 'function' ? body(close) : body);
  const acts = h('div', { class: 'acts' });
  actions.forEach(a => {
    const btn = h('button', { class: 'btn ' + (a.kind === undefined ? 'ghost' : a.kind), id: a.id }, a.icon ? LS.icon(a.icon) : null, a.label);
    btn.addEventListener('click', async () => { if (btn.disabled) return; const keep = a.onClick ? await a.onClick(close, btn) : false; if (!keep) close(); });
    if (a.disabled) btn.disabled = true;
    a.ref && a.ref(btn);
    acts.append(btn);
  });
  if (actions.length) box.append(acts);
  ov.append(box);
  ov.addEventListener('mousedown', e => { if (e.target === ov) close(); });
  document.body.append(ov);
  setTimeout(() => { const f = box.querySelector('input, textarea'); f && f.focus(); }, 60);
  return close;
};
LS.toast = function toast(msg, kind = 'info', ms = 4200) {
  const box = LS.$('#toasts');
  const t = h('div', { class: 'toast ' + kind }, LS.icon(kind === 'err' ? 'warn' : kind === 'ok' ? 'check' : kind === 'warn' ? 'warn' : 'info'), h('div', {}, msg));
  box.append(t);
  setTimeout(() => { t.classList.add('out'); setTimeout(() => t.remove(), 300); }, ms);
};
LS.notes = function notes(section) {
  const box = h('div', { class: 'issues' });
  const draw = () => {
    box.textContent = '';
    LS.issues(section).forEach(i => box.append(h('div', { class: 'note err' }, LS.icon('warn'), i.message)));
    LS.issues(section, 'warnings').forEach(i => box.append(h('div', { class: 'note warn' }, LS.icon('info'), i.message)));
    box.classList.toggle('hidden', !box.childNodes.length);
  };
  draw(); box._draw = draw; return box;
};

/* ------------------------------------------------------------- effects */
/* Three levels, chosen by the backend from the GPU (effects.py), stepped down if the
   measured frame rate is low, and overridable from the "Effects" badge:
     minimal   no animation at all (spinners only), flat background, no shadows
     balanced  page transitions, short entrance, ripples; no cursor glow, no tilt
     full      everything                                                            */
LS.fx = { TIERS: ['minimal', 'balanced', 'full'], tier: 'full', why: '', manual: false };
const root = document.documentElement;
LS.fx.at = t => LS.fx.TIERS.indexOf(LS.fx.tier) >= LS.fx.TIERS.indexOf(t);
LS.fx.set = function set(tier, why, manual) {
  if (!LS.fx.TIERS.includes(tier)) return;
  LS.fx.TIERS.forEach(t => root.classList.remove('fx-' + t));
  root.classList.add('fx-' + tier);
  Object.assign(LS.fx, { tier, why: why || LS.fx.why, manual: !!manual });
  if (tier !== 'full') { untilt(tiltCard); tiltCard = hoverCard = null; LS.$('#glow').classList.remove('on'); }
  if (LS.renderBadges) LS.renderBadges();
};
LS.fx.init = function init(detected) {
  const q = new URLSearchParams(location.search);
  if (q.has('still')) root.classList.add('still');
  const forced = q.get('fx') || (q.has('lite') ? 'minimal' : null);
  if (forced) return LS.fx.set(forced, 'set in the page address', true);
  const d = detected || { tier: 'full', reason: '', auto: true };
  LS.fx.set(d.tier, d.reason, !d.auto);
  if (!d.auto || d.tier === 'minimal') return;
  // Safety net: measure the real frame rate once and step down if it is low.
  let n = 0; const t0 = performance.now();
  (function f(t) {
    n++;
    if (t - t0 < 1500) return requestAnimationFrame(f);
    const fps = Math.round(n / ((t - t0) / 1000));
    if (LS.fx.manual) return;
    if (fps < 28) LS.fx.set('minimal', `${d.reason}; measured ${fps} fps`);
    else if (fps < 45 && LS.fx.tier === 'full') LS.fx.set('balanced', `${d.reason}; measured ${fps} fps`);
  })(t0);
};
LS.fx.menu = function menu() {
  const det = (S.boot && S.boot.effects) || {};
  const desc = { minimal: 'No animations. Fastest on integrated graphics, weak GPUs and VMs.',
    balanced: 'Smooth page changes and feedback, without the heavy extras.', full: 'Everything: cursor glow, 3D tilt, confetti.' };
  const pick = (tier, manual) => { LS.fx.set(tier, manual ? 'chosen manually' : det.reason, manual); close(); };
  const close = LS.dialog({ title: 'Effects', lead: `Detected: ${det.detected || det.tier || '?'}, ${det.reason || ''}`,
    body: h('div', { class: 'choices' },
      W().choice({ id: 'fx-auto', title: `Automatic (${det.detected || det.tier})`, desc: 'Picked for this computer\'s graphics.', sel: !LS.fx.manual, onClick: () => pick(det.detected || det.tier || 'minimal', false) }),
      LS.fx.TIERS.map(t => W().choice({ id: 'fx-' + t, title: t[0].toUpperCase() + t.slice(1), desc: desc[t], sel: LS.fx.manual && LS.fx.tier === t, onClick: () => pick(t, true) }))),
    actions: [{ label: 'Close' }] });
};
const W = () => LS.w;

document.addEventListener('pointerdown', e => {
  if (!LS.fx.at('balanced')) return;
  const t = e.target.closest('.btn, .card, .disk, .tile, .choice'); if (!t || e.button !== 0) return;
  const r = t.getBoundingClientRect();
  const s = h('span', { class: 'ripple', style: { left: (e.clientX - r.left) + 'px', top: (e.clientY - r.top) + 'px' } });
  t.append(s); setTimeout(() => s.remove(), 700);
});
document.addEventListener('contextmenu', e => { if (!e.target.closest('input, textarea, .selectable')) e.preventDefault(); });
/* Pointer effects (full only): at most one style write per animation frame, transforms only. */
let gx = 0, gy = 0, raf = 0, tiltCard = null, hoverCard = null;
function untilt(c) { if (!c) return; c.classList.remove('tilting'); c.style.transform = ''; }
function frame() {
  raf = 0;
  LS.$('#glow').style.transform = `translate3d(${gx}px,${gy}px,0)`;
  if (hoverCard !== tiltCard) { untilt(tiltCard); tiltCard = hoverCard; }
  if (!tiltCard) return;
  const r = tiltCard.getBoundingClientRect();
  const px = Math.min(1, Math.max(0, (gx - r.left) / r.width)), py = Math.min(1, Math.max(0, (gy - r.top) / r.height));
  tiltCard.classList.add('tilting');
  tiltCard.style.transform = `perspective(800px) rotateX(${((.5 - py) * 8).toFixed(2)}deg) rotateY(${((px - .5) * 8).toFixed(2)}deg)`;
  const shine = tiltCard.querySelector('.shine');
  if (shine) shine.style.transform = `translate3d(${(px * r.width).toFixed(0)}px,${(py * r.height).toFixed(0)}px,0)`;
}
document.addEventListener('pointermove', e => {
  dbg(e);
  if (LS.fx.tier !== 'full') return;
  gx = e.clientX; gy = e.clientY;
  LS.$('#glow').classList.add('on');
  hoverCard = e.target.closest ? e.target.closest('.card:not(.off)') : null;
  if (!raf) raf = requestAnimationFrame(frame);
}, { passive: true });
document.addEventListener('pointerleave', () => { hoverCard = null; untilt(tiltCard); tiltCard = null; });
let lastBtn = '-';
function dbg(e) { const d = LS.$('#dbg'); if (d && !d.classList.contains('hidden')) d.textContent = `pointer ${e.clientX}, ${e.clientY}\nlast button: ${lastBtn}\nscreen: ${current && current.name}\neffects: ${LS.fx.tier}`; }
document.addEventListener('pointerdown', e => { lastBtn = ['left', 'middle', 'right'][e.button] || e.button; dbg(e); });
document.addEventListener('keydown', e => { if (e.key === 'F2') LS.$('#dbg').classList.toggle('hidden'); });

LS.fx.confetti = function confetti() {
  if (!LS.fx.at('balanced') || matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  const cv = LS.$('#fx'), ctx = cv.getContext('2d'); cv.width = innerWidth; cv.height = innerHeight;
  const cols = ['#8b5cf6', '#22d3ee', '#34d399', '#fbbf24', '#f472b6'];
  const n = LS.fx.tier === 'full' ? 160 : 50;
  const ps = Array.from({ length: n }, () => ({ x: innerWidth / 2, y: innerHeight * .4, vx: (Math.random() - .5) * 16, vy: -Math.random() * 15 - 4,
    s: 5 + Math.random() * 6, c: cols[Math.random() * cols.length | 0], r: Math.random() * 6 }));
  let f = 0;
  (function loop() {
    ctx.clearRect(0, 0, cv.width, cv.height);
    ps.forEach(p => { p.vy += .33; p.vx *= .995; p.x += p.vx; p.y += p.vy; p.r += .18; ctx.fillStyle = p.c; ctx.save(); ctx.translate(p.x, p.y); ctx.rotate(p.r); ctx.fillRect(-p.s / 2, -p.s / 4, p.s, p.s / 2); ctx.restore(); });
    if (++f < 220) requestAnimationFrame(loop); else ctx.clearRect(0, 0, cv.width, cv.height);
  })();
};
