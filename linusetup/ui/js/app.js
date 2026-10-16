/* LinuSetup front end. Talks to Python via window.pywebview.api, or to a mock
   when opened in a plain browser (so the design can be iterated without Python). */
(() => {
'use strict';
const $ = (s, r = document) => r.querySelector(s);
const SCREENS = ['welcome', 'vibe', 'disk', 'you', 'install', 'done'];
const DOTS = 5;  // welcome, vibe, disk, you, install

const ICONS = {
  gaming: 'M6 12h4m-2-2v4M15 13h.01M18 11h.01M17.3 5H6.7a4 4 0 0 0-3.9 3.2l-1.3 6A3 3 0 0 0 4.4 18c1 0 1.9-.5 2.4-1.4L8 15h8l1.2 1.6c.5.9 1.4 1.4 2.4 1.4a3 3 0 0 0 2.9-3.8l-1.3-6A4 4 0 0 0 17.3 5Z',
  coding: 'M16 18l6-6-6-6M8 6l-6 6 6 6',
  everyday: 'M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20ZM2 12h20M12 2a15 15 0 0 1 0 20 15 15 0 0 1 0-20',
  creating: 'M12 3a9 9 0 1 0 0 18c1.1 0 2-.9 2-2 0-.5-.2-1-.5-1.3-.3-.4-.5-.8-.5-1.3 0-1.1.9-2 2-2h2.4A3.6 3.6 0 0 0 21 10.8C21 6.5 17 3 12 3ZM7.5 11h.01M10.5 7.5h.01M15 7.5h.01',
  disk: 'M22 12H2M5.5 5.1 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.5-6.9A2 2 0 0 0 16.8 4H7.2a2 2 0 0 0-1.7 1.1ZM6 16h.01M10 16h.01',
  check: 'M20 6 9 17l-5-5',
  cross: 'M18 6 6 18M6 6l12 12',
  wait: 'M12 6v6l4 2',
};
function icon(name) {
  const s = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  s.setAttribute('viewBox', '0 0 24 24'); s.setAttribute('class', 'i');
  const p = document.createElementNS('http://www.w3.org/2000/svg', 'path');
  p.setAttribute('d', ICONS[name] || ICONS.disk); s.appendChild(p); return s;
}
function h(tag, attrs = {}, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === 'class') e.className = v; else if (k.startsWith('on')) e.addEventListener(k.slice(2), v); else e.setAttribute(k, v);
  }
  for (const k of kids.flat()) if (k != null) e.append(k.nodeType ? k : document.createTextNode(k));
  return e;
}

/* ---------------------------------------------------------------- state */
const state = {
  screen: 0, info: null, disks: [], busy: false, dry: true,
  cfg: { presets: ['everyday'], disk: '', fullname: '', username: '', hostname: 'linusetup', password: '', timezone: 'UTC', keymap: 'us' },
  password2: '', touched: {},
};

