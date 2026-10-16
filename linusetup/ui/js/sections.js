/* Advanced mode: the hub and one editor per section. Everything archinstall
   can configure, plus a manual partition editor. */
'use strict';
(() => {
const { h, icon, w: W, S, $ } = LS;
const MiB = 1024 * 1024, GiB = 1024 * MiB;
const cat = () => S.boot.catalog;

const SECTIONS = [
  { id: 'disk', icon: 'disk', title: 'Disks & partitions', desc: 'Where Arch goes, filesystems, encryption' },
  { id: 'desktop', icon: 'monitor', title: 'Desktop & graphics', desc: 'Desktop, login screen, drivers, sound' },
  { id: 'users', icon: 'users', title: 'Users & security', desc: 'Accounts, administrator, root' },
  { id: 'software', icon: 'package', title: 'Software', desc: 'Apps, Flatpak, AUR helper, any package' },
  { id: 'locale', icon: 'globe', title: 'Language & region', desc: 'Language, keyboard, timezone' },
  { id: 'boot', icon: 'rocket', title: 'Boot & kernels', desc: 'Boot loader, kernels, parameters' },
  { id: 'mirrors', icon: 'server', title: 'Mirrors & repositories', desc: 'Download servers, multilib' },
  { id: 'network', icon: 'wifi', title: 'Network', desc: 'Wi-Fi now, network manager later' },
  { id: 'system', icon: 'sliders', title: 'System & extras', desc: 'Hostname, swap, firewall, services, scripts' },
];
const SECTION = Object.fromEntries(SECTIONS.map(s => [s.id, s]));
const toHub = () => LS.go('hub', { dir: 'l', back: true });
const label = (list, id) => (list.find(x => x.id === id) || { label: id }).label;
const profileName = id => (cat().profiles.find(p => p.id === id) || { name: id }).name;

function summary(id) {
  const c = S.cfg, ch = S.check || {};
  switch (id) {
    case 'disk': {
      if (c.disk.mode === 'manual') {
        const m = c.disk.manual;
        return `Manual: ${m.new.length} new, ${m.existing.length} reused, ${m.delete.length} deleted partitions${m.wipe.length ? `, ${m.wipe.length} disk(s) erased` : ''}`;
      }
      const d = LS.disk(c.disk.device);
      if (!d) return 'No disk chosen yet';
      return `${d.model} · ${{ wipe: 'erase', free: 'free space', shrink: 'shrink Windows' }[c.disk.scope]} · ${c.disk.fs}${c.disk.encryption.enabled ? ' · encrypted' : ''}`;
    }
    case 'desktop': return [c.profiles.map(profileName).join(', ') || 'Nothing', ch.greeter && ch.greeter !== 'none' ? ch.greeter : null,
      (ch.drivers || []).length ? ch.drivers.join(', ') + ' graphics' : null, c.audio === 'pipewire' ? 'PipeWire' : null].filter(Boolean).join(' · ');
    case 'users': return c.users.length ? c.users.map(u => u.username + (u.sudo ? ' (admin)' : '')).join(', ') + (c.root.password ? ' · root password set' : ' · root locked') : 'No user yet';
    case 'software': return `${c.software.length} app bundle${c.software.length === 1 ? '' : 's'}${c.extra_packages.length ? ` + ${c.extra_packages.length} packages` : ''}${c.flatpak ? ' · Flatpak' : ''}${c.aur_helper !== 'none' ? ' · ' + c.aur_helper : ''}`;
    case 'locale': return `${c.locale.language} · ${label(cat().keyboards, c.locale.keyboard)} · ${c.timezone}`;
    case 'boot': return `${c.bootloader.type === 'auto' ? (ch.bootloader ? `Automatic (${ch.bootloader})` : 'Automatic') : c.bootloader.type} · ${c.kernels.join(', ')}`;
    case 'mirrors': return `${{ auto: 'Fastest mirrors', iso: 'Installer list', custom: 'Custom mirrors' }[c.mirrors.mode]}${c.mirrors.countries.length ? ' in ' + c.mirrors.countries.join(', ') : ''} · ${c.mirrors.parallel} parallel${ch.multilib ? ' · multilib' : ''}`;
    case 'network': return `${S.online ? 'Online' : 'Offline'} now · ${label(cat().network, c.network.manager)}`;
    case 'system': return `${c.hostname} · swap ${c.swap.mode} · firewall ${c.firewall}${c.ssh ? ' · SSH' : ''}`;
  }
  return '';
}

/* ================================================================ hub */
LS.screens.hub = {
  crumb: () => ['Advanced'],
  render(el, ctx) {
    el.append(h('div', { class: 'row wrap st', style: { marginBottom: '20px' } },
      h('div', { class: 'grow' }, h('h1', {}, 'Configure ', h('span', { class: 'grad' }, 'everything')),
        h('p', { class: 'lead', style: { margin: 0 } }, 'Open any section. Problems show up here as you go, and the review screen checks it all.')),
      h('button', { class: 'btn ghost sm', id: 'hub-load', onclick: LS.loadConfigDialog }, icon('upload'), 'Load'),
      h('button', { class: 'btn ghost sm', id: 'hub-save', onclick: LS.saveConfig }, icon('save'), 'Save')));
    const tiles = h('div', { class: 'tiles' });
    el.append(tiles);
    const draw = () => {
      tiles.textContent = '';
      SECTIONS.forEach(s => {
        const errs = LS.issues(s.id).length, warns = LS.issues(s.id, 'warnings').length;
        const pill = errs ? h('span', { class: 'pill err' }, icon('warn'), `${errs} to fix`) : warns ? h('span', { class: 'pill warn' }, icon('info'), 'Check') : h('span', { class: 'pill ok' }, icon('check'), 'Ready');
        tiles.append(h('div', { class: 'tile st' + (errs ? ' has-err' : ''), id: 'tile-' + s.id, onclick: () => LS.go('sec-' + s.id) },
          h('span', { class: 'st-pill' }, pill),
          h('div', { class: 'th' }, h('div', { class: 'ti' }, icon(s.icon)), h('b', {}, s.title)),
          h('div', { class: 'sum' }, summary(s.id))));
      });
      LS.stagger(tiles);
      LS.refreshFooter();
    };
    draw();
    ctx.on('checked', draw);
    if (!S.disks.length) LS.loadDisks().then(draw);
  },
  footer: () => {
    const n = S.check ? S.check.errors.length : 0;
    return { back: { label: 'Mode', action: () => LS.go('mode', { dir: 'l', back: true }) },
      hint: n ? h('span', { class: 'pill err' }, `${n} thing${n > 1 ? 's' : ''} to fix`) : S.checking ? h('span', { class: 'mut small' }, 'Checking…') : h('span', { class: 'pill ok' }, icon('check'), 'All good'),
      next: { label: 'Review', action: () => LS.go('review') } };
  },
};

function section(id, render) {
  const s = SECTION[id];
  LS.screens['sec-' + id] = {
    crumb: () => ['Advanced', s.title],
    render(el, ctx) {
      el.append(h('div', { class: 'head st' }, h('div', { class: 'ico' }, icon(s.icon)), h('div', {}, h('h1', {}, s.title), h('p', {}, s.desc))));
      const notes = LS.notes(id);
      el.append(notes);
      ctx.on('checked', () => notes._draw());
      const body = h('div');
      el.append(body);
      render(body, ctx);
    },
    footer: { back: { label: 'All settings', action: toHub }, next: { label: 'Done', icon: 'check', action: toHub } },
  };
}
const panel = (title, ...kids) => h('div', { class: 'panel st' }, title ? h('h3', {}, title) : null, ...kids);

/* ================================================================ locale */
section('locale', (el) => {
  const c = S.cfg;
  el.append(panel(null, h('div', { class: 'form' },
    W.field('Language', W.combo({ id: 'adv-language', value: c.locale.language, options: cat().locales.map(l => ({ id: l, label: l })), onChange: v => LS.set(x => { x.locale.language = v; }) })),
    W.field('Keyboard layout', W.combo({ id: 'adv-keyboard', value: c.locale.keyboard, options: cat().keyboards.map(k => ({ id: k.id, label: k.label, hint: k.id })),
      onChange: v => LS.set(x => { x.locale.keyboard = v; }) }), { help: 'Used on the console, the login screen and your desktop.' }),
    W.field('Timezone', W.combo({ id: 'adv-timezone', value: c.timezone, options: S.boot.timezones.map(z => ({ id: z, label: z.replace(/_/g, ' ') })), onChange: v => LS.set(x => { x.timezone = v; }) })),
    W.field('Extra languages', W.multi({ values: c.locale.extra, options: cat().locales.map(l => ({ id: l, label: l })), onChange: v => LS.set(x => { x.locale.extra = v; }) }),
      { help: 'Generate more locales, e.g. for apps in another language.' }))),
  panel(null, W.toggle({ title: 'Set the clock automatically', desc: 'Network time (systemd-timesyncd)', value: c.ntp, id: 'adv-ntp', onChange: v => LS.set(x => { x.ntp = v; }) })));
});

/* ================================================================ network */
section('network', (el, ctx) => {
  const status = h('div');
  const draw = () => {
    status.textContent = '';
    const wifi = S.boot.hardware.wifi;
    status.append(h('div', { class: 'row wrap' },
      h('span', { class: 'badge ' + (S.online ? 'ok' : 'bad') }, icon('wifi'), S.online ? 'Online' : 'Offline'),
      h('span', { class: 'mut small grow' }, S.online ? 'The installer can download packages.' : 'Packages are downloaded during the install, so connect first.'),
      wifi.length ? h('button', { class: 'btn sm', id: 'adv-wifi', onclick: LS.wifiDialog }, icon('wifi'), 'Wi-Fi networks') : h('span', { class: 'mut small' }, 'No Wi-Fi adapter'),
      h('button', { class: 'btn ghost sm', onclick: LS.refreshOnline }, icon('refresh'), 'Check again')));
  };
  draw(); ctx.on('online', draw);
  const choices = h('div', { class: 'choices' });
  const drawChoices = () => {
    choices.textContent = '';
    const desc = { networkmanager: 'Wi-Fi and wired with a tray icon and settings. Works with every desktop.',
      networkd: 'Lean and fast. DHCP on every wired and wireless interface, Wi-Fi via iwctl.', none: 'Install nothing. For experts building their own setup.' };
    cat().network.forEach(n => choices.append(W.choice({ id: 'net-' + n.id, title: n.label, desc: desc[n.id], sel: S.cfg.network.manager === n.id,
      onClick: () => { LS.set(x => { x.network.manager = n.id; }); drawChoices(); } })));
  };
  drawChoices();
  el.append(panel('Right now', status), panel('On the installed system', choices,
    h('div', { style: { marginTop: '12px' } }, W.toggle({ title: 'Remember this Wi-Fi network', desc: 'Copy the network you connect to here into the new system',
      value: S.cfg.network.copy_wifi, id: 'adv-copywifi', onChange: v => LS.set(x => { x.network.copy_wifi = v; }) }))));
});

/* ================================================================ mirrors */
section('mirrors', (el) => {
  const m = S.cfg.mirrors;
  const extra = h('div');
  const choices = h('div', { class: 'choices' });
  const drawChoices = () => {
    choices.textContent = '';
    [['auto', 'Fastest mirrors, picked automatically', 'Reflector tests recent HTTPS mirrors and keeps the 20 fastest.'],
     ['iso', 'Keep the installer\'s mirror list', 'Use whatever the live ISO already ranked at boot.'],
     ['custom', 'My own mirrors', 'A local cache or a mirror you trust.']].forEach(([id, t, d]) =>
      choices.append(W.choice({ id: 'mir-' + id, title: t, desc: d, sel: S.cfg.mirrors.mode === id, onClick: () => { LS.set(x => { x.mirrors.mode = id; }); drawChoices(); drawExtra(); } })));
  };
  const drawExtra = () => {
    extra.textContent = '';
    if (S.cfg.mirrors.mode === 'auto') extra.append(W.field('Only use mirrors in', W.multi({ values: S.cfg.mirrors.countries, placeholder: 'Add a country…',
      options: cat().countries.map(c => ({ id: c.id, label: c.label, hint: c.id })), onChange: v => LS.set(x => { x.mirrors.countries = v; }) }), { help: 'Leave empty to search worldwide.' }));
    if (S.cfg.mirrors.mode === 'custom') {
      const ta = h('textarea', { class: 'input', id: 'mir-custom', placeholder: 'https://mirror.example.org/archlinux/$repo/os/$arch' });
      ta.value = S.cfg.mirrors.custom.join('\n');
      ta.addEventListener('input', () => LS.set(x => { x.mirrors.custom = ta.value.split('\n').map(s => s.trim()).filter(Boolean); }));
      extra.append(W.field('Mirror URLs, one per line', ta));
    }
  };
  drawChoices(); drawExtra();
  const multilibNote = h('div', { class: 'small mut', style: { marginTop: '6px' } });
  const ml = W.toggle({ title: 'Enable multilib (32-bit) repository', desc: 'Needed by Steam and Wine. Turned on automatically when you pick them.', value: m.multilib, id: 'adv-multilib',
    onChange: v => LS.set(x => { x.mirrors.multilib = v; }) });
  el.append(panel('Download servers', choices, h('div', { style: { marginTop: '14px' } }, extra)),
    panel('Pacman', h('div', { class: 'stack' },
      W.field('Parallel downloads', W.slider({ min: 1, max: 20, value: m.parallel, id: 'adv-parallel', format: v => `${v} at once`, onInput: v => LS.set(x => { x.mirrors.parallel = v; }) })),
      ml, multilibNote,
      W.toggle({ title: 'Colourful pacman output', value: m.color, onChange: v => LS.set(x => { x.mirrors.color = v; }) }))));
});

/* ================================================================ disk */
section('disk', (el, ctx) => {
  const tabs = W.seg([{ id: 'guided', label: 'Guided' }, { id: 'manual', label: 'Manual partitioning' }], S.cfg.disk.mode,
    v => { LS.set(x => { x.disk.mode = v; }); draw(); }, 'disk-mode');
  const body = h('div', { style: { marginTop: '16px' } });
  const after = h('div');
  el.append(h('div', { class: 'row st' }, tabs, h('span', { class: 'spacer' }), h('button', { class: 'btn ghost sm', onclick: async () => { await LS.loadDisks(); draw(); LS.checkNow(); } }, icon('refresh'), 'Rescan disks')), body, after);
  const draw = () => {
    body.textContent = '';
    if (S.cfg.disk.mode === 'guided') guidedDisk(body, draw); else manualDisk(body, draw);
    LS.stagger(body);
    drawAfter();
  };
  const drawAfter = () => {
    after.textContent = '';
    const ch = S.check; if (!ch || !ch.preview) return;
    const p = h('div', { class: 'panel', style: { marginTop: '16px' } }, h('h3', {}, icon('layers'), 'Result'));
    Object.entries(ch.preview).forEach(([path, pv]) => p.append(h('div', { class: 'small mut', style: { marginTop: '8px' } }, path), LS.afterBar(pv)));
    if (ch.layout && ch.layout.length) p.append(h('div', { class: 'actions-list', style: { marginTop: '14px' } },
      ch.layout.map(a => h('div', { class: 'act ' + a.kind }, icon({ wipe: 'trash', delete: 'trash', shrink: 'layers', create: 'plus', format: 'disk', keep: 'check' }[a.kind] || 'disk'), a.text))));
    after.append(p);
  };
  if (!S.disks.length) LS.loadDisks().then(draw); else draw();
  ctx.on('checked', drawAfter);
});

function guidedDisk(el, redraw) {
  const g = S.cfg.disk;
  const list = h('div', { class: 'disklist' });
  S.disks.forEach(d => list.append(W.diskCard(d, { sel: g.device === d.path, onClick: dd => {
    LS.set(x => { x.disk.device = dd.path; x.disk.scope = 'wipe'; x.disk.shrink = { partition: '', free_gb: 0 }; }); redraw(); } })));
  el.append(panel('Disk', list));
  const d = LS.disk(g.device);
  if (!d) return;
  el.append(panel('How to use it', LS.scopeChoices(d, redraw)));
  const fsSeg = W.seg(cat().filesystems.map(f => ({ id: f.id, label: f.label, title: f.desc })), g.fs, v => { LS.set(x => { x.disk.fs = v; }); redraw(); }, 'adv-fs');
  const fsDesc = h('div', { class: 'small mut', style: { marginTop: '8px' } }, (cat().filesystems.find(f => f.id === g.fs) || {}).desc);
  const fs = panel('Filesystem', fsSeg, fsDesc);
  if (g.fs === 'btrfs') {
    fs.append(h('div', { class: 'grid2', style: { marginTop: '14px' } },
      W.toggle({ title: 'Subvolumes', desc: '@, @home, @log, @pkg (recommended)', value: g.btrfs.subvolumes, id: 'adv-subvol', onChange: v => LS.set(x => { x.disk.btrfs.subvolumes = v; }) }),
      W.toggle({ title: 'Snapshots', desc: 'Snapper, plus a snapshot before every update', value: g.btrfs.snapshots, id: 'adv-snapshots', onChange: v => LS.set(x => { x.disk.btrfs.snapshots = v; }) })),
      h('div', { class: 'row', style: { marginTop: '12px' } }, h('span', { class: 'lbl' }, 'Compression'),
        W.seg([{ id: 'zstd', label: 'zstd' }, { id: 'lzo', label: 'lzo' }, { id: 'none', label: 'Off' }], g.btrfs.compress, v => LS.set(x => { x.disk.btrfs.compress = v; }))));
  }
  const homeSlider = W.slider({ min: 20, max: 500, step: 5, value: g.home.root_gb, id: 'adv-rootgb', format: v => `${v} GB system`, onInput: v => LS.set(x => { x.disk.home.root_gb = v; }) });
  const homeBox = h('div', { class: g.home.separate ? '' : 'hidden', style: { marginTop: '12px' } }, homeSlider, h('div', { class: 'small mut' }, 'The rest of the space goes to /home.'));
  fs.append(h('div', { style: { marginTop: '14px' } }, W.toggle({ title: 'Separate /home partition', desc: 'Keep your files apart from the system', value: g.home.separate, id: 'adv-home',
    onChange: v => { LS.set(x => { x.disk.home.separate = v; }); homeBox.classList.toggle('hidden', !v); } })), homeBox);
  el.append(fs);
  const enc = LS.encryptionUI();
  el.append(panel('Encryption', enc.toggle, enc.fields));
}

/* ---------------------------------------------------------------- manual */
const FS_OPTS = [
  { id: 'ext4', label: 'ext4' }, { id: 'btrfs', label: 'Btrfs' }, { id: 'xfs', label: 'XFS' }, { id: 'f2fs', label: 'F2FS' },
  { id: 'vfat', label: 'FAT32 (EFI system partition)' }, { id: 'swap', label: 'Swap' }, { id: 'bios_grub', label: 'BIOS boot (1 MB, legacy GRUB)' }];
const MOUNTS = ['/', '/boot', '/efi', '/home', '/var', '/srv', '/opt', '/data'];
let manualDiskPath = null;

function manualDisk(el, redraw) {
  const m = S.cfg.disk.manual;
  const usable = S.disks.filter(d => d.usable || d.partitions.some(p => !p.mounted));
  if (!manualDiskPath || !LS.disk(manualDiskPath)) manualDiskPath = (usable[0] || {}).path;
  const picker = h('div', { class: 'chips' });
  S.disks.forEach(d => picker.append(h('span', { class: 'chip click' + (d.path === manualDiskPath ? ' sel' : ''), onclick: () => { manualDiskPath = d.path; redraw(); } },
    icon('disk'), `${d.path} · ${LS.gb(d.size)}`)));
  el.append(panel('Disk', picker, h('p', { class: 'small mut', style: { margin: '10px 0 0' } },
    'Plan the partitions on each disk. Nothing is written until you install. Every change is listed on the review screen.')));
  const d = LS.disk(manualDiskPath);
  if (!d) return;
  const wiped = m.wipe.includes(d.path);
  const deleted = new Set(m.delete);
  const kept = wiped ? [] : d.partitions.filter(p => !deleted.has(p.node));
  const news = m.new.map((n, i) => ({ ...n, i })).filter(n => n.disk === d.path);
  const occupied = [...kept.map(p => ({ start: p.start, size: p.size })), ...news.map(n => ({ start: n.start_mib * MiB, size: n.size_mib * MiB }))];
  const free = LS.freeRegions(d.size, occupied);

  const segs = [...kept.map(p => ({ start: p.start, size: p.size, kind: p.kind, label: p.label || W.KIND_LABEL[p.kind] })),
    ...news.map(n => ({ start: n.start_mib * MiB, size: n.size_mib * MiB, kind: n.fs === 'swap' ? 'swap' : n.fs === 'vfat' ? 'esp' : n.encrypt ? 'luks' : 'new', label: n.mount || n.fs }))];
  const rows = [];
  if (!wiped) d.partitions.forEach(p => rows.push({ t: 'part', p, start: p.start }));
  news.forEach(n => rows.push({ t: 'new', n, start: n.start_mib * MiB }));
  free.forEach(f => rows.push({ t: 'free', f, start: f.start }));
  rows.sort((a, b) => a.start - b.start);

  const table = h('table', { class: 'ptable' });
  rows.forEach(r => {
    if (r.t === 'part') {
      const p = r.p, del = deleted.has(p.node), use = m.existing.find(e => e.device === p.node);
      const status = del ? h('span', { class: 'chip red' }, 'delete') : use ? h('span', { class: 'chip green' }, `${use.format ? 'format ' + use.fs + ', ' : ''}${use.mount === '[SWAP]' ? 'swap' : use.mount}`) : h('span', { class: 'chip' }, 'keep');
      table.append(h('tr', { class: del ? 'del' : '' },
        h('td', {}, h('i', { class: 'sw-k k-' + p.kind }), h('b', {}, p.node)), h('td', {}, LS.gb(p.size)),
        h('td', {}, p.fstype || W.KIND_LABEL[p.kind]), h('td', { class: 'mut' }, p.label || p.name), h('td', {}, status),
        h('td', {}, p.mounted || p.kind === 'bitlocker' ? h('span', { class: 'mut small' }, p.mounted ? 'in use' : 'locked') : [
          !del ? h('button', { class: 'btn ghost sm', onclick: () => existingDialog(p, redraw) }, icon('edit'), use ? 'Edit' : 'Use') : null, ' ',
          h('button', { class: 'btn ghost sm', onclick: () => { LS.set(x => {
            const mm = x.disk.manual;
            if (del) mm.delete = mm.delete.filter(n => n !== p.node);
            else { mm.delete.push(p.node); mm.existing = mm.existing.filter(e => e.device !== p.node); }
          }); redraw(); } }, icon(del ? 'refresh' : 'trash'), del ? 'Restore' : 'Delete')])));
    } else if (r.t === 'new') {
      const n = r.n;
      table.append(h('tr', { class: 'new' },
        h('td', {}, h('i', { class: 'sw-k k-new' }), h('b', {}, 'new')), h('td', {}, LS.gb(n.size_mib * MiB)), h('td', {}, n.fs + (n.encrypt ? ' · encrypted' : '')),
        h('td', { class: 'mut' }, n.label || ''), h('td', {}, h('span', { class: 'chip blue' }, n.fs === 'swap' ? 'swap' : n.fs === 'bios_grub' ? 'bios boot' : n.mount)),
        h('td', {}, h('button', { class: 'btn ghost sm', onclick: () => newDialog(d, null, redraw, n) }, icon('edit'), 'Edit'), ' ',
          h('button', { class: 'btn ghost sm', onclick: () => { LS.set(x => { x.disk.manual.new.splice(n.i, 1); }); redraw(); } }, icon('trash'), 'Remove'))));
    } else {
      table.append(h('tr', { class: 'free' }, h('td', {}, h('i', { class: 'sw-k k-free' }), 'Free space'), h('td', {}, LS.gb(r.f.size)), h('td', { colspan: 3 }),
        h('td', {}, h('button', { class: 'btn sm', 'data-free': r.f.start, onclick: () => newDialog(d, r.f, redraw) }, icon('plus'), 'New partition'))));
    }
  });
  const wipeBtn = h('button', { class: 'btn ' + (wiped ? 'ghost' : 'danger') + ' sm', id: 'manual-wipe', onclick: () => {
    LS.set(x => {
      const mm = x.disk.manual;
      if (wiped) mm.wipe = mm.wipe.filter(p => p !== d.path);
      else {
        mm.wipe.push(d.path);
        const nodes = new Set(d.partitions.map(p => p.node));
        mm.delete = mm.delete.filter(n => !nodes.has(n)); mm.existing = mm.existing.filter(e => !nodes.has(e.device));
      }
      mm.new = mm.new.filter(n => n.disk !== d.path);
    }); redraw(); } }, icon(wiped ? 'refresh' : 'trash'), wiped ? 'Keep existing partitions' : 'Erase whole disk (new GPT)');
  const quick = h('button', { class: 'btn ghost sm', id: 'manual-suggest', onclick: () => suggest(d, redraw) }, icon('sparkles'), 'Suggest a layout');
  el.append(panel(null, h('div', { class: 'row wrap' }, h('h3', { class: 'grow', style: { margin: 0 } }, `${d.model} (${d.path})`), quick, wipeBtn),
    d.pttype === 'dos' && !wiped ? W.note('warn', 'This disk has an MBR partition table. To create partitions on it, erase it first (it becomes GPT).') : null,
    W.diskBar(d.size, segs), table));
  const anyEnc = [...m.new, ...m.existing].some(x => x.encrypt);
  if (anyEnc) {
    const enc = LS.encryptionUI();
    if (!S.cfg.disk.encryption.enabled) LS.set(x => { x.disk.encryption.enabled = true; });
    enc.fields.classList.remove('hidden');
    el.append(panel('Encryption passphrase', h('p', { class: 'small mut', style: { margin: '0 0 6px' } }, 'One passphrase unlocks every encrypted partition at boot.'), enc.fields));
  }
}

/* Fill the biggest free region with an EFI/BIOS + root layout. */
function suggest(d, redraw) {
  const m = S.cfg.disk.manual, uefi = S.boot.hardware.uefi;
  const wiped = m.wipe.includes(d.path);
  const kept = wiped ? [] : d.partitions.filter(p => !m.delete.includes(p.node));
  const occ = [...kept, ...m.new.filter(n => n.disk === d.path).map(n => ({ start: n.start_mib * MiB, size: n.size_mib * MiB }))];
  const f = LS.freeRegions(d.size, occ).sort((a, b) => b.size - a.size)[0];
  if (!f || f.size < 24 * GiB) return LS.toast('Not enough free space for a suggestion (needs 24 GB).', 'warn');
  let start = f.start / MiB; const end = f.end / MiB;
  const add = [];
  const esp = !wiped && d.partitions.find(p => p.kind === 'esp' && !m.delete.includes(p.node));
  if (uefi && esp) LS.set(x => { if (!x.disk.manual.existing.some(e => e.device === esp.node)) x.disk.manual.existing.push({ device: esp.node, mount: '/efi', format: false, fs: '', encrypt: false, label: '' }); });
  else if (uefi) { add.push({ disk: d.path, start_mib: start, size_mib: 1024, fs: 'vfat', mount: '/boot', label: 'ESP', encrypt: false }); start += 1024; }
  else { add.push({ disk: d.path, start_mib: start, size_mib: 1, fs: 'bios_grub', mount: '', label: 'BIOS', encrypt: false }); start += 1; }
  add.push({ disk: d.path, start_mib: start, size_mib: end - start, fs: 'ext4', mount: '/', label: 'arch', encrypt: false });
  LS.set(x => { x.disk.manual.new.push(...add); });
  redraw();
}

function newDialog(d, region, redraw, existing) {
  const m = S.cfg.disk.manual;
  let maxMiB;
  if (existing) {
    const others = [...(m.wipe.includes(d.path) ? [] : d.partitions.filter(p => !m.delete.includes(p.node))),
      ...m.new.filter((n, i) => n.disk === d.path && i !== existing.i).map(n => ({ start: n.start_mib * MiB, size: n.size_mib * MiB }))];
    region = LS.freeRegions(d.size, others).find(r => r.start <= existing.start_mib * MiB && existing.start_mib * MiB < r.end);
  }
  maxMiB = Math.floor(region.size / MiB);
  const v = existing ? { ...existing } : { disk: d.path, start_mib: region.start / MiB, size_mib: maxMiB, fs: 'ext4', mount: '/', label: '', encrypt: false };
  v.start_mib = region.start / MiB;
  const sizeIn = W.input({ id: 'np-size', value: String(Math.round(v.size_mib / 1024 * 10) / 10), onInput: x => { v.size_mib = Math.max(1, Math.min(maxMiB, Math.round(parseFloat(x || 0) * 1024))); } });
  const mountIn = W.input({ id: 'np-mount', value: v.mount, placeholder: '/', onInput: x => { v.mount = x.trim(); } });
  const mountRow = W.field('Mount point', h('div', { class: 'stack' }, mountIn, h('div', { class: 'chips' }, MOUNTS.map(mp => h('span', { class: 'chip click', onclick: () => { mountIn.value = mp; v.mount = mp; } }, mp)))));
  const encT = W.toggle({ title: 'Encrypt (LUKS2)', value: v.encrypt, id: 'np-encrypt', onChange: x => { v.encrypt = x; } });
  const syncFs = () => {
    const noMount = v.fs === 'swap' || v.fs === 'bios_grub';
    mountRow.classList.toggle('hidden', noMount);
    encT.classList.toggle('off', ['vfat', 'swap', 'bios_grub'].includes(v.fs));
    if (v.fs === 'bios_grub') { v.size_mib = 1; sizeIn.value = '0.001'; }
    if (v.fs === 'vfat' && (!v.mount || v.mount === '/')) { v.mount = '/boot'; mountIn.value = '/boot'; }
  };
  const fsSel = W.combo({ id: 'np-fs', value: v.fs, options: FS_OPTS, search: false, onChange: x => { v.fs = x; syncFs(); } });
  const body = h('div', { class: 'form' },
    W.field(`Size in GB (up to ${(maxMiB / 1024).toFixed(1)})`, h('div', { class: 'row' }, sizeIn, h('button', { class: 'btn ghost sm', onclick: () => { v.size_mib = maxMiB; sizeIn.value = (maxMiB / 1024).toFixed(1); } }, 'Use all'))),
    W.field('Filesystem', fsSel), mountRow,
    W.field('Label (optional)', W.input({ id: 'np-label', value: v.label, onInput: x => { v.label = x.trim(); } })),
    h('div', { class: 'wide' }, encT));
  syncFs();
  LS.dialog({ title: existing ? 'Edit new partition' : 'New partition', lead: `In ${LS.gb(region.size)} of free space on ${d.path}.`, body, wide: true,
    actions: [{ label: 'Cancel' }, { label: existing ? 'Save' : 'Add partition', kind: '', id: 'np-ok', icon: 'check', onClick: () => {
      if (v.fs === 'swap' || v.fs === 'bios_grub') v.mount = '';
      if (['vfat', 'swap', 'bios_grub'].includes(v.fs)) v.encrypt = false;
      const out = { disk: v.disk, start_mib: v.start_mib, size_mib: Math.min(v.size_mib, maxMiB), fs: v.fs, mount: v.mount, label: v.label, encrypt: v.encrypt };
      LS.set(x => { if (existing) x.disk.manual.new[existing.i] = out; else x.disk.manual.new.push(out); });
      redraw();
    } }] });
}

function existingDialog(p, redraw) {
  const m = S.cfg.disk.manual;
  const cur = m.existing.find(e => e.device === p.node);
  const v = cur ? { ...cur } : { device: p.node, mount: p.kind === 'esp' ? '/efi' : p.kind === 'swap' ? '[SWAP]' : '', format: false, fs: p.fstype === 'vfat' ? 'vfat' : 'ext4', encrypt: false, label: '' };
  const fmtBox = h('div', { class: v.format ? '' : 'hidden' });
  const mountIn = W.input({ id: 'ep-mount', value: v.mount === '[SWAP]' ? '' : v.mount, placeholder: '/home', onInput: x => { v.mount = x.trim(); } });
  fmtBox.append(W.field('New filesystem', W.combo({ id: 'ep-fs', value: v.fs, options: FS_OPTS.filter(f => f.id !== 'bios_grub'), search: false, onChange: x => { v.fs = x; } })),
    h('div', { style: { marginTop: '10px' } }, W.toggle({ title: 'Encrypt (LUKS2)', value: v.encrypt, onChange: x => { v.encrypt = x; } })));
  const body = h('div', { class: 'stack' },
    W.note('info', `${p.node}: ${LS.gb(p.size)}, ${p.fstype || 'no filesystem'}${p.label ? ', "' + p.label + '"' : ''}.`),
    W.field('Mount point', h('div', { class: 'stack' }, mountIn, h('div', { class: 'chips' }, MOUNTS.map(mp => h('span', { class: 'chip click', onclick: () => { mountIn.value = mp; v.mount = mp; } }, mp))))),
    W.toggle({ title: 'Format this partition', desc: 'Erases what is on it. Leave off to keep the data (e.g. reuse an EFI partition or an existing /home).', value: v.format, id: 'ep-format',
      onChange: x => { v.format = x; fmtBox.classList.toggle('hidden', !x); } }), fmtBox);
  LS.dialog({ title: `Use ${p.node}`, body, wide: true, actions: [
    cur ? { label: 'Stop using it', onClick: () => { LS.set(x => { x.disk.manual.existing = x.disk.manual.existing.filter(e => e.device !== p.node); }); redraw(); } } : { label: 'Cancel' },
    { label: 'Save', kind: '', id: 'ep-ok', icon: 'check', onClick: () => {
      const out = { device: p.node, mount: v.format && v.fs === 'swap' ? '[SWAP]' : v.mount, format: v.format, fs: v.format ? v.fs : '', encrypt: v.format && v.encrypt, label: v.label };
      LS.set(x => { const mm = x.disk.manual; const i = mm.existing.findIndex(e => e.device === p.node); if (i >= 0) mm.existing[i] = out; else mm.existing.push(out); });
      redraw();
    } }] });
}

/* ================================================================ boot */
section('boot', (el) => {
  const c = S.cfg, uefi = S.boot.hardware.uefi;
  const choices = h('div', { class: 'choices' });
  const draw = () => {
    choices.textContent = '';
    [['auto', 'Automatic', `Picks the best one for your setup${S.check && S.check.bootloader ? ` (currently ${S.check.bootloader})` : ''}.`],
     ['systemd-boot', 'systemd-boot', uefi ? 'Simple and fast. Needs the EFI partition at /boot.' : 'Needs UEFI; this computer uses legacy BIOS.'],
     ['grub', 'GRUB', 'The classic. Works everywhere, finds Windows and other systems, supports snapshots in the menu.']]
      .forEach(([id, t, d]) => choices.append(W.choice({ id: 'bl-' + id, title: t, desc: d, sel: S.cfg.bootloader.type === id, off: id === 'systemd-boot' && !uefi,
        onClick: () => { LS.set(x => { x.bootloader.type = id; }); draw(); } })));
  };
  draw();
  const kernels = h('div', { class: 'cards' });
  cat().kernels.forEach(k => {
    const card = W.card({ icon: 'cpu', title: k.label, desc: k.desc, id: 'k-' + k.id, sel: c.kernels.includes(k.id), onClick: () => {
      LS.set(x => { x.kernels = x.kernels.includes(k.id) ? x.kernels.filter(y => y !== k.id) : [...x.kernels, k.id]; if (!x.kernels.length) x.kernels = [k.id]; });
      LS.$$('[id^="k-"]', kernels).forEach(e => e.classList.toggle('sel', S.cfg.kernels.includes(e.id.slice(2))));
    } });
    kernels.append(card);
  });
  el.append(panel('Boot loader', choices, h('div', { class: 'grid2', style: { marginTop: '14px' } },
      W.field('Menu timeout', W.slider({ min: 0, max: 10, value: c.bootloader.timeout, id: 'adv-timeout', format: v => v ? `${v} s` : 'Hidden', onInput: v => LS.set(x => { x.bootloader.timeout = v; }) })),
      W.toggle({ title: 'Detect other systems', desc: 'Add Windows and other OSes to the GRUB menu (os-prober)', value: c.bootloader.os_prober, onChange: v => LS.set(x => { x.bootloader.os_prober = v; }) }))),
    panel('Kernels', h('p', { class: 'small mut', style: { margin: '0 0 12px' } }, 'Install one or several; each gets its own boot menu entry.'), kernels,
      h('div', { class: 'grid2', style: { marginTop: '14px' } },
        W.toggle({ title: 'Kernel headers', desc: 'Needed to build modules (DKMS, VirtualBox)', value: c.headers, onChange: v => LS.set(x => { x.headers = v; }) }),
        W.field('Kernel parameters', W.input({ id: 'adv-params', value: c.kernel_params, placeholder: 'loglevel=3 quiet', onInput: v => LS.set(x => { x.kernel_params = v; }) })))));
});

/* ================================================================ users */
section('users', (el) => {
  const list = h('div', { class: 'stack' });
  const draw = () => {
    list.textContent = '';
    S.cfg.users.forEach((u, i) => list.append(h('div', { class: 'act', style: { padding: '12px 14px' } },
      h('div', { class: 'ti', style: { width: '38px', height: '38px', borderRadius: '50%', background: 'var(--grad)', display: 'grid', placeItems: 'center', fontWeight: 800 } }, (u.fullname || u.username || '?')[0].toUpperCase()),
      h('div', { class: 'grow' }, h('b', {}, u.username || '(no username)'), ' ', h('span', { class: 'mut small' }, u.fullname)),
      u.sudo ? h('span', { class: 'chip green' }, 'admin') : null, u.autologin ? h('span', { class: 'chip blue' }, 'autologin') : null, h('span', { class: 'chip' }, u.shell),
      h('button', { class: 'btn ghost sm', onclick: () => userDialog(i, draw) }, icon('edit'), 'Edit'),
      h('button', { class: 'btn ghost sm', onclick: () => { LS.set(x => { x.users.splice(i, 1); }); draw(); } }, icon('trash')))));
    if (!S.cfg.users.length) list.append(W.note('info', 'No users yet. Add at least one administrator.'));
  };
  draw();
  const rootPw = W.password({ id: 'root-pw', value: S.cfg.root.password, placeholder: 'Leave empty to lock root', onInput: v => LS.set(x => { x.root.password = v; x.root.lock = !v; }) });
  el.append(panel(null, h('div', { class: 'row', style: { marginBottom: '12px' } }, h('h3', { class: 'grow', style: { margin: 0 } }, 'Users'),
      h('button', { class: 'btn sm', id: 'add-user', onclick: () => userDialog(-1, draw) }, icon('plus'), 'Add user')), list),
    panel('Root account', h('p', { class: 'small mut', style: { margin: '0 0 10px' } }, 'Most people never need root directly: administrators use sudo. With no password, root login is locked.'), rootPw));
});

function userDialog(i, redraw) {
  const u = i >= 0 ? { ...S.cfg.users[i] } : Object.assign(LS.clone(S.boot.default_user), { sudo: true });
  let pw2 = u.password;
  const fUser = W.field('Username', W.input({ id: 'ud-username', value: u.username, onInput: v => { u.username = v.trim(); fUser.error(u.username && !/^[a-z_][a-z0-9_-]{0,31}$/.test(u.username) ? 'Lowercase letters, digits, - and _' : ''); } }));
  const fPw2 = W.field('Repeat password', W.password({ id: 'ud-password2', value: pw2, onInput: v => { pw2 = v; fPw2.error(pw2 !== u.password ? 'Passwords don\'t match' : ''); } }));
  const body = h('div', { class: 'form' },
    W.field('Full name', W.input({ id: 'ud-fullname', value: u.fullname, onInput: v => { u.fullname = v; } })), fUser,
    W.field('Password', W.password({ id: 'ud-password', value: u.password, meter: true, onInput: v => { u.password = v; } })), fPw2,
    W.field('Shell', W.seg(S.boot.catalog.shells.map(s => ({ id: s, label: s })), u.shell, v => { u.shell = v; })), h('div'),
    W.toggle({ title: 'Administrator', desc: 'Can use sudo', value: u.sudo, onChange: v => { u.sudo = v; } }),
    W.toggle({ title: 'Log in automatically', value: u.autologin, onChange: v => { u.autologin = v; } }));
  LS.dialog({ title: i >= 0 ? `Edit ${u.username}` : 'Add a user', body, wide: true, actions: [{ label: 'Cancel' }, { label: 'Save', kind: '', id: 'ud-ok', icon: 'check', onClick: () => {
    if (!u.username || !u.password) { LS.toast('A username and a password are needed.', 'warn'); return true; }
    if (pw2 !== u.password) { LS.toast('Passwords don\'t match.', 'warn'); return true; }
    LS.set(x => { if (u.autologin) x.users.forEach(y => { y.autologin = false; }); if (i >= 0) x.users[i] = u; else x.users.push(u); });
    redraw();
  } }] });
}

/* ================================================================ desktop */
section('desktop', (el, ctx) => {
  const c = S.cfg;
  const groups = [['desktop', 'Desktops'], ['wm', 'Window managers'], ['other', 'No desktop']];
  const cards = {};
  const ICON = { desktop: 'monitor', wm: 'layers', other: 'terminal' };
  groups.forEach(([kind, title]) => {
    const grid = h('div', { class: 'cards' });
    cat().profiles.filter(p => p.kind === kind).forEach(p => {
      cards[p.id] = W.card({ icon: ICON[kind], title: p.name, desc: p.blurb, id: 'pf-' + p.id, sel: c.profiles.includes(p.id), onClick: () => {
        const kindOf = id => (cat().profiles.find(q => q.id === id) || {}).kind;
        const apply = fn => { LS.set(fn); Object.entries(cards).forEach(([id, cd]) => cd.set(S.cfg.profiles.includes(id))); };
        const on = S.cfg.profiles.includes(p.id);
        const desktops = S.cfg.profiles.filter(y => kindOf(y) !== 'other');
        if (kind === 'other' && !on && desktops.length) {
          // "No desktop" removes the chosen desktops: never do that silently.
          LS.dialog({ title: `Switch to ${p.name}?`,
            lead: `This removes ${desktops.map(profileName).join(' and ')}. The new system will boot to a text console with no graphical desktop.`,
            actions: [{ label: 'Keep my desktop' },
              { label: 'Yes, no desktop', kind: 'danger', id: 'pf-confirm', onClick: () => apply(x => { x.profiles = [p.id]; }) }] });
          return;
        }
        apply(x => {
          if (kind === 'other') x.profiles = on ? [] : [p.id];
          else x.profiles = on ? x.profiles.filter(y => y !== p.id) : [...x.profiles.filter(y => kindOf(y) !== 'other'), p.id];
        });
      } });
      grid.append(cards[p.id]);
    });
    el.append(panel(title, grid));
  });
  const hw = S.boot.hardware;
  const detected = hw.gpus.map(g => g.name).join(', ') || (hw.virt ? `Virtual machine (${hw.virt})` : 'Nothing special detected');
  el.append(panel('Login, graphics and sound', h('div', { class: 'form' },
    W.field('Login screen', W.combo({ id: 'adv-greeter', value: c.greeter, search: false, options: [{ id: 'auto', label: 'Automatic (best for your desktop)' }, ...cat().greeters], onChange: v => LS.set(x => { x.greeter = v; }) })),
    W.field('Graphics driver', W.combo({ id: 'adv-graphics', value: c.graphics, search: false, options: cat().graphics, onChange: v => LS.set(x => { x.graphics = v; }) }), { help: 'Detected: ' + detected }),
    W.field('Sound', W.seg(cat().audio.map(a => ({ id: a.id, label: a.label })), c.audio, v => LS.set(x => { x.audio = v; }))),
    hw.virt ? W.toggle({ title: 'Virtual machine tools', desc: 'Clipboard sharing and auto-resize', value: c.vm_tools, onChange: v => LS.set(x => { x.vm_tools = v; }) }) : h('div'),
    W.toggle({ title: 'Bluetooth', value: c.bluetooth, id: 'adv-bt', onChange: v => LS.set(x => { x.bluetooth = v; }) }),
    W.toggle({ title: 'Printing', desc: 'CUPS + network printer discovery', value: c.printing, id: 'adv-print', onChange: v => LS.set(x => { x.printing = v; }) }))));
});

/* ================================================================ software */
section('software', (el) => {
  cat().software.forEach(group => {
    const chips = h('div', { class: 'cards' });
    group.items.forEach(it => {
      const card = W.card({ title: it.name, desc: it.desc, id: 'sw-' + it.id, sel: S.cfg.software.includes(it.id), onClick: () => {
        LS.set(x => { x.software = x.software.includes(it.id) ? x.software.filter(y => y !== it.id) : [...x.software, it.id]; });
        card.set(S.cfg.software.includes(it.id));
      } });
      card.title = it.packages.join(' ');
      card.style.padding = '16px';
      chips.append(card);
    });
    el.append(panel(group.category, chips));
  });
  const added = h('div', { class: 'chips' });
  const drawAdded = () => {
    added.textContent = '';
    S.cfg.extra_packages.forEach(p => added.append(h('span', { class: 'chip sel' }, p, h('span', { class: 'x', onclick: () => { LS.set(x => { x.extra_packages = x.extra_packages.filter(y => y !== p); }); drawAdded(); } }, icon('x')))));
    if (!S.cfg.extra_packages.length) added.append(h('span', { class: 'mut small' }, 'None yet'));
  };
  drawAdded();
  const results = h('div', { class: 'stack', style: { marginTop: '10px', maxHeight: '300px', overflow: 'auto' } });
  const search = LS.debounce(async q => {
    results.textContent = '';
    if (q.length < 2) return;
    results.append(h('div', { class: 'row mut' }, h('span', { class: 'spin' }), 'Searching…'));
    const res = await LS.call('search_packages', q);
    results.textContent = '';
    if (!res.length) results.append(h('div', { class: 'mut small' }, 'No packages found.'));
    res.forEach(r => results.append(h('div', { class: 'act' }, h('div', { class: 'grow' }, h('b', {}, r.name), ' ', h('span', { class: 'mut small' }, `${r.repo} · ${r.version}`), h('div', { class: 'small mut' }, r.desc)),
      h('button', { class: 'btn sm ' + (S.cfg.extra_packages.includes(r.name) ? 'ghost' : ''), onclick: e => {
        if (!S.cfg.extra_packages.includes(r.name)) { LS.set(x => { x.extra_packages.push(r.name); }); drawAdded(); e.currentTarget.classList.add('ghost'); }
      } }, icon('plus'), 'Add'))));
  }, 350);
  const q = W.input({ id: 'pkg-search', placeholder: 'Search the Arch repositories…', onInput: v => search(v.trim()) });
  el.append(panel('Any other package', added, h('div', { style: { marginTop: '12px' } }, q), results),
    panel('More sources', h('div', { class: 'grid2' },
      W.toggle({ title: 'Flatpak + Flathub', desc: 'Thousands of sandboxed apps', value: S.cfg.flatpak, id: 'adv-flatpak', onChange: v => LS.set(x => { x.flatpak = v; }) }),
      W.field('AUR helper', W.seg(cat().aur_helpers.map(a => ({ id: a.id, label: a.label })), S.cfg.aur_helper, v => LS.set(x => { x.aur_helper = v; })),
        { help: 'Built from the AUR as your admin user. Optional: the install continues if it fails.' }))));
});

/* ================================================================ system */
section('system', (el) => {
  const c = S.cfg;
  const sizeRow = W.field('Swap size', W.slider({ min: 0.5, max: 32, step: 0.5, value: c.swap.size_gb, id: 'adv-swapsize', format: v => `${v} GB`, onInput: v => LS.set(x => { x.swap.size_gb = v; }) }));
  sizeRow.classList.toggle('hidden', c.swap.mode === 'none');
  const svcIn = W.input({ id: 'svc-in', placeholder: 'e.g. cronie or libvirtd.socket' });
  const svcs = h('div', { class: 'chips' });
  const drawSvcs = () => { svcs.textContent = ''; S.cfg.services.forEach(s => svcs.append(h('span', { class: 'chip sel' }, s, h('span', { class: 'x', onclick: () => { LS.set(x => { x.services = x.services.filter(y => y !== s); }); drawSvcs(); } }, icon('x'))))); };
  drawSvcs();
  svcIn.addEventListener('keydown', e => { if (e.key === 'Enter' && svcIn.value.trim()) { const v = svcIn.value.trim(); LS.set(x => { if (!x.services.includes(v)) x.services.push(v); }); svcIn.value = ''; drawSvcs(); } });
  const ta = h('textarea', { class: 'input', id: 'custom-cmds', placeholder: '# runs inside the new system as root, after everything else\nsystemctl enable cronie' });
  ta.value = c.custom_commands;
  ta.addEventListener('input', () => LS.set(x => { x.custom_commands = ta.value; }));
  el.append(
    panel('Identity', W.field('Computer name (hostname)', W.input({ id: 'adv-hostname', value: c.hostname, onInput: v => LS.set(x => { x.hostname = v.trim(); }) }))),
    panel('Swap', W.seg([{ id: 'zram', label: 'zram (RAM compression)' }, { id: 'swapfile', label: 'Swap file' }, { id: 'partition', label: 'Swap partition' }, { id: 'none', label: 'None' }],
      c.swap.mode, v => { LS.set(x => { x.swap.mode = v; }); sizeRow.classList.toggle('hidden', v === 'none'); }, 'adv-swap'), h('div', { style: { marginTop: '12px' } }, sizeRow)),
    panel('Security & services', h('div', { class: 'stack' },
      W.field('Firewall', W.seg(cat().firewalls.map(f => ({ id: f.id, label: f.label })), c.firewall, v => LS.set(x => { x.firewall = v; }), 'adv-firewall')),
      W.toggle({ title: 'SSH server', desc: 'Log in to this computer remotely (openssh)', value: c.ssh, id: 'adv-ssh', onChange: v => LS.set(x => { x.ssh = v; }) }),
      W.field('Also enable these services (press Enter to add)', h('div', { class: 'stack' }, svcIn, svcs)))),
    panel('After installing', W.field('When it\'s done', W.seg([{ id: 'none', label: 'Wait for me' }, { id: 'reboot', label: 'Restart' }, { id: 'poweroff', label: 'Power off' }], c.finish, v => LS.set(x => { x.finish = v; }), 'adv-finish')),
      h('div', { style: { marginTop: '14px' } }, W.field('Custom commands', ta, { help: 'A bash script run inside the new system at the very end. If it fails you get a warning, not a broken install.' }))));
});
})();
