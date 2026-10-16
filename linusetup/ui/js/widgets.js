/* Reusable controls. Each returns a DOM element; controls that can change
   from outside expose el.set(value). */
'use strict';
(() => {
const { h, icon } = LS;
const W = LS.w = {};
const MiB = 1024 * 1024;

W.seg = function seg(options, value, onChange, id) {
  const el = h('div', { class: 'seg', id });
  const draw = v => {
    el.textContent = '';
    options.forEach(o => {
      const b = h('button', { class: o.id === v ? 'on' : '', title: o.title || '', 'data-id': o.id }, o.label);
      if (o.disabled) b.disabled = true;
      b.addEventListener('click', () => { if (o.id !== v) { draw(o.id); onChange(o.id); } });
      el.append(b);
    });
  };
  draw(value); el.set = draw; return el;
};

W.toggle = function toggle({ title, desc, value, onChange, disabled, id }) {
  const el = h('div', { class: 'toggle' + (value ? ' on' : '') + (disabled ? ' off' : ''), id, role: 'switch', tabindex: 0 },
    h('div', { class: 't' }, h('b', {}, title), desc ? h('small', {}, desc) : null), h('div', { class: 'sw' }));
  const flip = () => { value = !value; el.classList.toggle('on', value); onChange(value); };
  el.addEventListener('click', flip);
  el.addEventListener('keydown', e => { if (e.key === ' ' || e.key === 'Enter') { e.preventDefault(); flip(); } });
  el.set = v => { value = v; el.classList.toggle('on', !!v); };
  return el;
};

W.field = function field(label, control, opts = {}) {
  const msg = h('div', { class: 'msg' });
  const el = h('div', { class: 'field' + (opts.wide ? ' wide' : ''), id: opts.id }, label ? h('label', {}, label) : null, control,
    opts.help ? h('div', { class: 'help' }, opts.help) : null, msg);
  el.error = text => { el.classList.toggle('err', !!text); msg.textContent = text || ''; };
  return el;
};

W.input = function input({ value = '', placeholder = '', type = 'text', onInput, id, maxlength }) {
  const el = h('input', { class: 'input', type, placeholder, id, autocomplete: 'off', spellcheck: 'false', maxlength });
  el.value = value;
  el.addEventListener('input', () => onInput && onInput(el.value));
  return el;
};

W.strength = function strength(pw) {
  let s = 0;
  if (pw.length >= 6) s++; if (pw.length >= 10) s++;
  if (/[A-Z]/.test(pw) && /[a-z]/.test(pw)) s++;
  if (/\d/.test(pw) && /[^\w]/.test(pw)) s++;
  return s;
};

W.password = function password({ value = '', onInput, id, meter, placeholder = '' }) {
  const inp = h('input', { class: 'input', type: 'password', id, autocomplete: 'new-password', placeholder });
  inp.value = value;
  const eye = h('button', { class: 'eye', type: 'button', title: 'Show / hide', tabindex: -1 }, icon('eye'));
  eye.addEventListener('click', () => { inp.type = inp.type === 'password' ? 'text' : 'password'; });
  const wrap = h('div', { class: 'pw' }, inp, eye);
  const el = h('div', { class: 'stack', style: { gap: '6px' } }, wrap);
  let bar;
  if (meter) { bar = h('i'); el.append(h('div', { class: 'meter' }, bar)); }
  const draw = () => {
    if (!bar) return;
    const s = W.strength(inp.value);
    bar.style.transform = `scaleX(${inp.value ? Math.max(.1, (s + 1) / 5) : 0})`;
    bar.style.background = ['#f87171', '#f87171', '#fbbf24', '#34d399', '#22d3ee'][s];
  };
  inp.addEventListener('input', () => { draw(); onInput && onInput(inp.value); });
  draw();
  el.input = inp;
  return el;
};

W.slider = function slider({ min, max, step = 1, value, format = v => v, onInput, id }) {
  const r = h('input', { type: 'range', min, max, step, id });
  r.value = value;
  const out = h('span', { class: 'val' }, format(+value));
  r.addEventListener('input', () => { out.textContent = format(+r.value); onInput && onInput(+r.value); });
  const el = h('div', { class: 'slider' }, r, out);
  el.set = v => { r.value = v; out.textContent = format(+v); };
  el.range = r;
  return el;
};

/* A button that opens a searchable list. options: [{id, label, hint}] */
W.combo = function combo({ options, value, onChange, placeholder = 'Choose…', id, search = true }) {
  const btn = h('button', { class: 'combo-btn', type: 'button', id });
  const draw = v => { const o = options.find(x => x.id === v); btn.textContent = o ? o.label : placeholder; value = v; };
  draw(value);
  btn.addEventListener('click', () => {
    const r = btn.getBoundingClientRect();
    const ov = h('div', { style: { position: 'fixed', inset: 0, zIndex: 59 } });
    const below = innerHeight - r.bottom > 260 || r.top < 260;
    const pop = h('div', { class: 'pop', style: { left: r.left + 'px', width: Math.max(r.width, 240) + 'px',
      [below ? 'top' : 'bottom']: (below ? r.bottom + 6 : innerHeight - r.top + 6) + 'px' } });
    const q = h('input', { class: 'input', placeholder: 'Search…', autocomplete: 'off' });
    const list = h('div', { class: 'opts' });
    let act = 0, shown = [];
    const close = () => { ov.remove(); pop.remove(); btn.focus(); };
    const pick = o => { draw(o.id); close(); onChange(o.id); };
    const render = () => {
      const term = q.value.trim().toLowerCase();
      shown = options.filter(o => !term || o.label.toLowerCase().includes(term) || String(o.id).toLowerCase().includes(term)).slice(0, 250);
      act = Math.max(0, Math.min(act, shown.length - 1));
      list.textContent = '';
      shown.forEach((o, i) => {
        const row = h('div', { class: 'opt' + (o.id === value ? ' on' : '') + (i === act ? ' act' : '') }, h('span', {}, o.label), o.hint ? h('small', {}, o.hint) : null);
        row.addEventListener('click', () => pick(o));
        list.append(row);
      });
      if (!shown.length) list.append(h('div', { class: 'opt mut' }, 'No matches'));
    };
    q.addEventListener('input', () => { act = 0; render(); });
    q.addEventListener('keydown', e => {
      if (e.key === 'ArrowDown') { act++; render(); e.preventDefault(); }
      else if (e.key === 'ArrowUp') { act--; render(); e.preventDefault(); }
      else if (e.key === 'Enter' && shown[act]) { e.preventDefault(); pick(shown[act]); }
      else if (e.key === 'Escape') { e.stopPropagation(); close(); }
    });
    ov.addEventListener('mousedown', close);
    if (search) pop.append(q);
    pop.append(list);
    document.body.append(ov, pop);
    act = Math.max(0, options.findIndex(o => o.id === value));
    render();
    const cur = list.querySelector('.on'); cur && cur.scrollIntoView({ block: 'center' });
    if (search) q.focus();
  });
  btn.set = draw;
  return btn;
};

/* Selected values as removable chips + a combo to add more. */
W.multi = function multi({ options, values, onChange, placeholder = 'Add…', id }) {
  const el = h('div', { class: 'stack', id });
  const chips = h('div', { class: 'chips' });
  const draw = () => {
    chips.textContent = '';
    values.forEach(v => {
      const o = options.find(x => x.id === v) || { label: v };
      const x = h('span', { class: 'x' }, icon('x'));
      x.addEventListener('click', () => { values = values.filter(y => y !== v); draw(); onChange(values); });
      chips.append(h('span', { class: 'chip sel' }, o.label, x));
    });
    if (!values.length) chips.append(h('span', { class: 'mut small' }, 'None selected'));
  };
  const add = W.combo({ options, value: null, placeholder, onChange: v => { if (!values.includes(v)) { values = [...values, v]; draw(); onChange(values); } add.set(null); } });
  draw();
  el.append(chips, add);
  return el;
};

W.card = function card({ icon: ic, title, desc, sel, onClick, tag, off, center, id, offReason }) {
  const el = h('div', { class: 'card st' + (sel ? ' sel' : '') + (off ? ' off' : '') + (center ? ' center' : ''), id, title: off ? offReason || '' : '' },
    h('span', { class: 'shine' }),
    tag ? h('span', { class: 'tag' }, tag) : null,
    h('div', { class: 'tick' }, icon('check')),
    ic ? h('div', { class: 'cico' }, icon(ic)) : null, h('b', {}, title), desc ? h('small', {}, desc) : null);
  if (!off) el.addEventListener('click', () => onClick && onClick(el));
  el.set = v => el.classList.toggle('sel', !!v);
  return el;
};

W.choice = function choice({ title, desc, sel, off, onClick, extra, id }) {
  const el = h('div', { class: 'choice' + (sel ? ' sel' : '') + (off ? ' off' : ''), id },
    h('div', { class: 'radio' }), h('div', { class: 'grow' }, h('b', {}, title), desc ? h('small', {}, desc) : null, extra ? h('div', { class: 'extra' }, extra) : null));
  if (!off) el.addEventListener('click', e => { if (!e.target.closest('.extra')) onClick(); });
  return el;
};

W.note = (kind, text) => h('div', { class: 'note ' + kind }, icon(kind === 'err' || kind === 'warn' ? 'warn' : kind === 'ok' ? 'check' : 'info'), h('div', {}, text));

W.signal = n => h('span', { class: 'signal' }, [1, 2, 3, 4].map(i => h('i', { class: i <= n ? 'on' : '', style: { height: (i * 3 + 2) + 'px' } })));

/* ---------- disks ---------- */
const KIND_LABEL = { esp: 'EFI', msr: 'MSR', windows: 'Windows', recovery: 'Recovery', linux: 'Linux', swap: 'Swap', luks: 'Encrypted',
  bios: 'BIOS', bitlocker: 'BitLocker', other: 'Other', data: 'Data', free: 'Free', new: 'New', delete: 'Delete' };
W.KIND_LABEL = KIND_LABEL;

/* Free gaps between segments, 1 MiB aligned, like disks.Disk.free_regions. */
LS.freeRegions = function freeRegions(size, parts, min = 16 * MiB) {
  const end = Math.floor((size - MiB) / MiB) * MiB;
  const sorted = parts.slice().sort((a, b) => a.start - b.start);
  const out = []; let cur = MiB;
  for (const p of [...sorted, null]) {
    const lim = p ? p.start : end;
    const s = Math.ceil(cur / MiB) * MiB, e = Math.floor(lim / MiB) * MiB;
    if (e - s >= min) out.push({ start: s, end: e, size: e - s });
    if (p) cur = Math.max(cur, p.start + p.size);
  }
  return out;
};

/* segments: [{start,size,kind,label,id}] ; gaps are filled in as free space. */
W.diskBar = function diskBar(size, segments, { onSeg, current, showFree = true } = {}) {
  const el = h('div', { class: 'dbar' });
  const all = segments.map(s => ({ ...s }));
  if (showFree) LS.freeRegions(size, segments, 512 * MiB).forEach(f => all.push({ start: f.start, size: f.size, kind: 'free', label: 'Free ' + LS.gb(f.size), free: true }));
  all.sort((a, b) => a.start - b.start);
  all.forEach(s => {
    const pct = s.size / size;
    const seg = h('div', { class: 'sg k-' + s.kind + (onSeg ? ' click' : '') + (current && current === s.id ? ' cur' : ''),
      title: (s.label || KIND_LABEL[s.kind] || '') + ' · ' + LS.gb(s.size), style: { flexGrow: Math.max(pct, .012) } },
    pct > .07 ? h('span', {}, s.label || KIND_LABEL[s.kind]) : null);
    if (onSeg) seg.addEventListener('click', () => onSeg(s));
    el.append(seg);
  });
  return el;
};
W.legend = kinds => h('div', { class: 'legend' }, [...new Set(kinds)].map(k => h('span', {}, h('i', { class: 'k-' + k }), KIND_LABEL[k] || k)));

W.diskCard = function diskCard(d, { sel, onClick, compact } = {}) {
  const segs = d.partitions.map(p => ({ start: p.start, size: p.size, kind: p.kind, label: p.label || KIND_LABEL[p.kind] }));
  const meta = [d.path, LS.gb(d.size), (d.transport || (d.rotational ? 'HDD' : 'SSD')).toUpperCase(), d.removable ? 'removable' : null,
    d.pttype === 'dos' ? 'MBR' : d.pttype ? 'GPT' : 'empty'].filter(Boolean).join(' · ');
  const chips = h('div', { class: 'chips', style: { marginTop: '8px' } });
  if (!d.usable) chips.append(h('span', { class: 'chip red' }, d.reason));
  if (d.has_windows) chips.append(h('span', { class: 'chip blue' }, icon('windows'), 'Windows'));
  if (d.partitions.some(p => p.kind === 'bitlocker')) chips.append(h('span', { class: 'chip yellow' }, icon('lock'), 'BitLocker'));
  if (d.partitions.some(p => p.kind === 'linux' || p.kind === 'luks')) chips.append(h('span', { class: 'chip green' }, 'Linux'));
  if (!d.partitions.length && d.usable) chips.append(h('span', { class: 'chip' }, 'Empty'));
  const el = h('div', { class: 'disk st' + (sel ? ' sel' : '') + (d.usable ? '' : ' off'), 'data-path': d.path },
    h('div', { class: 'dh' }, h('div', { class: 'dico' }, icon('disk')),
      h('div', { class: 'dm' }, h('b', {}, d.model), h('small', {}, meta), chips), h('div', { class: 'tick' }, icon('check'))),
    compact ? null : W.diskBar(d.size, segs));
  if (d.usable) el.addEventListener('click', () => onClick && onClick(d));
  return el;
};
})();
