"""probes.py — the JavaScript the harness evaluates inside the page.

Two blobs, run by visual_review.py through Playwright's page.evaluate():

  RUN_PROBE_JS    run-level facts, read once per run from a cold page
  STATE_PROBE_JS  per-state geometry of the rendered SVG and the sidebar panels

They are strings on purpose: they execute in Chromium, not in Python, so nothing in
this module may import anything or be called from Python. I18N_KEYS travels with them
because it names the keys RUN_PROBE_JS reads out of the page.

Reference: docs/data-contract.md (the viewer's DOM and data contract).
"""
# ---------------------------------------------------------------- JS probes
# Run-level facts, read once per run from a cold page so they do not depend on --states.
RUN_PROBE_JS = r"""
() => {
  const DATA = JSON.parse(document.getElementById('data').textContent);
  const F = DATA.files || [], META = DATA.meta || {};
  const EPS = DATA.entry_points || [], UCS = DATA.ucs || [], CALLS = DATA.calls || {};
  const mutedIds = new Set((META.categories || []).filter(c => c.muted).map(c => c.id));
  const vis = [];
  for (let i = 0; i < F.length; i++) if (!mutedIds.has(F[i].g)) vis.push(i);
  const callsOf = i => CALLS[String(i)] || {n: [], x: []};

  let ci = 0, cx = 0;
  for (const k of Object.keys(CALLS)) {
    ci += (CALLS[k].n || []).length;
    cx += (CALLS[k].x || []).length;
  }
  const data = {
    files: F.length, imports: (DATA.imports || []).length, ucs: UCS.length,
    entry_points: EPS.length, calls_files: Object.keys(CALLS).length,
    calls_internal: ci, calls_cross: cx, lang: META.lang || 'en'
  };

  const KINDS = ['http', 'command', 'event', 'cli', 'cron', 'other'];
  const by_kind = {};
  KINDS.forEach(k => by_kind[k] = 0);
  for (const ep of EPS) by_kind[by_kind[ep.kind] === undefined ? 'other' : ep.kind]++;

  const STATUSES = ['human-verified', 'agent-verified', 'inferred', 'hypothesis', 'outdated'];
  const by_status = {};
  STATUSES.forEach(s => by_status[s] = 0);
  let hops_total = 0;
  for (const u of UCS) {
    hops_total += (u.hops || []).length;
    if (by_status[u.status] !== undefined) by_status[u.status]++;
  }

  // Star rows are read as numbers, never as words: "calls" is "cham" in pt-BR.
  const starEls = Array.from(document.querySelectorAll('#starlist .star'));
  let zero_rows = 0;
  for (const b of starEls) {
    const el = b.querySelector('.starnums');
    const nums = ((el ? el.textContent : '') || '').match(/\d+/g) || [];
    const n = nums.map(Number);
    if (n.length >= 4 && n[0] === 0 && n[2] === 0 && n[3] === 0) zero_rows++;
  }

  const chips = Array.from(document.querySelectorAll('#legend .chip'));

  // The contract's "a color defined in only one theme block is a bug", checked directly.
  const norm = s => (s || '').replace(/\s+/g, '');
  const buckets = {root: new Set(), media_dark: new Set(), attr_dark: new Set()};
  function walk(rules, inDark) {
    for (const r of rules) {
      if (r.cssRules && (r.conditionText !== undefined || r.media)) {
        const cond = norm(r.conditionText || (r.media && r.media.mediaText) || '');
        walk(r.cssRules, inDark || /prefers-color-scheme:dark/.test(cond));
      } else if (r.style && r.selectorText) {
        const names = Array.from(r.style).filter(n => n.startsWith('--'));
        if (!names.length) continue;
        const sel = norm(r.selectorText).replace(/'/g, '"');
        let b = null;
        if (sel === ':root' && !inDark) b = buckets.root;
        else if (inDark && sel === ':root:not([data-theme="light"])') b = buckets.media_dark;
        else if (sel === ':root[data-theme="dark"]') b = buckets.attr_dark;
        if (b) names.forEach(n => b.add(n));
      }
    }
  }
  for (const sheet of Array.from(document.styleSheets)) {
    try { walk(sheet.cssRules, false); } catch (e) { /* cross-origin sheet */ }
  }
  const all = new Set([...buckets.root, ...buckets.media_dark, ...buckets.attr_dark]);
  const missing = [...all].filter(
    n => !(buckets.root.has(n) && buckets.media_dark.has(n) && buckets.attr_dark.has(n))).sort();

  const txt = (sel, attr) => {
    const e = document.querySelector(sel);
    if (!e) return null;
    return attr ? e.getAttribute(attr) : (e.textContent || '').trim();
  };
  const strings = {
    search_placeholder: txt('#search', 'placeholder'),
    toggle_stars: txt('#starstgl span'),
    panel_entry_points: txt('#ephdr span[data-t]'),
    panel_stars: txt('#starhdr span[data-t]'),
    panel_usecases: txt('#uchdr span[data-t]'),
    crumb_context: txt('#bctx'),
    crumb_packages: txt('#bpac'),
    hint: txt('#hint'),
    map_aria: txt('#map', 'aria-label'),
    detail_title: txt('#dtitle'),
    detail_empty: txt('#dbody .empty'),
    uc_export: txt('#sidebar [data-exportst]'),
    zoom_fit_title: txt('#zfit', 'title')
  };

  // --- derived selection: never a hardcoded repo path (principle 4) ---
  let focus = -1, bScore = -1, bX = -1;
  for (const i of vis) {
    const c = callsOf(i);
    const s = (c.n || []).length + (c.x || []).length, x = (c.x || []).length;
    if (s > bScore || (s === bScore && x > bX)) { bScore = s; bX = x; focus = i; }
  }
  const ucBy = new Map();
  for (const u of UCS) {
    const seen = new Set((u.hops || []).map(h => h.i));
    for (const i of seen) ucBy.set(i, (ucBy.get(i) || 0) + 1);
  }
  let rev = -1, bRev = -1;
  for (const i of vis) {
    const c = ucBy.get(i) || 0;
    if (c > bRev) { bRev = c; rev = i; }
  }
  let uc = -1, bHops = -1;
  UCS.forEach((u, j) => {
    const n = (u.hops || []).length;
    if (n > bHops) { bHops = n; uc = j; }
  });
  const seg = {};
  for (const i of vis) {
    const p = F[i].p || '';
    if (p.indexOf('/') < 0) continue;
    const s0 = p.split('/')[0];
    seg[s0] = (seg[s0] || 0) + 1;
  }
  let query = '', bSeg = -1;
  for (const k of Object.keys(seg).sort()) if (seg[k] > bSeg) { bSeg = seg[k]; query = k; }
  const epb = document.querySelector('#eplist .ep');
  const first_entry_point = epb
    ? ((epb.firstChild ? epb.firstChild.textContent : epb.textContent) || '').trim() : null;

  const focusFile = focus >= 0 ? F[focus] : null;
  return {
    selection: {
      focus: focus, focus_path: focusFile ? focusFile.p : null,
      rev: rev, rev_path: rev >= 0 ? F[rev].p : null,
      uc: uc, uc_name: uc >= 0 ? UCS[uc].name : null,
      query: query, first_entry_point: first_entry_point
    },
    data: data,
    entry_points: {total: EPS.length, by_kind: by_kind},
    usecases: {count: UCS.length, hops_total: hops_total, by_status: by_status},
    stars: {
      rows: starEls.length, zero_rows: zero_rows,
      first_row_path: starEls.length ? starEls[0].getAttribute('title') : null
    },
    legend: {items: chips.length, labels: chips.map(c => (c.textContent || '').trim())},
    theme_tokens: {
      root: buckets.root.size, media_dark: buckets.media_dark.size,
      attr_dark: buckets.attr_dark.size, missing_in_some_block: missing
    },
    i18n: {strings: strings},
    _pre: {
      entry_points: EPS.length,
      uc_hops: bHops,
      focus_symbols: focusFile ? (focusFile.c || []).length + (focusFile.f || []).length : 0,
      query_len: query.length
    }
  };
}
"""

