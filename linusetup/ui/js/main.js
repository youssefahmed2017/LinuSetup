/* Boot: wait for the backend, load hardware/disks/defaults, show Welcome. */
'use strict';
(() => {
const { S, h } = LS;
let started = false;

async function boot() {
  if (started) return;
  started = true;
  try {
    S.boot = await LS.call('bootstrap');
  } catch (e) {
    document.querySelector('#view').append(h('div', { class: 'wrap' }, h('div', { class: 'note err' }, 'LinuSetup could not start its backend: ' + e.message)));
    return;
  }
  LS.fx.init(S.boot.effects);
  S.online = S.boot.online;
  S.cfg = LS.clone(S.boot.defaults);
  S.cfg.timezone = LS.guessTimezone();
  LS.renderBadges();
  await LS.loadDisks();
  LS.checkNow();
  LS.go('welcome', { dir: 'up' });
  const dev = S.boot.selftest || location.search.includes('selftest') ? 'selftest' : location.search.includes('shot=') ? 'tour' : null;
  if (dev) {
    const s = document.createElement('script');
    s.src = `js/${dev}.js`;
    document.body.append(s);
  }
}

/* Enter = Continue (outside text areas and dialogs). */
document.addEventListener('keydown', e => {
  if (e.key !== 'Enter' || e.isComposing || document.querySelector('.overlay, .pop')) return;
  if (e.target.closest && e.target.closest('textarea, button, .combo-btn, .toggle')) return;
  const next = document.querySelector('#btn-next');
  if (next && !next.disabled) { e.preventDefault(); next.click(); }
});

/* pywebview serves this page from its own local HTTP server and injects
   window.pywebview; its API is usable only after 'pywebviewready'. The dev
   server has no window.pywebview and answers /api/* itself. */
const bridgeReady = () => window.pywebview && window.pywebview.api && typeof window.pywebview.api.bootstrap === 'function';
if (bridgeReady()) boot();
else {
  window.addEventListener('pywebviewready', boot);
  let waited = 0;
  const t = setInterval(() => {
    waited += 100;
    if (started) return clearInterval(t);
    if (bridgeReady()) { clearInterval(t); boot(); }
    else if (!window.pywebview && waited >= 600) {
      clearInterval(t);
      if (location.protocol === 'file:') document.querySelector('#view').append(h('div', { class: 'wrap' },
        h('div', { class: 'note warn' }, 'Open this page through LinuSetup (python -m linusetup) or the dev server (make preview).')));
      else boot();
    }
  }, 100);
}
})();
