/* In-page end-to-end test (dev only). Loaded with ?selftest or when the GUI
   runs with LINUSETUP_SELFTEST=1. Drives the real UI with real clicks against
   the fixture backend and reports results to the backend. */
'use strict';
(async () => {
const { S, $ } = LS;
const T = { size: `${innerWidth}x${innerHeight}`, ua: navigator.userAgent, results: [], errors: [], layout: [] };
window.addEventListener('error', e => T.errors.push(String(e.message) + ' @' + (e.filename || '').split('/').pop() + ':' + e.lineno));
window.addEventListener('unhandledrejection', e => T.errors.push('unhandled: ' + ((e.reason && e.reason.message) || e.reason)));
const origErr = console.error;
console.error = (...a) => { T.errors.push('console: ' + a.map(String).join(' ')); origErr(...a); };

const until = async (fn, ms = 8000, what = '') => {
  const t0 = Date.now();
  while (Date.now() - t0 < ms) {
    try { const v = fn(); if (v) return v; } catch (_) {}
    await LS.sleep(40);
  }
  throw new Error('timed out waiting for ' + what);
};
const q = sel => typeof sel === 'string' ? $(sel) : sel();
const click = async (sel, what) => {
  const el = await until(() => { const e = q(sel); return e && !e.disabled && e; }, 8000, 'clickable ' + (what || sel));
  const r = el.getBoundingClientRect();
  el.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true, clientX: r.left + 5, clientY: r.top + 5 }));
  el.click();
  await LS.sleep(120);
};
const type = async (sel, text) => {
  const el = await until(() => q(sel), 5000, 'input ' + sel);
  el.focus(); el.value = text; el.dispatchEvent(new Event('input', { bubbles: true }));
  await LS.sleep(60);
};
const settled = () => !LS.$('.screen.out-l, .screen.out-r') && !LS.isBusy();
const onScreen = (name, ms = 8000) => until(() => LS.current() && LS.current().name === name && settled(), ms, 'screen ' + name);
const checked = () => until(() => !S.checking && S.check, 8000, 'validation');
const assert = (cond, msg) => { if (!cond) throw new Error('assert: ' + msg); };
const layout = name => {
  const scr = LS.current() && LS.current().el;
  if (!scr) return;
  if (scr.scrollWidth > scr.clientWidth + 2) T.layout.push({ screen: name, problem: `content wider than screen (${scr.scrollWidth} > ${scr.clientWidth})` });
  LS.$$('.wrap > *', scr).forEach(e => { const r = e.getBoundingClientRect(); if (r.right > innerWidth + 1) T.layout.push({ screen: name, problem: `${e.className || e.tagName} overflows right by ${Math.round(r.right - innerWidth)}px` }); });
  const nb = $('#btn-next'); if (nb) { const r = nb.getBoundingClientRect(); if (r.bottom > innerHeight + 1 || r.right > innerWidth + 1) T.layout.push({ screen: name, problem: 'Continue button is off-screen' }); }
  if (getComputedStyle(scr).overflowY !== 'auto') T.layout.push({ screen: name, problem: 'screen does not scroll' });
};
const step = async (name, fn) => {
  const t0 = Date.now();
  try { await fn(); T.results.push({ name, ok: true, ms: Date.now() - t0 }); return true; }
  catch (e) { T.results.push({ name, ok: false, error: String((e && e.message) || e), screen: LS.current() && LS.current().name }); return false; }
};
const closeDialogs = () => LS.$$('.overlay').forEach(o => o.remove());

await onScreen('welcome', 15000).catch(() => {});