# Per-state facts, read after the state has been driven.
STATE_PROBE_JS = r"""
() => {
  const world = document.getElementById('world');
  const q = sel => world.querySelectorAll(sel).length;
  const r1 = v => Math.round(v * 10) / 10;
  let bb = {x: 0, y: 0, width: 0, height: 0};
  try { bb = world.getBBox(); } catch (e) { /* empty scene */ }
  const w = r1(bb.width), h = r1(bb.height);

  const svg = {
    nodes: q('.node'), nodes_dimmed: q('.node.dimmed'), nodes_selected: q('.node.sel'),
    nodes_hit: q('.node.hit'), clusters: q('.cluster'), cluster_labels: q('.clabel'),
    halos: q('.halo'),
    ctx_boxes: q('.ctxbox'), ctx_boxes_dimmed: q('.ctxbox.dimmed'), ctx_labels: q('.ctxlabel'),
    agg_edges: q('.aggedge'),
    flow_nodes: q('.flownode'), flow_lines: q('.flowline'), flow_badges: q('.fbadge'),
    class_boxes: q('.classbox'), pills: q('.pill'), pills_selected: q('.pill.sel'),
    pills_dimmed: q('.pill.dimmed'), stubs: q('.stub'), call_edges: q('.calledge'),
    import_edges_out: q('.edge-out'), import_edges_in: q('.edge-in'),
    total_elements: q('*')
  };

  const box = el => {
    try { const b = el.getBBox(); return {x: b.x, y: b.y, w: b.width, h: b.height}; }
    catch (e) { return null; }
  };
  const pairs = [];
  const cl = Array.from(world.querySelectorAll('.cluster'));
  const cla = Array.from(world.querySelectorAll('.clabel'));
  if (cl.length && cl.length === cla.length) {
    for (let i = 0; i < cl.length; i++) pairs.push([cl[i], cla[i]]);
  } else {
    // Pair inside each cluster group; this correctly leaves out the entry-point lens
    // label, which is a .ctxlabel drawn outside any [data-ck] group.
    for (const g of world.querySelectorAll('[data-ck]')) {
      const b = g.querySelector('.ctxbox'), l = g.querySelector('.ctxlabel');
      if (b && l) pairs.push([b, l]);
    }
  }
  let overrun_count = 0, overrun_max_px = 0, overrun_worst = null;
  const lbs = [];
  for (const [b, l] of pairs) {
    const bb2 = box(b), lb = box(l);
    if (!bb2 || !lb) continue;
    lbs.push(lb);
    const o = (lb.x + lb.w) - (bb2.x + bb2.w);
    if (o > 0.5) {
      overrun_count++;
      if (o > overrun_max_px) { overrun_max_px = o; overrun_worst = (l.textContent || '').trim(); }
    }
  }
  let overlap_pairs = 0;
  for (let i = 0; i < lbs.length; i++) for (let j = i + 1; j < lbs.length; j++) {
    const a = lbs[i], b2 = lbs[j];
    if (a.x < b2.x + b2.w && b2.x < a.x + a.w && a.y < b2.y + b2.h && b2.y < a.y + a.h) overlap_pairs++;
  }

  const crumbEls = Array.from(document.querySelectorAll('#crumbs button'));
  // ONE notion of "visible" for the whole probe, and the same one Playwright uses in
  // set_panel/is_open: a non-empty box and no visibility:hidden. The [hidden] attribute
  // is only one way to collapse a panel; a panel collapsed by CSS (display:none, zero
  // height, visibility) must read closed here exactly as it does there, so the probe,
  // set_panel and check_state cannot disagree about the same panel.
  const shown = el => {
    if (!el) return false;
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0 && getComputedStyle(el).visibility !== 'hidden';
  };
  const bfile = document.getElementById('bfile');
  let scene = 'unknown';
  if (shown(bfile)) scene = 'symbols';
  else {
    const on = document.querySelector('#crumbs button.on');
    scene = on ? ({bctx: 'context', bpac: 'packages', bflow: 'flow'}[on.id] || 'unknown') : 'unknown';
  }

  const selPill = world.querySelector('.pill.sel');
  return {
    scene: scene,
    world: {x: r1(bb.x), y: r1(bb.y), w: w, h: h,
            aspect: h ? Math.round(w / h * 100) / 100 : 0},
    svg: svg,
    labels: {
      count: pairs.length, overrun_count: overrun_count,
      overrun_max_px: Math.round(overrun_max_px * 10) / 10,
      overrun_worst: overrun_worst, overlap_pairs: overlap_pairs
    },
    crumbs: {
      visible: crumbEls.filter(shown).map(e => e.id),
      on: crumbEls.filter(e => e.classList.contains('on')).map(e => e.id)
    },
    panels: {
      entry_points: {
        present: shown(document.getElementById('ephdr')),
        open: shown(document.getElementById('eplist')),
        items: document.querySelectorAll('#eplist .ep').length,
        groups: document.querySelectorAll('#eplist .kindhdr').length
      },
      stars: {
        present: shown(document.getElementById('starhdr')),
        open: shown(document.getElementById('starlist')),
        items: document.querySelectorAll('#starlist .star').length
      },
      usecases: {
        present: shown(document.getElementById('uchdr')),
        open: shown(document.getElementById('ucwrap')),
        items: document.querySelectorAll('#uclist .uc').length
      },
      search: {
        open: shown(document.getElementById('results')),
        items: document.querySelectorAll('#results button').length
      },
      detail: {
        title: (document.getElementById('dtitle').textContent || '').trim(),
        headings: Array.from(document.querySelectorAll('#dbody h3'))
          .map(e => (e.textContent || '').trim()),
        empty: !!document.querySelector('#dbody .empty')
      }
    },
    selected_symbol: selPill ? selPill.getAttribute('data-sym') : null,
    // Read for the post-conditions only (check_state), never written to metrics.json:
    // the harness deliberately does not drive these two checkboxes, so every metric
    // above assumes they are off, and that assumption is worth asserting.
    toggles: {
      muted: !!document.getElementById('tgtests').checked,
      stars: !!document.getElementById('tgstars').checked
    }
  };
}
"""

I18N_KEYS = [
    'search_placeholder', 'toggle_stars', 'panel_entry_points', 'panel_stars',
    'panel_usecases', 'crumb_context', 'crumb_packages', 'hint', 'map_aria',
    'detail_title', 'detail_empty', 'uc_export', 'zoom_fit_title',
]