/* ------------------------------------------------------------ mock API */
const mockApi = {
  async system_info() {
    return { dry_run: true, live: false, online: true, uefi: true, cpu: 'amd', gpus: ['amd'], virt: '', ram_gb: 16,
      presets: [
        { id: 'gaming', name: 'Gaming', blurb: 'Steam, GPU drivers, Proton-ready', packages: ['steam', 'gamemode', 'mangohud'] },
        { id: 'coding', name: 'Coding', blurb: 'Git, Docker, a solid editor', packages: ['base-devel', 'git', 'docker', 'neovim', 'code'] },
        { id: 'everyday', name: 'Everyday', blurb: 'Office, media and the basics', packages: ['libreoffice-fresh', 'vlc', 'thunderbird'] },
        { id: 'creating', name: 'Creating', blurb: 'Blender, Krita, OBS and friends', packages: ['blender', 'krita', 'obs-studio'] }],
      timezones: ['UTC', 'Africa/Cairo', 'Europe/London', 'America/New_York', 'Asia/Tokyo'], keymaps: ['us', 'uk', 'de', 'fr', 'ara'] };
  },
  async disks() {
    return [
      { path: '/dev/vda', name: 'vda', model: 'Samsung SSD 980', size_gb: 500, transport: 'nvme', rotational: false, removable: false, contents: [], usable: true, reason: '' },
      { path: '/dev/sdb', name: 'sdb', model: 'WD Blue', size_gb: 1000, transport: 'sata', rotational: true, removable: false, contents: ['ntfs'], usable: true, reason: '' },
      { path: '/dev/sdc', name: 'sdc', model: 'USB Stick', size_gb: 8, transport: 'usb', rotational: false, removable: true, contents: [], usable: false, reason: 'Too small (needs 20 GB)' }];
  },
  async start_install() {
    const steps = ['Preparing the disk', 'Creating filesystems', 'Installing Arch Linux and your desktop', 'Configuring the system', 'Creating your account', 'Installing the boot loader', 'Finishing up'];
    let i = 0, p = 0;
    const tick = setInterval(() => {
      if (i === 0 || p >= (i / steps.length)) { window.LinuSetup.onEvent({ type: 'step', label: steps[i], index: i, total: steps.length }); i++; }
      p += 0.012; window.LinuSetup.onEvent({ type: 'progress', value: Math.min(p, 1) });
      window.LinuSetup.onEvent({ type: 'log', line: '[mock] working… ' + Math.round(p * 100) + '%' });
      if (p >= 1) { clearInterval(tick); window.LinuSetup.onEvent({ type: 'done', dry_run: true }); }
    }, 90);
    return { ok: true, dry_run: true };
  },
  async reboot() { return { ok: true, dry_run: true }; },
};
const api = () => (window.pywebview && window.pywebview.api) ? window.pywebview.api : mockApi;

/* --------------------------------------------------------------- stage */
const stage = $('#stage');
function screenEl(i) { return $(`[data-screen="${SCREENS[i]}"]`, stage); }

function show(i, instant) {
  const dir = i >= state.screen ? 'r' : 'l';
  const from = screenEl(state.screen), to = screenEl(i);
  if (from !== to && !instant) {
    from.classList.add(dir === 'r' ? 'leave-l' : 'leave-r');
    setTimeout(() => from.classList.remove('on', 'leave-l', 'leave-r'), 220);
  } else if (from !== to) from.classList.remove('on');
  state.screen = i;
  to.classList.remove('enter-r', 'enter-l', 'leave-l', 'leave-r');
  to.classList.add('on', dir === 'r' ? 'enter-r' : 'enter-l');
  [...to.querySelectorAll('.st')].forEach((el, k) => el.style.setProperty('--i', k));
  renderDots(); renderFooter();
}

function renderDots() {
  const d = $('#dots'); d.textContent = '';
  for (let k = 0; k < DOTS; k++) d.append(h('div', { class: 'dot' + (k === state.screen ? ' on' : k < state.screen ? ' done' : '') }));
}

function renderFooter() {
  const s = SCREENS[state.screen], back = $('#back'), next = $('#next');
  back.style.visibility = (s === 'vibe' || s === 'disk' || s === 'you') ? 'visible' : 'hidden';
  next.style.display = (s === 'install' || s === 'done') ? 'none' : '';
  next.textContent = { welcome: 'Get started', vibe: 'Continue', disk: 'Continue', you: 'Review' }[s] || 'Continue';
  next.disabled = !stepValid(s);
  if (s === 'done') { next.style.display = ''; next.textContent = state.dry ? 'Close' : 'Restart now'; next.disabled = false; back.style.visibility = 'hidden'; }
}

function stepValid(s) {
  if (s === 'welcome') return !!state.info;
  if (s === 'disk') return !!state.cfg.disk;
  if (s === 'you') return Object.keys(errors()).length === 0;
  return true;
}