// ------------------------------------------------------------------ Easy
const easy = await step('easy: welcome → mode', async () => {
  layout('welcome');
  await click('#btn-next'); await onScreen('mode'); layout('mode');
  await click('#mode-easy'); await click('#btn-next'); await onScreen('uses'); layout('uses');
}) && await step('easy: use cases', async () => {
  await click('#use-gaming');
  assert(S.cfg.software.includes('steam'), 'gaming adds steam');
  await click('#use-gaming'); assert(!S.cfg.software.includes('steam'), 'unselect removes steam');
  await click('#use-gaming');
}) && await step('double-click does not skip a screen', async () => {
  const b = $('#btn-next'); b.click(); b.click(); b.click();
  await LS.sleep(700);
  assert(LS.current().name === 'desktop', 'expected desktop, got ' + LS.current().name);
  layout('desktop');
}) && await step('quick back/forward keeps one live screen', async () => {
  $('#btn-back').click(); await LS.sleep(30); $('#btn-next') && $('#btn-next').click();
  await LS.sleep(700);
  assert(LS.$$('.screen').length === 1, 'screens in DOM: ' + LS.$$('.screen').length);
  if (LS.current().name !== 'desktop') { await onScreen(LS.current().name); if (LS.current().name === 'uses') { await click('#btn-next'); await onScreen('desktop'); } }
}) && await step('easy: desktop', async () => {
  await click('#de-gnome'); assert(S.cfg.profiles[0] === 'gnome', 'gnome chosen');
  await click('#btn-next'); await onScreen('disk'); layout('disk');
}) && await step('easy: disk alongside Windows + encryption', async () => {
  await click('.disk[data-path="/dev/nvme0n1"]');
  await click('#scope-shrink');
  await until(() => $('#shrink-slider'), 5000, 'shrink slider');
  await click('#scope-free');
  await click('#tg-encrypt');
  await type('#luks-pw', 'luks-pass-123');
  await LS.sleep(300);
  assert($('#btn-next').disabled, 'next disabled until passphrase repeated');
  await type('#luks-pw2', 'luks-pass-123');
  await checked(); await LS.sleep(300);
  assert(!LS.issues('disk').length, 'disk errors: ' + JSON.stringify(LS.issues('disk')));
  assert(S.check.preview['/dev/nvme0n1'], 'after-bar preview');
  layout('disk');
  await click('#btn-next'); await onScreen('you'); layout('you');
}) && await step('easy: account', async () => {
  await type('#fullname', 'Sam Rivera');
  assert($('#username').value === 'sam', 'username suggested: ' + $('#username').value);
  assert(S.cfg.hostname === 'sam-pc', 'hostname suggested: ' + S.cfg.hostname);
  await type('#password', 'pw-123456');
  await type('#password2', 'pw-12345');
  await checked(); await LS.sleep(250);
  assert($('#btn-next').disabled, 'mismatched passwords block Continue');
  await type('#password2', 'pw-123456');
  await checked(); await LS.sleep(300);
  await click('#btn-next'); await onScreen('review'); layout('review');
}) && await step('easy: review + commands + install', async () => {
  await checked(); await LS.sleep(300);
  assert(!S.check.errors.length, 'review errors: ' + JSON.stringify(S.check.errors));
  await click('#show-cmds'); await until(() => $('.overlay .cmds'), 5000, 'commands dialog');
  assert(!$('.overlay .cmds').textContent.includes('pw-123456'), 'password not shown');
  closeDialogs();
  await click('#btn-next');
  await until(() => $('#confirm-word'), 4000, 'confirm dialog');
  assert($('#confirm-go').disabled, 'confirm disabled before typing');
  await type('#confirm-word', 'nvme0n1');
  await click('#confirm-go');
  await onScreen('install', 10000); layout('install');
  await until(() => LS.$$('.stp').length > 5, 5000, 'step list');
  await onScreen('done', 90000); layout('done');
});

