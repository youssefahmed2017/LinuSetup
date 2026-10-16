/* Dev only: drive the UI to one screen for screenshots (?shot=<name>), then
   set document.title = 'READY'. Uses the fixture backend. */
'use strict';
(async () => {
const { S, $ } = LS;
const shot = new URLSearchParams(location.search).get('shot');
const until = async (fn, ms = 10000) => { const t0 = Date.now(); while (Date.now() - t0 < ms) { try { const v = fn(); if (v) return v; } catch (_) {} await LS.sleep(40); } throw new Error('tour timeout'); };
const at = name => until(() => LS.current() && LS.current().name === name && !LS.isBusy() && !LS.$('.screen.out-l, .screen.out-r'));
const click = async sel => { const el = await until(() => { const e = typeof sel === 'string' ? $(sel) : sel(); return e && !e.disabled && e; }); el.click(); await LS.sleep(150); };
const type = async (sel, v) => { const el = await until(() => $(sel)); el.value = v; el.dispatchEvent(new Event('input', { bubbles: true })); await LS.sleep(60); };
const checked = () => until(() => !S.checking && S.check);
const ready = async () => { await LS.sleep(700); document.title = 'READY'; };
await at('welcome');
if (shot === 'welcome') return ready();
if (shot === 'perf') {
  /* Sweep the pointer over the desktop cards for 3 s and record frame times. */
  await click('#btn-next'); await at('mode'); await click('#mode-easy'); await click('#btn-next'); await at('uses');
  await click('#btn-next'); await at('desktop'); await LS.sleep(1200);
  const cards = LS.$$('.card'); const frames = []; let last = performance.now(), run = true;
  (function f(t) { frames.push(t - last); last = t; if (run) requestAnimationFrame(f); })(last);
  const t0 = performance.now(); let i = 0;
  while (performance.now() - t0 < 3000) {
    const c = cards[Math.floor(i / 12) % cards.length], r = c.getBoundingClientRect(), k = (i % 12) / 12;
    c.dispatchEvent(new PointerEvent('pointermove', { bubbles: true, clientX: r.left + r.width * k, clientY: r.top + r.height * (1 - k) }));
    i++; await LS.sleep(8);
    if (i % 40 === 0) LS.checkNow();          // validation round-trips, as when clicking around
  }
  run = false;
  const s = frames.slice(2).sort((a, b) => a - b);
  const res = { frames: s.length, p50: s[Math.floor(s.length * .5)], p95: s[Math.floor(s.length * .95)], max: s[s.length - 1],
    over33: s.filter(x => x > 33).length, fx: LS.fx.tier };
  await fetch('/api/_report', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(res) });
  return ready();
}
await click('#btn-next'); await at('mode');
if (shot === 'mode') { await click('#mode-easy'); return ready(); }
if (['hub', 'sec-disk', 'sec-desktop', 'sec-software', 'sec-users', 'sec-system', 'sec-boot'].includes(shot)) {
  await click('#mode-advanced'); await click('#btn-next'); await at('hub'); await checked();
  if (shot === 'hub') return ready();
  if (shot === 'sec-disk') {
    await click('#tile-disk'); await at('sec-disk');
    await click(() => LS.$('#disk-mode button[data-id="manual"]'));
    await click(() => LS.$$('.chip.click').find(c => c.textContent.includes('/dev/nvme0n1')));
    await click(() => LS.$$('.ptable button').find(b => b.textContent.includes('Delete') && b.closest('tr').textContent.includes('p4')));
    await click('#manual-suggest'); await checked(); await LS.sleep(400); await checked();
    return ready();
  }
  await click('#tile-' + shot.slice(4)); await at(shot);
  if (shot === 'sec-users') { await click('#add-user'); await type('#ud-fullname', 'Alex Kim'); await type('#ud-username', 'alex'); await type('#ud-password', 'Secret-123!'); }
  return ready();
}
await click('#mode-easy'); await click('#btn-next'); await at('uses');
await click('#use-gaming');
if (shot === 'uses') return ready();
await click('#btn-next'); await at('desktop');
if (shot === 'desktop') return ready();
await click('#btn-next'); await at('disk');
await click('.disk[data-path="/dev/nvme0n1"]');
await click('#scope-shrink'); await until(() => $('#shrink-slider'));
await checked(); await LS.sleep(500); await checked();
if (shot === 'disk') return ready();
await click('#scope-free');
await click('#btn-next'); await at('you');
await type('#fullname', 'Sam Rivera'); await type('#password', 'Correct-Horse-9'); await type('#password2', 'Correct-Horse-9');
await checked(); await LS.sleep(300);
if (shot === 'you') return ready();
await click('#btn-next'); await at('review'); await checked(); await LS.sleep(400);
if (shot === 'review') return ready();
await click('#btn-next'); await type('#confirm-word', 'nvme0n1');
if (shot === 'confirm') return ready();
await click('#confirm-go'); await at('install');
if (shot === 'install') { await until(() => parseInt($('#pct').textContent) >= 35, 60000); $('#log-toggle').click(); return ready(); }
await at('done', 120000);
await LS.sleep(1500);
return ready();
})();