/* ------------------------------------------------------------- welcome */
function renderWelcome() {
  const i = state.info, box = $('#checks'); box.textContent = '';
  const items = [
    [i.uefi ? 'ok' : 'ok', i.uefi ? 'UEFI firmware' : 'Legacy BIOS', i.uefi ? 'Modern boot supported' : 'Will use GRUB'],
    [i.online ? 'ok' : 'bad', i.online ? 'Internet connected' : 'No internet', i.online ? 'Ready to download' : 'Connect a cable, then reopen'],
    [i.ram_gb >= 2 ? 'ok' : 'bad', `${i.ram_gb || '?'} GB memory`, i.ram_gb >= 2 ? 'Plenty' : 'At least 2 GB recommended'],
  ];
  items.forEach(([kind, title, sub], k) => {
    const ic = h('div', { class: 'ic' }, icon(kind === 'ok' ? 'check' : 'cross'));
    const c = h('div', { class: 'chk ' + (kind === 'ok' ? '' : 'bad'), style: `animation-delay:${400 + k * 150}ms` }, ic, h('div', {}, title, h('small', {}, sub)));
    c.classList.add('st'); c.style.setProperty('--i', 4 + k); box.append(c);
  });
  const b = $('#badges'); b.textContent = '';
  if (i.dry_run) b.append(h('div', { class: 'badge warn' }, 'Dry run: nothing will be changed'));
  else b.append(h('div', { class: 'badge ok' }, 'Live install mode'));
}

/* ---------------------------------------------------------------- vibe */
function renderVibes() {
  const g = $('#vibes'); g.textContent = '';
  state.info.presets.forEach((p, k) => {
    const sel = state.cfg.presets.includes(p.id);
    const c = h('div', { class: 'card st' + (sel ? ' sel' : ''), 'data-id': p.id },
      h('div', { class: 'tick' }, icon('check')),
      h('div', { class: 'ico' }, icon(p.id)), h('b', {}, p.name), h('small', {}, p.blurb));
    c.style.setProperty('--i', 2 + k);
    c.addEventListener('click', () => {
      const a = state.cfg.presets, ix = a.indexOf(p.id);
      ix >= 0 ? a.splice(ix, 1) : a.push(p.id); c.classList.toggle('sel', ix < 0);
    });
    c.addEventListener('contextmenu', e => {
      e.preventDefault();
      openCtx(e.clientX, e.clientY, p.name, p.packages.length ? p.packages.join(', ') : 'Nothing extra.');
    });
    g.append(c);
  });
}

/* ---------------------------------------------------------------- disk */
async function renderDisks() {
  const box = $('#disks'); box.textContent = '';
  state.disks = await api().disks();
  if (!state.disks.length) box.append(h('div', { class: 'sub' }, 'No disks found. If you are in a VM, add a virtual disk.'));
  if (!state.disks.some(d => d.path === state.cfg.disk && d.usable)) state.cfg.disk = '';
  state.disks.forEach((d, k) => {
    const chips = [h('span', { class: 'chip red' }, 'Will be erased')];
    if (d.contents.length) chips.unshift(h('span', { class: 'chip' }, 'Has data: ' + d.contents.join(', ')));
    if (d.contents.includes('ntfs')) chips.push(h('span', { class: 'chip soon' }, 'Install alongside Windows: coming soon'));
    const row = h('div', { class: 'disk st' + (d.usable ? '' : ' off') + (state.cfg.disk === d.path ? ' sel' : '') },
      h('div', { class: 'ico' }, icon('disk')),
      h('div', { class: 'meta' }, h('b', {}, d.model), h('small', {}, `${d.path} · ${d.size_gb} GB · ${(d.transport || (d.rotational ? 'hdd' : 'ssd')).toUpperCase()}${d.removable ? ' · removable' : ''}`),
        h('div', { class: 'chips' }, d.usable ? chips : [h('span', { class: 'chip' }, d.reason)])),
      h('div', { class: 'tick' }, icon('check')));
    row.style.setProperty('--i', 2 + k);
    row.addEventListener('click', () => {
      if (!d.usable) return;
      state.cfg.disk = d.path;
      box.querySelectorAll('.disk').forEach(x => x.classList.remove('sel')); row.classList.add('sel'); renderFooter();
    });
    box.append(row);
  });
  $('#disk-note').textContent = state.info.virt ? 'Running in a virtual machine: this is a virtual disk, your real disks are safe.' : '';
  renderFooter();
}

