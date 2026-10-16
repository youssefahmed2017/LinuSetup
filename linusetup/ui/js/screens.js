/* Welcome, mode, the Easy flow, Review, Install and Done. */
'use strict';
(() => {
const { h, icon, w: W, S, $ } = LS;
const GiB = 1024 ** 3;
LS.EASY_STEPS = 7;

LS.USES = {
  everyday: { title: 'Everyday', icon: 'briefcase', desc: 'Browser, office, email, media and printing',
    software: ['firefox', 'libreoffice', 'thunderbird', 'vlc', 'codecs', 'archive', 'filesystems', 'fonts'] },
  gaming: { title: 'Gaming', icon: 'gaming', desc: 'Steam with Proton, Lutris, Wine and GPU drivers',
    software: ['steam', 'gamemode', 'mangohud', 'lutris', 'wine'] },
  coding: { title: 'Coding', icon: 'code', desc: 'VS Code, Git, Docker, Python, Node and Neovim',
    software: ['devtools', 'vscode', 'docker', 'python', 'node', 'neovim'] },
  creating: { title: 'Creating', icon: 'palette', desc: 'GIMP, Krita, Inkscape, Blender, Kdenlive, OBS',
    software: ['gimp', 'krita', 'inkscape', 'blender', 'kdenlive', 'obs', 'audacity'] },
};
const EASY_DESKTOPS = ['kde', 'gnome', 'cinnamon', 'xfce', 'cosmic', 'hyprland'];
const DESKTOP_ICON = { kde: 'sparkles', gnome: 'globe', cinnamon: 'monitor', xfce: 'zap', cosmic: 'rocket', hyprland: 'layers' };

LS.applyUses = function applyUses() {
  const sw = new Set(['firefox', 'archive', 'filesystems']);
  S.uses.forEach(u => LS.USES[u].software.forEach(s => sw.add(s)));
  LS.set(c => { c.software = [...sw]; c.printing = S.uses.includes('everyday'); });
};

LS.guessTimezone = function guessTimezone() {
  try { const z = Intl.DateTimeFormat().resolvedOptions().timeZone; if (S.boot.timezones.includes(z)) return z; } catch (_) {}
  return 'UTC';
};
const slug = s => s.toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/[^a-z0-9]+/g, '').slice(0, 24);
const profileName = id => (S.boot.catalog.profiles.find(p => p.id === id) || { name: id }).name;

/* ================================================================ welcome */
LS.screens.welcome = {
  center: true, step: 0,
  render(el, ctx) {
    const hw = S.boot.hardware;
    el.classList.add('center-text');
    el.append(
      h('div', { class: 'hero-mark st' }, icon('logo')),
      h('h1', { class: 'st' }, 'Arch Linux, ', h('span', { class: 'grad' }, 'minus the pain.')),
      h('p', { class: 'lead st' }, 'Answer a few questions, or take full control of every option. Then go touch grass while LinuSetup installs everything.'));
    const checks = h('div', { class: 'checks' });
    const chk = (kind, ic, title, sub, extra) => h('div', { class: 'chk st ' + kind }, h('div', { class: 'ci' }, icon(ic)), h('div', {}, h('b', {}, title), h('small', {}, sub)), extra || null);
    const draw = () => {
      checks.textContent = '';
      const usable = S.disks.filter(d => d.usable);
      const gpus = hw.gpus.map(g => g.name).join(', ') || (hw.virt ? 'Virtual display' : 'Basic display');
      checks.append(
        chk('', 'zap', hw.uefi ? 'UEFI firmware' : 'Legacy BIOS', hw.uefi ? 'Modern boot' : 'GRUB will be used'),
        chk(S.online ? '' : 'bad', 'wifi', S.online ? 'Connected' : 'No internet', S.online ? 'Ready to download' : 'Needed to install',
          !S.online && hw.wifi.length ? h('button', { class: 'btn sm', id: 'wifi-btn', onclick: LS.wifiDialog }, 'Wi-Fi') : null),
        chk(hw.ram_gb >= 2 ? '' : 'warn', 'cpu', `${hw.ram_gb} GB memory`, hw.cpu_model || 'Processor detected'),
        chk('', 'monitor', 'Graphics', gpus),
        chk(usable.length ? '' : 'bad', 'disk', `${usable.length} usable disk${usable.length === 1 ? '' : 's'}`, usable.length ? usable.map(d => LS.gb(d.size)).join(' + ') : 'Add a disk to install to'));
      LS.stagger(checks);
    };
    draw();
    el.append(checks);
    ctx.on('online', draw);
    if (!S.online) ctx.every(5000, LS.refreshOnline);
  },
  footer: () => ({ next: { label: "Let's go", action: () => LS.go('mode'), disabled: () => !S.disks.some(d => d.usable) } }),
};

LS.refreshOnline = async function refreshOnline() {
  const n = await LS.call('network');
  if (n.online !== S.online) { S.online = n.online; LS.renderBadges(); LS.emit('online'); LS.checkNow(); }
};

/* ================================================================ mode */
LS.screens.mode = {
  center: true, step: 1,
  render(el, ctx) {
    el.classList.add('center-text');
    el.append(h('h1', { class: 'st' }, 'How do you want to ', h('span', { class: 'grad' }, 'install?')),
      h('p', { class: 'lead st' }, 'You can switch at any time before installing. Both end in the same review screen.'));
    const easy = W.card({ icon: 'sparkles', title: 'Easy', id: 'mode-easy', tag: 'Recommended', center: true, sel: S.mode === 'easy',
      desc: 'Four friendly questions. Sensible, modern defaults for everything else.', onClick: () => pick('easy') });
    const adv = W.card({ icon: 'wrench', title: 'Advanced', id: 'mode-advanced', center: true, sel: S.mode === 'advanced',
      desc: 'Every archinstall option and more: partitions, encryption, kernels, mirrors, boot loaders.', onClick: () => pick('advanced') });
    function pick(m) { S.mode = m; easy.set(m === 'easy'); adv.set(m === 'advanced'); LS.refreshFooter(); }
    el.append(h('div', { class: 'cards two', style: { maxWidth: '720px', margin: '0 auto', width: '100%' } }, easy, adv),
      h('div', { class: 'row st', style: { justifyContent: 'center', marginTop: '22px' } },
        h('button', { class: 'btn ghost sm', id: 'load-config', onclick: LS.loadConfigDialog }, icon('upload'), 'Load a saved config')));
  },
  footer: () => ({ back: {}, next: { label: 'Continue', action: () => {
    if (S.mode === 'easy') { LS.applyUses(); LS.go('uses'); } else LS.go('hub');
  } } }),
};

/* ================================================================ easy: uses */
LS.screens.uses = {
  step: 2,
  render(el, ctx) {
    el.append(h('div', { class: 'center-text' }, h('h1', { class: 'st' }, 'What will you ', h('span', { class: 'grad' }, 'use it for?')),
      h('p', { class: 'lead st' }, 'Pick any that fit. Right-click a card to see exactly what it installs.')));
    const grid = h('div', { class: 'cards' });
    Object.entries(LS.USES).forEach(([id, u]) => {
      const c = W.card({ icon: u.icon, title: u.title, desc: u.desc, center: true, id: 'use-' + id, sel: S.uses.includes(id),
        onClick: () => { S.uses = S.uses.includes(id) ? S.uses.filter(x => x !== id) : [...S.uses, id]; c.set(S.uses.includes(id)); LS.applyUses(); } });
      c.addEventListener('contextmenu', e => { e.preventDefault(); LS.packagesDialog(u.title, u.software); });
      grid.append(c);
    });
    el.append(grid, h('p', { class: 'mut small center-text st', style: { marginTop: '18px' } },
      'A desktop, web browser, sound, Bluetooth and Wi-Fi are always included.'));
  },
  footer: () => ({ back: {}, next: { action: () => LS.go('desktop') } }),
};

LS.packagesDialog = function packagesDialog(title, ids) {
  const items = S.boot.catalog.software.flatMap(c => c.items).filter(i => ids.includes(i.id));
  LS.dialog({ title, lead: 'Installed when this is selected:',
    body: h('div', { class: 'stack' }, items.map(i => h('div', { class: 'act' }, icon('package'), h('div', { class: 'grow' }, h('b', {}, i.name), ' ', h('span', { class: 'mut small' }, i.desc)), h('span', { class: 'mono small mut' }, i.packages.join(' '))))),
    actions: [{ label: 'Close' }] });
};

/* ================================================================ easy: desktop */
LS.screens.desktop = {
  step: 3,
  render(el) {
    el.append(h('div', { class: 'center-text' }, h('h1', { class: 'st' }, 'Choose your ', h('span', { class: 'grad' }, 'desktop')),
      h('p', { class: 'lead st' }, 'This is what you will see every day. You can install others later.')));
    const grid = h('div', { class: 'cards' });
    const cards = {};
    EASY_DESKTOPS.forEach(id => {
      const p = S.boot.catalog.profiles.find(x => x.id === id);
      cards[id] = W.card({ icon: DESKTOP_ICON[id], title: p.name, desc: p.blurb, id: 'de-' + id,
        sel: S.cfg.profiles[0] === id, onClick: () => { LS.set(c => { c.profiles = [id]; c.greeter = 'auto'; }); Object.entries(cards).forEach(([k, v]) => v.set(k === id)); } });
      grid.append(cards[id]);
    });
    el.append(grid, h('p', { class: 'mut small center-text st', style: { marginTop: '18px' } },
      'Looking for i3, Sway, bspwm, MATE or a server? They are in Advanced mode.'));
  },
  footer: () => ({ back: {}, next: { action: async () => { await LS.loadDisks(); LS.go('disk'); } } }),
};

/* ================================================================ easy: disk */
LS.screens.disk = {
  step: 4,
  render(el, ctx) {
    el.append(h('h1', { class: 'st' }, 'Where should it ', h('span', { class: 'grad' }, 'live?')),
      h('p', { class: 'lead st' }, 'Pick a disk, then how to use it. Nothing is changed until you confirm on the last screen.'));
    const notes = LS.notes('disk');
    const list = h('div', { class: 'disklist' });
    const how = h('div');
    const after = h('div');
    el.append(list, how, after, notes);
    const drawList = () => {
      list.textContent = '';
      S.disks.forEach(d => list.append(W.diskCard(d, { sel: S.cfg.disk.device === d.path, onClick: pickDisk })));
      LS.stagger(list);
    };
    const pickDisk = d => {
      LS.set(c => { c.disk.mode = 'guided'; c.disk.device = d.path; c.disk.scope = 'wipe'; c.disk.shrink = { partition: '', free_gb: 0 }; });
      drawList(); drawHow();
    };
    const drawHow = () => {
      how.textContent = '';
      const d = LS.disk(S.cfg.disk.device);
      if (!d) return;
      const g = S.cfg.disk, enc = LS.encryptionUI();
      how.append(h('h3', { style: { marginTop: '24px' } }, 'How should Arch use this disk?'), LS.scopeChoices(d, drawHow),
        h('div', { class: 'grid2', style: { marginTop: '14px' } }, enc.toggle,
          W.toggle({ title: 'System snapshots', desc: 'Btrfs + Snapper: undo a bad update in seconds', value: g.fs === 'btrfs' && g.btrfs.snapshots, id: 'tg-snap',
            onChange: v => LS.set(c => { c.disk.fs = v ? 'btrfs' : 'ext4'; c.disk.btrfs.snapshots = v; }) })),
        enc.fields);
      LS.stagger(how);
    };
    const drawAfter = () => {
      after.textContent = '';
      const pv = S.check && S.check.preview && S.check.preview[S.cfg.disk.device];
      if (pv) after.append(LS.afterBar(pv));
    };
    drawList(); drawHow(); drawAfter();
    ctx.on('checked', () => { drawAfter(); notes._draw(); LS.refreshFooter(); });
  },
  footer: () => ({ back: {}, next: { action: () => LS.go('you'),
    disabled: () => !S.cfg.disk.device || S.checking || LS.issues('disk').length > 0 || !LS.encryptionOk() } }),
};

LS.afterBar = function afterBar(pv) {
  return h('div', {}, h('div', { class: 'barlabel' }, 'After installing'),
    W.diskBar(pv.size, pv.partitions.map(p => ({ start: p.start, size: p.size,
      kind: p.new ? (p.encrypt ? 'luks' : p.fs === 'vfat' ? 'esp' : p.fs === 'swap' ? 'swap' : p.fs === 'bios_grub' ? 'bios' : 'new') : p.kind,
      label: p.new ? (p.mount === '/' ? 'Arch Linux' : p.mount === '[SWAP]' ? 'Swap' : p.mount || p.label) : (p.label || W.KIND_LABEL[p.kind]) }))),
    W.legend(['new', ...pv.partitions.filter(p => !p.new).map(p => p.kind)]));
};

LS.encryptionOk = () => !S.cfg.disk.encryption.enabled || (!!S.cfg.disk.encryption.passphrase && S.luks2 === S.cfg.disk.encryption.passphrase);
LS.encryptionUI = function encryptionUI() {
  const enc = S.cfg.disk.encryption;
  if (S.luks2 == null) S.luks2 = enc.passphrase;
  const check = () => { f2.error(S.luks2 && S.luks2 !== S.cfg.disk.encryption.passphrase ? 'Passphrases don\'t match' : ''); LS.refreshFooter(); };
  const f2 = W.field('Repeat passphrase', W.password({ id: 'luks-pw2', value: S.luks2, onInput: v => { S.luks2 = v; check(); } }));
  const fields = h('div', { class: 'grid2' + (enc.enabled ? '' : ' hidden'), style: { marginTop: '12px' } },
    W.field('Passphrase (asked at every boot)', W.password({ value: enc.passphrase, id: 'luks-pw', meter: true,
      onInput: v => { LS.set(c => { c.disk.encryption.passphrase = v; }); check(); } })), f2);
  const toggle = W.toggle({ title: 'Encrypt the disk', desc: 'LUKS2. Protects your files if the computer is lost or stolen', value: enc.enabled, id: 'tg-encrypt',
    onChange: v => { LS.set(c => { c.disk.encryption.enabled = v; }); fields.classList.toggle('hidden', !v); LS.refreshFooter(); } });
  return { toggle, fields };
};

/* Erase / use free space / shrink Windows, for the guided disk setup. */
LS.scopeChoices = function scopeChoices(d, redraw) {
      const g = S.cfg.disk;
      const biggest = d.free.reduce((m, f) => Math.max(m, f.size), 0);
      const canFree = d.pttype === 'gpt' && biggest >= 20 * 1e9;
      const ntfs = d.partitions.filter(p => p.kind === 'windows').sort((a, b) => b.size - a.size)[0];
      const bitlocker = d.partitions.some(p => p.kind === 'bitlocker');
      const other = d.has_windows ? 'Windows' : 'what is already there';
      const choices = h('div', { class: 'choices' });
      const set = scope => { LS.set(c => { c.disk.scope = scope; if (scope === 'shrink' && ntfs) c.disk.shrink.partition = ntfs.node; }); redraw(); };
      choices.append(W.choice({ id: 'scope-wipe', title: `Erase ${d.model} and install`, sel: g.scope === 'wipe',
        desc: d.partitions.length ? `Everything on this disk (${d.partitions.length} partitions) will be deleted.` : 'The disk is empty. Perfect.', onClick: () => set('wipe') }));
      if (d.partitions.length) {
        choices.append(W.choice({ id: 'scope-free', title: `Install alongside ${other}`, sel: g.scope === 'free', off: !canFree,
          desc: canFree ? `Use the ${LS.gb(biggest)} of free space. Existing partitions are not touched.` : (d.pttype !== 'gpt' ? 'Only possible on GPT disks.' : 'Not enough free space (needs 20 GB).'),
          onClick: () => set('free') }));
      }
      if (ntfs && d.pttype === 'gpt') {
        const info = S.ntfs[ntfs.node];
        let extra = null;
        if (g.scope === 'shrink') {
          if (!info) extra = h('div', { class: 'row mut' }, h('span', { class: 'spin' }), 'Checking how much Windows can give up…');
          else if (!info.ok) extra = W.note('err', 'Windows can\'t be shrunk right now: ' + info.error + ' Boot Windows, turn off Fast Startup, shut down fully and try again.');
          else {
            const max = Math.floor((ntfs.size - info.min_bytes - 2 * GiB) / GiB);
            if (max < 20) extra = W.note('err', 'Windows doesn\'t have enough free space to give 20 GB to Arch.');
            else {
              const val = Math.min(Math.max(g.shrink.free_gb || Math.min(80, max), 20), max);
              if (g.shrink.free_gb !== val) LS.set(c => { c.disk.shrink.free_gb = val; });
              const keep = h('span', { class: 'small mut' }, `Windows keeps ${Math.floor(ntfs.size / GiB) - val} GB`);
              extra = h('div', { class: 'stack' }, W.slider({ min: 20, max, value: val, id: 'shrink-slider', format: v => `${v} GB for Arch`,
                onInput: v => { LS.set(c => { c.disk.shrink.free_gb = v; }); keep.textContent = `Windows keeps ${Math.floor(ntfs.size / GiB) - v} GB`; } }), keep);
            }
          }
        }
        choices.append(W.choice({ id: 'scope-shrink', title: 'Make room by shrinking Windows', sel: g.scope === 'shrink', extra,
          desc: `Take space from ${ntfs.node} (${LS.gb(ntfs.size)}). Back up first; resizing always carries some risk.`,
          onClick: async () => { set('shrink'); if (!S.ntfs[ntfs.node]) { S.ntfs[ntfs.node] = await LS.call('ntfs_info', ntfs.node); redraw(); } } }));
      } else if (bitlocker) {
        choices.append(W.note('info', 'Windows on this disk uses BitLocker, so LinuSetup can\'t shrink it. Shrink it from Windows (Disk Management) to make free space, or use another disk.'));
      }
      return choices;
};

/* ================================================================ easy: you */
LS.screens.you = {
  step: 5,
  render(el, ctx) {
    if (!S.cfg.users.length) S.cfg.users.push(Object.assign(LS.clone(S.boot.default_user), { sudo: true }));
    const u = S.cfg.users[0];
    let userEdited = !!u.username, hostEdited = S.cfg.hostname !== 'archlinux';
    el.append(h('h1', { class: 'st' }, 'Now, ', h('span', { class: 'grad' }, 'who are you?')),
      h('p', { class: 'lead st' }, 'This creates your account. It can do administrator tasks with your password (sudo).'));
    const fUser = W.field('Username', W.input({ value: u.username, id: 'username', placeholder: 'sam', onInput: v => { userEdited = true; setUser(v); } }));
    const fPw2 = W.field('Repeat password', W.password({ id: 'password2', value: u.password, onInput: v => { S.pw2 = v; local(); } }));
    const fHost = W.field('Computer name', W.input({ value: S.cfg.hostname, id: 'hostname', onInput: v => { hostEdited = true; LS.set(c => { c.hostname = v.trim(); }); local(); } }));
    S.pw2 = u.password;
    const setUser = v => { LS.set(c => { c.users[0].username = v.trim(); if (!hostEdited) c.hostname = (slug(v) || 'arch') + '-pc'; }); if (!hostEdited) $('#hostname').value = S.cfg.hostname; local(); };
    const form = h('div', { class: 'form st' },
      W.field('Your name', W.input({ value: u.fullname, id: 'fullname', placeholder: 'Sam Rivera', onInput: v => {
        LS.set(c => { c.users[0].fullname = v; });
        if (!userEdited) { const s = slug(v.split(' ')[0] || ''); $('#username').value = s; setUser(s); }
      } })),
      fUser,
      W.field('Password', W.password({ id: 'password', value: u.password, meter: true, onInput: v => { LS.set(c => { c.users[0].password = v; }); local(); } })),
      fPw2, fHost,
      W.field('Keyboard layout', W.combo({ id: 'keyboard', value: S.cfg.locale.keyboard, options: S.boot.catalog.keyboards.map(k => ({ id: k.id, label: k.label })),
        onChange: v => LS.set(c => { c.locale.keyboard = v; }) })),
      W.field('Timezone', W.combo({ id: 'timezone', value: S.cfg.timezone, options: S.boot.timezones.map(z => ({ id: z, label: z.replace(/_/g, ' ') })),
        onChange: v => LS.set(c => { c.timezone = v; }) })),
      W.field('Language', W.combo({ id: 'language', value: S.cfg.locale.language, options: S.boot.catalog.locales.map(l => ({ id: l, label: l })),
        onChange: v => LS.set(c => { c.locale.language = v; }) })),
      h('div', { class: 'wide' }, W.toggle({ title: 'Log in automatically', desc: 'Skip the login screen on this computer', value: u.autologin, id: 'tg-autologin',
        onChange: v => LS.set(c => { c.users[0].autologin = v; }) })));
    el.append(form);
    const local = () => {
      const c = S.cfg, uu = c.users[0];
      fUser.error(uu.username && !/^[a-z_][a-z0-9_-]{0,31}$/.test(uu.username) ? 'Lowercase letters, digits, - and _ only' : '');
      fPw2.error(S.pw2 && S.pw2 !== uu.password ? 'Passwords don\'t match' : '');
      fHost.error(c.hostname && !/^[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$/.test(c.hostname) ? 'Letters, digits and dashes' : '');
      LS.refreshFooter();
    };
    const notes = LS.notes('users'); el.append(notes);
    ctx.on('checked', () => { notes._draw(); LS.refreshFooter(); });
    local();
  },
  footer: () => ({ back: {}, next: { label: 'Review', action: () => LS.go('review'), disabled: () => {
    const u = S.cfg.users[0];
    return !u || !u.username || !u.password || S.pw2 !== u.password || S.checking || LS.issues('users').length > 0 || LS.issues('system').length > 0;
  } } }),
};

/* ================================================================ review */
const EDIT = {
  easy: { disk: 'disk', users: 'you', locale: 'you', desktop: 'desktop', software: 'uses', system: 'you', boot: 'disk' },
};
LS.editSection = sec => {
  if (S.mode === 'easy' && EDIT.easy[sec]) return LS.go(EDIT.easy[sec], { dir: 'l' });
  S.mode = 'advanced'; LS.go('sec-' + sec, { dir: 'l' });
};
LS.screens.review = {
  step: 6,
  crumb: () => ['Advanced', 'Review'],
  render(el, ctx) {
    el.append(h('h1', { class: 'st' }, 'Ready ', h('span', { class: 'grad' }, 'when you are.')),
      h('p', { class: 'lead st' }, 'Check everything once more. Click any card to change it.'));
    const body = h('div');
    el.append(body);
    const draw = () => {
      body.textContent = '';
      const ch = S.check || {}, c = S.cfg, cat = S.boot.catalog;
      if (S.checking && !S.check) { body.append(h('div', { class: 'skel', style: { height: '200px' } })); return; }
      (ch.errors || []).forEach(e => body.append(h('div', { class: 'note err st' }, icon('warn'), h('div', { class: 'grow' }, e.message), h('button', { class: 'linkbtn', onclick: () => LS.editSection(e.section) }, 'Fix'))));
      (ch.warnings || []).forEach(e => body.append(h('div', { class: 'note warn st' }, icon('info'), e.message)));
      const card = (sec, ic, title, rows) => {
        const el = h('div', { class: 'sumcard st', style: { cursor: 'pointer' }, onclick: () => LS.editSection(sec) },
          h('div', { class: 'sh' }, icon(ic), h('b', {}, title), h('span', { class: 'linkbtn small' }, 'Edit')),
          h('dl', {}, rows.filter(r => r && r[1] !== '' && r[1] != null).flatMap(([k, v]) => [h('dt', {}, k), h('dd', {}, v)])));
        return el;
      };
      const d = LS.disk(c.disk.device);
      const sw = cat.software.flatMap(x => x.items).filter(i => c.software.includes(i.id)).map(i => i.name);
      const kb = cat.keyboards.find(k => k.id === c.locale.keyboard);
      body.append(h('div', { class: 'sumgrid', style: { marginTop: '16px' } },
        card('disk', 'disk', 'Disk', [
          ['Disk', c.disk.mode === 'manual' ? 'Manual partitioning' : d ? `${d.model} (${d.path})` : '—'],
          c.disk.mode === 'guided' ? ['How', { wipe: 'Erase the whole disk', free: 'Use free space', shrink: `Shrink Windows by ${c.disk.shrink.free_gb} GB` }[c.disk.scope]] : null,
          ['Filesystem', c.disk.mode === 'guided' ? c.disk.fs + (c.disk.fs === 'btrfs' && c.disk.btrfs.snapshots ? ' + snapshots' : '') : 'as set per partition'],
          ['Encryption', (c.disk.mode === 'guided' ? c.disk.encryption.enabled : [...c.disk.manual.new, ...c.disk.manual.existing].some(x => x.encrypt)) ? 'On (LUKS2)' : 'Off'],
          ['Swap', c.swap.mode === 'none' ? 'None' : `${c.swap.mode} · ${c.swap.size_gb} GB`]]),
        card('users', 'user', 'You', [
          ['Users', c.users.map(u => u.username + (u.sudo ? ' (admin)' : '')).join(', ') || 'none'],
          ['Root', c.root.password ? 'Password set' : 'Locked (use sudo)'],
          ['Computer', c.hostname], ['Autologin', c.users.find(u => u.autologin) ? 'On' : 'Off']]),
        card('desktop', 'monitor', 'Desktop', [
          ['Desktop', c.profiles.map(profileName).join(', ')],
          ['Login screen', ch.greeter || '—'], ['Graphics', (ch.drivers || []).join(', ') || '—'],
          ['Sound', c.audio === 'pipewire' ? 'PipeWire' : 'None'], ['Bluetooth', c.bluetooth ? 'On' : 'Off']]),
        card('locale', 'globe', 'Region', [
          ['Language', c.locale.language], ['Keyboard', kb ? kb.label : c.locale.keyboard], ['Timezone', c.timezone]]),
        card('software', 'package', 'Software', [
          ['Apps', sw.length ? sw.join(', ') : 'Just the basics'], ['Packages', ch.package_count ? `${ch.package_count} + dependencies` : '—'],
          ['Flatpak', c.flatpak ? 'Flathub enabled' : null], ['AUR helper', c.aur_helper !== 'none' ? c.aur_helper : null],
          ['Extras', c.extra_packages.join(' ') || null]]),
        card('boot', 'rocket', 'Boot', [
          ['Boot loader', ch.bootloader || '—'], ['Kernels', c.kernels.join(', ')], ['Dual boot', ch.dual_boot ? 'Yes, other systems in the menu' : null],
          ['Mirrors', c.mirrors.mode === 'auto' ? 'Fastest, picked automatically' : c.mirrors.mode === 'custom' ? 'Custom' : 'Installer default']])));
      if (ch.layout && ch.layout.length) {
        body.append(h('h3', { style: { marginTop: '24px' } }, 'What happens to your disks'),
          h('div', { class: 'actions-list st' }, ch.layout.map(a => h('div', { class: 'act ' + a.kind },
            icon({ wipe: 'trash', delete: 'trash', shrink: 'layers', create: 'plus', format: 'disk', keep: 'check' }[a.kind] || 'disk'), a.text))));
      }
      body.append(h('div', { class: 'row wrap', style: { marginTop: '20px' } },
        h('button', { class: 'btn ghost sm', id: 'show-cmds', onclick: LS.commandsDialog }, icon('terminal'), 'Show every command'),
        h('button', { class: 'btn ghost sm', id: 'save-cfg', onclick: LS.saveConfig }, icon('save'), 'Save this setup'),
        S.mode === 'easy' ? h('button', { class: 'btn subtle sm', onclick: () => { S.mode = 'advanced'; LS.go('hub'); } }, icon('wrench'), 'Fine-tune in Advanced') : null));
      LS.stagger(body);
      LS.refreshFooter();
    };
    draw();
    ctx.on('checked', draw);
    LS.checkNow();
  },
  footer: () => ({
    back: { label: 'Back', action: () => (S.mode === 'advanced' ? LS.go('hub', { dir: 'l' }) : LS.back()) },
    hint: S.check && S.check.errors.length ? h('span', { class: 'pill err' }, `${S.check.errors.length} to fix`) : '',
    next: { label: S.boot.dry_run ? 'Install (dry run)' : 'Install', icon: 'rocket', action: LS.confirmInstall,
      disabled: () => S.checking || !S.check || S.check.errors.length > 0 || !LS.encryptionOk() } }),
};

LS.commandsDialog = async function commandsDialog() {
  const res = await LS.call('preview', S.cfg);
  const box = h('div', { class: 'cmds selectable' });
  if (!res.ok) box.textContent = res.error;
  else res.steps.forEach(s => { box.append(h('div', { class: 'sh' }, '## ' + s.label)); s.commands.forEach(c => box.append(c + '\n')); box.append('\n'); });
  LS.dialog({ title: 'Every command, in order', lead: 'Passwords are passed on standard input and never appear here or in logs.', body: box, wide: true, actions: [{ label: 'Close' }] });
};

LS.saveConfig = async function saveConfig() {
  const res = await LS.call('save_config', S.cfg);
  if (!res.ok) return LS.toast(res.error, 'err');
  const exp = await LS.call('export_config', S.cfg);
  LS.dialog({ title: 'Setup saved', lead: `Saved to ${res.path}. Passwords are never saved. Load it later from the start screen, or run: python -m linusetup check ${res.path}`,
    body: h('pre', { class: 'cmds selectable' }, exp.text), wide: true, actions: [{ label: 'Done', kind: '' }] });
};

LS.confirmInstall = function confirmInstall() {
  const ch = S.check, m = S.cfg.disk.manual;
  const diskOf = node => (S.disks.find(d => d.partitions.some(x => x.node === node)) || {}).path;
  const touched = S.cfg.disk.mode === 'guided' ? [S.cfg.disk.device]
    : [...new Set([...m.wipe, ...m.new.map(n => n.disk), ...m.delete.map(diskOf), ...m.existing.filter(e => e.format).map(e => diskOf(e.device))])].filter(Boolean);
  const word = (touched[0] || 'install').replace('/dev/', '');
  let go;
  const inp = W.input({ id: 'confirm-word', placeholder: word, onInput: v => { go.disabled = v.trim() !== word; } });
  LS.dialog({
    title: S.boot.dry_run ? 'Start the dry run?' : 'Last check before changes are made',
    lead: S.boot.dry_run ? 'This is a dry run: every step is shown, nothing is changed.' : 'These changes can\'t be undone:',
    body: h('div', { class: 'stack' }, h('div', { class: 'actions-list' }, (ch.layout || []).filter(a => a.kind !== 'keep').map(a => h('div', { class: 'act ' + a.kind }, icon(a.kind === 'create' ? 'plus' : 'warn'), a.text))),
      W.field(`Type "${word}" to confirm`, inp)),
    actions: [{ label: 'Cancel' },
      { label: S.boot.dry_run ? 'Start dry run' : 'Erase and install', kind: 'danger', id: 'confirm-go', icon: 'rocket', disabled: true, ref: b => { go = b; },
        onClick: async (close, btn) => {
          btn.disabled = true;
          const res = await LS.call('start_install', S.cfg, S.fps);
          if (!res.ok) {
            LS.toast(res.error, 'err', 7000);
            if (res.stale) { await LS.loadDisks(); close(); LS.go(S.mode === 'easy' ? 'disk' : 'sec-disk', { dir: 'l' }); return true; }
            btn.disabled = false; return true;
          }
          S.installed = { dry: res.dry_run, t0: Date.now() };
          close(); LS.go('install', { dir: 'up' }); return true;
        } }] });
};

/* ================================================================ install */
const TIPS = [
  'Go touch grass. Seriously, LinuSetup has this.',
  'Arch is a rolling release: run "sudo pacman -Syu" every week or so to stay current.',
  'The Arch Wiki is the best Linux documentation anywhere. Bookmark wiki.archlinux.org.',
  'Snapshots on? Snapper takes one before every pacman transaction, so a bad update is easy to undo.',
  'Flatpak apps install from Flathub without touching your system packages.',
  'AUR helpers like yay build community packages for you. Read PKGBUILDs you don\'t trust.',
  'The install log is saved to /var/log/linusetup-install.log on your new system.',
  'Hold Shift while turning off Windows to do a full shutdown (needed for dual boot).',
];
LS.screens.install = {
  render(el, ctx) {
    S.finish = S.cfg.finish;
    const pct = h('span', { class: 'pct', id: 'pct' }, '0%');
    const title = h('h2', { id: 'inst-title' }, S.installed && S.installed.dry ? 'Dry run in progress' : 'Installing Arch Linux');
    const fill = h('div', { class: 'fill', id: 'fill' });
    const elapsed = h('b', {}, '0:00'), eta = h('b', {}, '…'), stepN = h('b', {}, '–');
    const ticker = h('div', { class: 'ticker', id: 'ticker' }, 'Starting…');
    const log = h('pre', { class: 'log hidden selectable', id: 'log' });
    const logBtn = h('button', { class: 'btn ghost sm', id: 'log-toggle', style: { marginTop: '12px' } }, icon('terminal'), 'Show details');
    logBtn.addEventListener('click', () => { log.classList.toggle('hidden'); logBtn.lastChild.textContent = log.classList.contains('hidden') ? 'Show details' : 'Hide details'; log.scrollTop = log.scrollHeight; });
    const errBox = h('div', { id: 'install-error' });
    const warnBox = h('div', { style: { marginTop: '12px' } });
    const steps = h('div', { class: 'steps', id: 'steps' });
    const tip = h('div', { class: 'tip mut' }, TIPS[0]);
    let tipI = 0;
    ctx.every(7000, () => { tip.style.opacity = 0; setTimeout(() => { tipI = (tipI + 1) % TIPS.length; tip.textContent = TIPS[tipI]; tip.style.opacity = 1; }, 400); });
    const finishSeg = W.seg([{ id: 'none', label: 'Stay' }, { id: 'reboot', label: 'Restart' }, { id: 'poweroff', label: 'Power off' }], S.finish, v => { S.finish = v; }, 'finish-seg');
    el.append(h('div', { class: 'install' },
      h('div', { class: 'panel st' }, h('div', { class: 'prog-head' }, pct, title),
        h('div', { class: 'track' }, fill),
        h('div', { class: 'stats' }, h('span', {}, 'Elapsed ', elapsed), h('span', {}, 'Remaining ', eta), h('span', {}, 'Step ', stepN)),
        ticker, errBox, warnBox, logBtn, log),
      h('div', { class: 'stack' },
        h('div', { class: 'panel st' }, h('h3', {}, icon('layers'), 'Steps'), steps),
        h('div', { class: 'panel grass st' }, h('div', { class: 'row' }, h('span', { class: 'leaf' }, icon('leaf')), h('b', {}, 'You can walk away')), tip,
          h('div', { class: 'lbl', style: { margin: '12px 0 8px' } }, 'When it\'s done:'), finishSeg))));
    const t0 = Date.now();
    let last = 0, seen = 0, finished = false, stepEls = {}, prog = 0;
    const fmt = s => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`;
    ctx.every(1000, () => {
      if (finished) return;
      const s = (Date.now() - t0) / 1000; elapsed.textContent = fmt(s);
      eta.textContent = prog > .06 ? '~' + fmt(Math.max(0, s / prog - s)) : '…';
    });
    const handle = ev => {
      if (ev.type === 'plan') {
        steps.textContent = '';
        ev.steps.forEach(s => { stepEls[s.id] = h('div', { class: 'stp', 'data-id': s.id }, h('div', { class: 'si' }), s.label); steps.append(stepEls[s.id]); });
      } else if (ev.type === 'step') {
        Object.values(stepEls).forEach(e => { if (e.classList.contains('now')) { e.classList.replace('now', 'done'); e.querySelector('.si').replaceChildren(icon('check')); } });
        const e = stepEls[ev.id]; if (e) e.classList.add('now');
        stepN.textContent = `${ev.index + 1}/${ev.total}`;
      } else if (ev.type === 'progress') {
        prog = ev.value; fill.style.transform = `scaleX(${ev.value})`; pct.textContent = Math.floor(ev.value * 100) + '%';
      } else if (ev.type === 'log') {
        ticker.textContent = ev.line;
        log.append(ev.line + '\n');
        if (log.childNodes.length > 3000) log.removeChild(log.firstChild);
        if (!log.classList.contains('hidden')) log.scrollTop = log.scrollHeight;
      } else if (ev.type === 'warning') {
        warnBox.append(W.note('warn', ev.message));
      } else if (ev.type === 'done') {
        finished = true;
        Object.values(stepEls).forEach(e => { if (!e.classList.contains('done')) { e.classList.remove('now'); e.classList.add('done'); e.querySelector('.si').replaceChildren(icon('check')); } });
        fill.style.transform = 'scaleX(1)'; pct.textContent = '100%';
        S.installed = Object.assign(S.installed || {}, { result: ev, seconds: ev.seconds });
        setTimeout(() => LS.go('done', { dir: 'up', replace: true, force: true }), 900);
      } else if (ev.type === 'error') {
        finished = true;
        Object.values(stepEls).forEach(e => { if (e.classList.contains('now')) { e.classList.replace('now', 'fail'); e.querySelector('.si').replaceChildren(icon('x')); } });
        title.textContent = 'The install stopped';
        errBox.append(h('div', { class: 'note err', style: { marginTop: '14px' } }, icon('warn'), h('div', { class: 'grow' },
          h('b', {}, `${ev.step}: `), ev.message,
          h('pre', { class: 'cmds selectable', style: { marginTop: '10px', maxHeight: '180px' } }, (ev.tail || []).join('\n')),
          h('div', { class: 'small' }, S.boot.dry_run ? '' : 'Full log: /var/log/linusetup.log'),
          h('div', { class: 'row', style: { marginTop: '10px' } },
            h('button', { class: 'btn sm', id: 'err-review', onclick: async () => { await LS.loadDisks(); LS.resetHistory(['welcome']); LS.go('review', { dir: 'l', force: true }); } }, 'Back to review'),
            h('button', { class: 'btn ghost sm', onclick: () => log.classList.remove('hidden') }, 'Show log')))));
        LS.refreshFooter();
      }
    };
    const poll = async () => {
      if (finished) return;
      try {
        const r = await LS.call('poll', seen);
        r.events.forEach(ev => { seen = ev.seq + 1; handle(ev); });
      } catch (e) { console.error(e); }
    };
    ctx.every(300, poll);
    poll();
  },
  footer: () => ({ hint: h('span', { class: 'mut small' }, S.boot.dry_run ? 'Dry run: nothing on this computer is being changed.' : 'Please keep the computer on and plugged in.') }),
  crumb: () => ['Installing'],
};

/* ================================================================ done */
LS.screens.done = {
  center: true,
  crumb: () => ['Done'],
  render(el, ctx) {
    const r = (S.installed && S.installed.result) || {};
    const dry = r.dry_run;
    const user = (S.cfg.users[0] || {}).username;
    el.classList.add('center-text');
    el.append(
      h('div', { html: '<svg class="big-check" viewBox="0 0 100 100"><circle cx="50" cy="50" r="48"/><path d="M30 52l14 14 27-30"/></svg>' }),
      h('h1', { class: 'st' }, dry ? 'Dry run ' : 'Welcome to ', h('span', { class: 'grad' }, dry ? 'complete!' : 'Arch Linux!')),
      h('p', { class: 'lead st' }, dry ? 'Every step ran in simulation. On the live ISO this exact plan installs your system.'
        : `Restart, remove the install media, and log in${user ? ' as ' + user : ''}.`),
      h('div', { class: 'chips st', style: { justifyContent: 'center', marginBottom: '18px' } },
        h('span', { class: 'chip green' }, icon('clock'), (r.seconds || 0) < 60 ? `${r.seconds || 0} s` : `${Math.floor(r.seconds / 60)} min ${r.seconds % 60} s`),
        S.check && S.check.package_count ? h('span', { class: 'chip blue' }, icon('package'), `${S.check.package_count} packages`) : null,
        (r.warnings || []).length ? h('span', { class: 'chip yellow' }, icon('warn'), `${r.warnings.length} warning${r.warnings.length > 1 ? 's' : ''}`) : null));
    (r.warnings || []).forEach(w => el.append(h('div', { class: 'note warn st', style: { maxWidth: '640px', margin: '0 auto 8px', textAlign: 'left' } }, icon('info'), w)));
    if (S.check && S.check.dual_boot) el.append(h('p', { class: 'mut small st' }, 'Windows will be in the boot menu. If it isn\'t, run "sudo grub-mkconfig -o /boot/grub/grub.cfg" once.'));
    const cd = h('div', { class: 'mut st countdown', id: 'countdown' });
    el.append(cd);
    if (!dry && S.finish !== 'none') {
      let n = 10;
      const label = S.finish === 'reboot' ? 'Restarting' : 'Powering off';
      cd.append(`${label} in `, h('b', {}, String(n)), ' s  ', h('button', { class: 'linkbtn', onclick: () => { clearInterval(t); cd.textContent = 'Cancelled.'; } }, 'Cancel'));
      const t = setInterval(() => { n--; cd.querySelector('b').textContent = n; if (n <= 0) { clearInterval(t); LS.call('power', S.finish); } }, 1000);
      ctx.cleanups.push(() => clearInterval(t));
    }
    setTimeout(LS.fx.confetti, 350);
  },
  footer: () => ({
    extra: h('button', { class: 'btn ghost', id: 'btn-poweroff', onclick: () => power('poweroff') }, icon('power'), 'Power off'),
    next: { label: 'Restart now', icon: 'refresh', action: () => power('reboot') } }),
};
async function power(a) {
  const r = await LS.call('power', a);
  if (r.dry_run) LS.toast(`Dry run: a real install would ${a === 'reboot' ? 'restart' : 'power off'} now.`, 'info');
}

/* ================================================================ dialogs */
LS.wifiDialog = function wifiDialog() {
  const iface = S.boot.hardware.wifi[0];
  const list = h('div', { class: 'stack', id: 'wifi-list' }, h('div', { class: 'row mut' }, h('span', { class: 'spin' }), 'Scanning…'));
  const close = LS.dialog({ title: 'Connect to Wi-Fi', lead: `Using ${iface}.`, body: list, actions: [{ label: 'Close' }] });
  LS.call('wifi_scan', iface).then(res => {
    list.textContent = '';
    if (!res.ok || !res.networks.length) { list.append(W.note('warn', res.error || 'No networks found.')); return; }
    res.networks.forEach(n => {
      const row = h('div', { class: 'act', style: { cursor: 'pointer' } }, W.signal(n.signal), h('b', { class: 'grow' }, n.ssid), n.security !== 'open' ? icon('lock') : null);
      row.addEventListener('click', () => {
        const pw = W.password({ id: 'wifi-pw', placeholder: 'Password' });
        const msg = h('div');
        const doConnect = async (c2, btn) => {
          btn.disabled = true; msg.replaceChildren(h('div', { class: 'row mut' }, h('span', { class: 'spin' }), 'Connecting…'));
          const r = await LS.call('wifi_connect', iface, n.ssid, pw.input.value);
          if (r.ok) { c2(); close(); LS.toast(`Connected to ${n.ssid}`, 'ok'); LS.refreshOnline(); return true; }
          msg.replaceChildren(W.note('err', r.error)); btn.disabled = false; return true;
        };
        if (n.security === 'open') { doConnect(() => {}, { disabled: false }); return; }
        LS.dialog({ title: n.ssid, body: h('div', { class: 'stack' }, pw, msg), actions: [{ label: 'Cancel' }, { label: 'Connect', kind: '', id: 'wifi-connect', onClick: doConnect }] });
      });
      list.append(row);
    });
  });
};

LS.loadConfigDialog = function loadConfigDialog() {
  const ta = h('textarea', { class: 'input selectable', id: 'config-text', placeholder: '{ "version": 1, ... }', style: { minHeight: '220px' } });
  const file = h('input', { type: 'file', accept: '.json,application/json' });
  file.addEventListener('change', async () => { if (file.files[0]) ta.value = await file.files[0].text(); });
  const msg = h('div');
  LS.dialog({ title: 'Load a saved setup', lead: 'Paste a LinuSetup config, or open a .json file. Passwords are never stored in configs, so you will set them again.',
    body: h('div', { class: 'stack' }, file, ta, msg), wide: true,
    actions: [{ label: 'Cancel' }, { label: 'Load', kind: '', id: 'config-load', onClick: async () => {
      const r = await LS.call('import_config', ta.value);
      if (!r.ok) { msg.replaceChildren(W.note('err', r.error)); return true; }
      S.cfg = r.config; S.mode = 'advanced';
      await LS.loadDisks(); LS.checkNow();
      LS.toast('Setup loaded. Review each section, then set passwords.', 'ok');
      LS.go('hub');
    } }] });
};
})();