// ------------------------------------------------------------------ Advanced
const startAdvanced = async () => {
  closeDialogs();
  S.cfg = LS.clone(S.boot.defaults); S.mode = 'advanced'; S.luks2 = null;
  LS.resetHistory(['welcome', 'mode']);
  LS.go('hub', { force: true }); await onScreen('hub'); await checked();
};
const adv = await step('advanced: every section opens', async () => {
  await startAdvanced(); layout('hub');
  for (const id of ['disk', 'desktop', 'users', 'software', 'locale', 'boot', 'mirrors', 'network', 'system']) {
    await click('#tile-' + id, 'tile ' + id); await onScreen('sec-' + id); layout('sec-' + id);
    await click('#btn-next'); await onScreen('hub');
  }
}) && await step('advanced: add a user', async () => {
  await click('#tile-users'); await onScreen('sec-users');
  await click('#add-user'); await type('#ud-username', 'alex'); await type('#ud-password', 'secret-12'); await type('#ud-password2', 'secret-12');
  await click('#ud-ok');
  assert(S.cfg.users.length === 1 && S.cfg.users[0].username === 'alex' && S.cfg.users[0].sudo, 'user added as admin');
  await click('#btn-next'); await onScreen('hub');
}) && await step('advanced: manual partitioning', async () => {
  await click('#tile-disk'); await onScreen('sec-disk');
  await click(() => LS.$('#disk-mode button[data-id="manual"]'), 'manual tab');
  await click(() => LS.$$('.chip.click').find(c => c.textContent.includes('/dev/sda ')), 'disk chip sda');
  await click('#manual-wipe');
  await click('#manual-suggest');
  assert(S.cfg.disk.manual.new.length === 2, 'suggested 2 partitions: ' + JSON.stringify(S.cfg.disk.manual.new));
  await checked(); await LS.sleep(300); await checked();
  assert(!LS.issues('disk').length, 'manual errors: ' + JSON.stringify(LS.issues('disk')));
  assert(S.check.preview['/dev/sda'], 'manual preview');
  // edit the root partition: add a separate /home by shrinking root
  const root = S.cfg.disk.manual.new.find(n => n.mount === '/');
  LS.set(c => { const r = c.disk.manual.new.find(n => n.mount === '/'); r.size_mib = 60 * 1024; });
  LS.current() && LS.go('sec-disk', { force: true, replace: true }); await onScreen('sec-disk');
  await click(() => LS.$$('button[data-free]').slice(-1)[0], 'new partition in free space');
  await until(() => $('#np-mount'), 4000, 'new partition dialog');
  await type('#np-mount', '/home');
  await click('#np-ok');
  assert(S.cfg.disk.manual.new.some(n => n.mount === '/home'), '/home added');
  await checked(); await LS.sleep(300); await checked();
  assert(!LS.issues('disk').length, 'manual errors after /home: ' + JSON.stringify(LS.issues('disk')));
  layout('sec-disk');
  await click('#btn-next'); await onScreen('hub');
}) && await step('advanced: desktop + software search', async () => {
  await click('#tile-desktop'); await onScreen('sec-desktop');
  await click('#pf-sway'); assert(S.cfg.profiles.includes('sway'), 'sway added');
  const before = S.cfg.profiles.slice();
  await click('#pf-minimal');
  await until(() => $('#pf-confirm'), 4000, '"no desktop" confirmation');
  assert(JSON.stringify(S.cfg.profiles) === JSON.stringify(before), 'desktop kept until confirmed');
  await click(() => LS.$$('.overlay .btn').find(b => b.textContent.includes('Keep my desktop')), 'keep desktop');
  assert(JSON.stringify(S.cfg.profiles) === JSON.stringify(before), 'desktop still selected after "Keep"');
  await click('#btn-next'); await onScreen('hub');
  await click('#tile-software'); await onScreen('sec-software');
  await type('#pkg-search', 'htop');
  await click(() => LS.$$('.act button').find(b => b.textContent.includes('Add')), 'add htop');
  assert(S.cfg.extra_packages.includes('htop'), 'htop added');
  await click('#btn-next'); await onScreen('hub');
}) && await step('advanced: review + dry install', async () => {
  await checked(); await LS.sleep(300);
  await click('#btn-next'); await onScreen('review'); await checked(); await LS.sleep(300);
  assert(!S.check.errors.length, 'errors: ' + JSON.stringify(S.check.errors));
  await click('#btn-next'); await until(() => $('#confirm-word'), 4000, 'confirm');
  await type('#confirm-word', 'sda'); await click('#confirm-go');
  await onScreen('install', 10000); await onScreen('done', 90000);
});

T.fx = LS.fx.tier;
T.passed = T.results.filter(r => r.ok).length;
T.failed = T.results.filter(r => !r.ok).length;
console.log('SELFTEST', JSON.stringify(T));
try {
  if (window.pywebview && window.pywebview.api) await LS.call('selftest_report', T);
  else await fetch('/api/_report', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(T) });
} catch (e) { origErr(e); }
})();