/* ----------------------------------------------------------------- you */
function errors() {
  const c = state.cfg, e = {};
  if (!/^[a-z_][a-z0-9_-]{0,31}$/.test(c.username) || ['root', 'sddm', 'docker', 'nobody', 'bin', 'daemon', 'sys'].includes(c.username)) e.username = 'Lowercase letters, digits, - or _';
  if (c.password.length < 4) e.password = 'At least 4 characters';
  if (c.password !== state.password2) e.password2 = 'Passwords do not match';
  if (!/^[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$/.test(c.hostname)) e.hostname = 'Letters, digits and dashes only';
  if (/[:,\n]/.test(c.fullname)) e.fullname = 'No colons or commas';
  return e;
}
function showErrors() {
  const e = errors();
  for (const f of ['username', 'password2', 'hostname', 'fullname']) {
    const box = $('#f-' + f); if (!box) continue;
    const show = e[f] && state.touched[f];
    box.classList.toggle('err', !!show);
    const m = box.querySelector('.msg'); if (m) m.textContent = show ? e[f] : '';
  }
  const pw = state.cfg.password; let s = 0;
  if (pw.length >= 4) s++; if (pw.length >= 8) s++; if (/[A-Z]/.test(pw) && /[a-z]/.test(pw)) s++; if (/\d/.test(pw) && /[^\w]/.test(pw)) s++;
  const m = $('#meter'); m.style.transform = `scaleX(${pw ? Math.max(.12, s / 4) : 0})`;
  m.style.background = ['#f87171', '#f87171', '#fbbf24', '#34d399', '#22d3ee'][s];
  renderFooter();
}
function initForm() {
  const tz = $('#timezone'), km = $('#keymap');
  state.info.timezones.forEach(z => tz.append(h('option', { value: z }, z)));
  state.info.keymaps.forEach(k => km.append(h('option', { value: k }, k)));
  let guess = 'UTC'; try { guess = Intl.DateTimeFormat().resolvedOptions().timeZone; } catch (_) {}
  tz.value = state.info.timezones.includes(guess) ? guess : 'UTC'; state.cfg.timezone = tz.value;
  const bind = (id, get) => $('#' + id).addEventListener('input', ev => { get(ev.target.value); state.touched[id] = true; showErrors(); });
  bind('fullname', v => state.cfg.fullname = v);
  bind('username', v => state.cfg.username = v.trim());
  bind('password', v => { state.cfg.password = v; state.touched.password2 = !!state.password2; });
  bind('password2', v => state.password2 = v);
  bind('hostname', v => state.cfg.hostname = v.trim());
  tz.addEventListener('change', () => state.cfg.timezone = tz.value);
  km.addEventListener('change', () => state.cfg.keymap = km.value);
}

/* ------------------------------------------------------------- confirm */
function openConfirm() {
  const c = state.cfg, d = state.disks.find(x => x.path === c.disk), word = c.disk.replace('/dev/', '');
  const names = state.info.presets.filter(p => c.presets.includes(p.id)).map(p => p.name);
  const sum = $('#sum'); sum.textContent = '';
  [['Disk', `${d.model} (${c.disk}, ${d.size_gb} GB)`], ['Desktop', 'KDE Plasma'], ['Extras', names.join(', ') || 'None'],
   ['User', c.username], ['Computer', c.hostname], ['Timezone', c.timezone]].forEach(([k, v]) => sum.append(h('dt', {}, k), h('dd', {}, v)));
  $('#confirm-label').textContent = `Everything on ${c.disk} will be erased. Type "${word}" to confirm.`;
  const inp = $('#confirm'); inp.value = ''; inp.placeholder = word; $('#m-go').disabled = true;
  inp.oninput = () => $('#m-go').disabled = inp.value.trim() !== word;
  $('#modal').classList.add('on'); setTimeout(() => inp.focus(), 50);
}
const closeConfirm = () => $('#modal').classList.remove('on');

/* ------------------------------------------------------------- install */
async function startInstall() {
  closeConfirm();
  $('#steps').textContent = ''; $('#log').textContent = ''; $('#errbox').classList.add('hidden');
  $('#inst-title').textContent = 'Installing…'; setProgress(0);
  show(4);
  const res = await api().start_install({ ...state.cfg });
  if (!res.ok) showError(res.error, []); else state.dry = res.dry_run;
}
function setProgress(v) {
  $('#fill').style.transform = `scaleX(${v})`; $('#inst-pct').textContent = Math.round(v * 100) + '%';
}
function showError(msg, tail) {
  $('#inst-title').textContent = 'Something went wrong';
  const box = $('#errbox'); box.classList.remove('hidden'); box.textContent = '';
  box.append(h('b', {}, msg), h('pre', { style: 'white-space:pre-wrap;margin:8px 0 12px;font-size:12px;user-select:text' }, (tail || []).join('\n')),
    h('button', { class: 'btn ghost', onclick: () => { show(3); } }, 'Go back'));
  $('#log').classList.remove('hidden');
}
let lastStep = null;
function onEvent(ev) {
  if (ev.type === 'step') {
    if (lastStep) { lastStep.classList.remove('now'); lastStep.classList.add('done'); lastStep.querySelector('.ic').replaceChildren(icon('check')); }
    const li = h('div', { class: 'stp now' }, h('div', { class: 'ic' }), ev.label); $('#steps').append(li); lastStep = li;
    $('#inst-step').textContent = ev.label;
  } else if (ev.type === 'progress') setProgress(ev.value);
  else if (ev.type === 'log') {
    const l = $('#log'); l.append(ev.line + '\n'); if (l.childNodes.length > 400) l.removeChild(l.firstChild); l.scrollTop = l.scrollHeight;
  } else if (ev.type === 'done') {
    state.dry = !!ev.dry_run; setProgress(1); lastStep = null;
    setTimeout(() => { $('#dry-note').classList.toggle('hidden', !state.dry); show(5); confetti(); }, 500);
  } else if (ev.type === 'error') showError(ev.message, ev.tail);
}
window.LinuSetup = { onEvent };

/* -------------------------------------------------- mouse + animation fx */
function openCtx(x, y, title, body) {
  const c = $('#ctx'); c.textContent = ''; c.append(h('h4', {}, title), h('p', {}, body));
  c.classList.add('on');
  const w = c.offsetWidth, hh = c.offsetHeight;
  c.style.left = Math.min(x, innerWidth - w - 10) + 'px'; c.style.top = Math.min(y, innerHeight - hh - 10) + 'px';
}
document.addEventListener('pointerdown', e => {
  if (!e.target.closest('#ctx')) $('#ctx').classList.remove('on');
  const t = e.target.closest('.btn, .card, .disk'); if (!t || e.button !== 0) return;
  const r = t.getBoundingClientRect();
  const s = h('span', { class: 'ripple', style: `left:${e.clientX - r.left}px;top:${e.clientY - r.top}px` });
  t.append(s); setTimeout(() => s.remove(), 700);
});
document.addEventListener('contextmenu', e => e.preventDefault());  // no browser menu in the kiosk

let gx = 0, gy = 0, raf = 0;
const glow = $('#glow');
document.addEventListener('pointermove', e => {
  gx = e.clientX; gy = e.clientY; glow.classList.add('on');
  if (!raf) raf = requestAnimationFrame(() => { glow.style.transform = `translate3d(${gx}px,${gy}px,0)`; raf = 0; });
  const c = e.target.closest('.card');
  if (c && !document.documentElement.classList.contains('lite')) {
    const r = c.getBoundingClientRect(), px = (e.clientX - r.left) / r.width, py = (e.clientY - r.top) / r.height;
    c.style.setProperty('--ry', ((px - .5) * 10).toFixed(1) + 'deg'); c.style.setProperty('--rx', ((.5 - py) * 10).toFixed(1) + 'deg');
    c.style.setProperty('--mx', (px * 100) + '%'); c.style.setProperty('--my', (py * 100) + '%');
  }
  dbgUpdate(e);
});
document.addEventListener('pointerout', e => { const c = e.target.closest && e.target.closest('.card'); if (c) { c.style.setProperty('--rx', '0deg'); c.style.setProperty('--ry', '0deg'); } });

/* F2 toggles a pointer debug overlay: handy when testing mouse input in the VM */
const dbg = $('#dbg'); let lastBtn = '-';
function dbgUpdate(e) { if (!dbg.classList.contains('hidden')) dbg.textContent = `x ${e.clientX}  y ${e.clientY}\nlast button: ${lastBtn}`; }
document.addEventListener('pointerdown', e => { lastBtn = ['left', 'middle', 'right'][e.button] || e.button; dbgUpdate(e); });
document.addEventListener('keydown', e => { if (e.key === 'F2') dbg.classList.toggle('hidden'); });

function confetti() {
  if (matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  const cv = $('#fx'), ctx = cv.getContext('2d'); cv.width = innerWidth; cv.height = innerHeight;
  const cols = ['#8b5cf6', '#22d3ee', '#34d399', '#fbbf24', '#f472b6'];
  const lite = document.documentElement.classList.contains('lite');
  const ps = Array.from({ length: lite ? 60 : 140 }, () => ({ x: innerWidth / 2, y: innerHeight * .45, vx: (Math.random() - .5) * 14, vy: -Math.random() * 14 - 4,
    s: 5 + Math.random() * 6, c: cols[Math.random() * cols.length | 0], r: Math.random() * 6 }));
  let f = 0;
  (function loop() {
    ctx.clearRect(0, 0, cv.width, cv.height);
    ps.forEach(p => { p.vy += .35; p.x += p.vx; p.y += p.vy; p.r += .2; ctx.fillStyle = p.c; ctx.save(); ctx.translate(p.x, p.y); ctx.rotate(p.r); ctx.fillRect(-p.s / 2, -p.s / 4, p.s, p.s / 2); ctx.restore(); });
    if (++f < 200) requestAnimationFrame(loop); else ctx.clearRect(0, 0, cv.width, cv.height);
  })();
}

function decor() {
  const d = $('#decor');
  for (let k = 0; k < 14; k++) d.append(h('i', { style: `left:${Math.random() * 100}%;top:${Math.random() * 100}%;animation-delay:-${(Math.random() * 14).toFixed(1)}s` }));
}
function probeFps() {  // slow (software-rendered) view? switch decorative effects off
  if (location.search.includes('still')) document.documentElement.classList.add('still');
  if (location.search.includes('lite')) return document.documentElement.classList.add('lite');
  let n = 0; const t0 = performance.now();
  (function f(t) { n++; if (t - t0 < 1200) requestAnimationFrame(f); else if (n / ((t - t0) / 1000) < 28) document.documentElement.classList.add('lite'); })(t0);
}

/* ---------------------------------------------------------------- wiring */
$('#next').addEventListener('click', () => {
  const s = SCREENS[state.screen];
  if (s === 'done') { api().reboot().then(r => { if (r.dry_run) { $('#dry-note').textContent = 'Dry run: a real install would restart now.'; } }); return; }
  if (!stepValid(s)) { Object.keys(errors()).forEach(k => state.touched[k] = true); showErrors(); return; }
  if (s === 'you') return openConfirm();
  if (s === 'vibe') renderDisks();
  show(state.screen + 1);
});
$('#back').addEventListener('click', () => show(state.screen - 1));
$('#m-cancel').addEventListener('click', closeConfirm);
$('#m-go').addEventListener('click', startInstall);
$('#log-toggle').addEventListener('click', e => { const l = $('#log'); l.classList.toggle('hidden'); e.target.textContent = l.classList.contains('hidden') ? 'Show details' : 'Hide details'; if (!l.classList.contains('hidden')) l.scrollTop = l.scrollHeight; });
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeConfirm(); });

let started = false;
async function init() {
  if (started) return; started = true;
  probeFps(); decor(); renderDots();
  try { state.info = await api().system_info(); } catch (err) { document.body.textContent = 'Failed to start: ' + err; return; }
  state.dry = state.info.dry_run;
  renderWelcome(); renderVibes(); initForm(); showErrors();
  // Dev hook for design review in a plain browser: index.html?mock&screen=disk
  const want = new URLSearchParams(location.search).get('screen'), idx = SCREENS.indexOf(want);
  if (idx > 0) {
    await renderDisks(); state.cfg.disk = '/dev/vda'; renderDisks();
    if (idx >= 4) { onEvent({ type: 'step', label: 'Preparing the disk' }); onEvent({ type: 'step', label: 'Installing Arch Linux and your desktop' }); setProgress(.45); }
    state.screen = idx; show(idx, true);
  } else show(0, true);
}
if (location.search.includes('mock')) init();
else if (window.pywebview && window.pywebview.api) init();
else {
  window.addEventListener('pywebviewready', init);
  setTimeout(() => { if (!started && !window.pywebview) init(); }, 1200);  // plain browser: use the mock
}
})();
