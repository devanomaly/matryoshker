"""visual_review.py — screenshots and metrics of the bundled fixture, in a real browser.

Builds `examples/sample-drf` with both bundled configs (from the committed golden
extraction in `tests/golden/`, so no Node is needed), drives the resulting map through a
fixed list of named states in headless Chromium, and writes:

  <out>/metrics.json   every measurement, one stable key order, for diffing
  <out>/report.md      the same numbers as Markdown, for a job summary or a PR body
  <out>/html/          the built demo maps, openable by hand
  <out>/shots/<run>/<state>.png
  <out>/build/         intermediate data.json/extra.json (removed unless --keep-build)
  <out>/.visual-review-out   marker: this directory is the harness's to remove and recreate

--out defaults to `visual-review/` at the root of THIS checkout, which `.gitignore`
already covers (alongside `out/` and `site/`); CI passes a path under the runner's
temp directory instead. The whole directory is removed and recreated on every run, and
the harness refuses an --out inside the repository being MAPPED (`examples/sample-drf`),
which it never writes to.

The point is that the numbers a pull request quotes about the viewer — the packed world's
aspect ratio, how far a cluster label sticks past its box, how many star rows read all
zeros, how many entry points there are per kind — stop coming from a throwaway script and
become reproducible:

  python3 tools/visual_review.py run --out visual-review
  python3 tools/visual_review.py diff --before base/metrics.json --after head/metrics.json

Playwright is a DEVELOPMENT-ONLY dependency (see requirements-dev.txt). Nothing in
`pipeline/`, nothing in `viewer/`, and no test in `tests/` needs it; `diff` and `list`
never import it either.

Reproducibility, honestly stated:
  - Metrics are viewport-independent by construction: the layout constants in the viewer
    are fixed, and only the fit() transform depends on the window, which is not measured.
    Two runs of the same input produce byte-identical metrics.json.
  - The page's own character encoding is asserted right after every load: an HTML file
    that declares no charset is decoded by a browser guess, and one mojibake label would
    move world.w, the aspect ratio and the label-overrun numbers. Wrong numbers, quietly
    emitted, are worse than a run that stops.
  - Screenshots are for eyeballing, and are comparable WITHIN ONE ENVIRONMENT ONLY. Fonts
    differ between machines (the Google Fonts request succeeds on a networked runner and
    fails offline), and even in one process a PNG can differ by a few pixels of shadow
    antialiasing. Do not build a pixel gate on this without re-measuring first.
  - Web fonts are blocked by default so that the text-measurement-derived metrics (label
    geometry, world width) are identical online and offline. The request still fires, so
    the "the page makes exactly one external request" invariant is still checked.

Reference: docs/data-contract.md (the viewer's DOM and data contract).
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

PROG = 'visual_review.py'
HARNESS = 'tools/visual_review.py'
SCHEMA = 1
# Written as the very first thing inside --out, so a run that dies half way through
# (a browser crash, a failed post-condition, Ctrl-C) still leaves a directory the next
# identical command may reuse. Keying the reuse guard on metrics.json instead would
# refuse to run again exactly when a crash made re-running necessary.
MARKER = '.visual-review-out'
MARKER_TEXT = (
    'Written by tools/visual_review.py. The harness removes and recreates this whole\n'
    'directory on every run: keep nothing here.\n')

# The run matrix, the state list and the two JS probes live beside this file so
# that what the harness *runs* stays readable apart from how it runs it.
try:
    from config import RUNS, STATES
    from probes import I18N_KEYS, RUN_PROBE_JS, STATE_PROBE_JS
except ImportError:  # invoked as tools/visual_review.py from the repo root
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from config import RUNS, STATES
    from probes import I18N_KEYS, RUN_PROBE_JS, STATE_PROBE_JS


# ---------------------------------------------------------------- small helpers
def fail(msg):
    raise SystemExit(f'{PROG}: {msg}')


def digest(*blobs):
    h = hashlib.sha256()
    for b in blobs:
        h.update(b)
    return h.hexdigest()[:12]


def dir_size(path):
    return sum(p.stat().st_size for p in Path(path).rglob('*') if p.is_file())


# ---------------------------------------------------------------- build
def run_step(argv, cwd):
    proc = subprocess.run(argv, cwd=str(cwd), stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, text=True, encoding='utf-8')
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr)
        fail('build step failed: ' + ' '.join(str(a) for a in argv))


def build_html(repo_root, golden, template, out, config, lang):
    """Builds one demo HTML from the committed golden extraction. No Node, no npm."""
    build_dir = out / 'build'
    html_dir = out / 'html'
    build_dir.mkdir(parents=True, exist_ok=True)
    html_dir.mkdir(parents=True, exist_ok=True)

    src_cfg = repo_root / 'config' / f'{config}.json'
    if not src_cfg.is_file():
        fail(f'config not found: {src_cfg}')
    cfg_obj = json.loads(src_cfg.read_text(encoding='utf-8'))
    repo_name = cfg_obj.get('repo') or 'repo'
    cfg_path = src_cfg
    if (cfg_obj.get('lang') or 'en') != lang:
        # A derived config, written under --out; config/ in the tree is never touched.
        cfg_obj['lang'] = lang
        cfg_path = build_dir / f'{config}.{lang}.json'
        cfg_path.write_text(json.dumps(cfg_obj, ensure_ascii=False, indent=2) + '\n',
                            encoding='utf-8')

    ucs = repo_root / 'examples' / 'sample-drf' / 'usecases.json'
    data = build_dir / f'data.{config}.{lang}.json'
    extra = build_dir / f'extra.{config}.{lang}.json'
    html = html_dir / f'{repo_name}.{config}.{lang}.html'
    common = ['--es', str(golden / 'es-output.json'),
              '--imports', str(golden / 'im-output.json'),
              '--config', str(cfg_path), '--ucs', str(ucs)]
    run_step([sys.executable, str(repo_root / 'pipeline' / 'prep_data.py')]
             + common + ['--out', str(data)], repo_root)
    run_step([sys.executable, str(repo_root / 'pipeline' / 'prep_extra.py')]
             + common + ['--repo', str(repo_root / 'examples' / 'sample-drf'),
                         '--out', str(extra)], repo_root)
    run_step([sys.executable, str(repo_root / 'pipeline' / 'inject.py'),
              '--template', str(template), '--data', str(data),
              '--extra', str(extra), '--out', str(html)], repo_root)
    return html, digest(data.read_bytes(), extra.read_bytes())


# ---------------------------------------------------------------- state driving
# Every sidebar panel header is a TOGGLE: one click opens a closed panel and closes an
# open one. Which panels start open is a viewer decision that a pull request may change
# (and the harness exists to review exactly those pull requests), so nothing here clicks
# a toggle blindly. set_panel reads the current state and clicks only when the state has
# to change; check_state then asserts the condition each state's own name claims, so a
# state that did not get there fails by name instead of timing out on a later selector.
# Below this the browser refuses to capture a screenshot at all.
MIN_VIEWPORT = 200

PANEL_TIMEOUT_MS = 5000


def is_open(page, sel):
    """True when the element is in the DOM and visible ([hidden] and display: aware)."""
    loc = page.locator(sel)
    return loc.count() > 0 and loc.first.is_visible()


def set_panel(page, state, header, body, want_open=True):
    """Idempotently opens (or closes) one collapsible sidebar panel, then waits for it."""
    from playwright.sync_api import Error as PlaywrightError
    if is_open(page, body) != want_open:
        page.click(header)
    try:
        page.wait_for_selector(body, state='visible' if want_open else 'hidden',
                               timeout=PANEL_TIMEOUT_MS)
    except PlaywrightError:
        fail(f'state "{state}": clicking {header} did not leave {body} '
             f'{"open" if want_open else "closed"}')


def drive(page, name, sel):
    """Puts the page into the named state, starting from a cold load."""
    if name == 'context':
        page.click('#bctx')
    elif name == 'packages':
        pass  # the boot scene, and the empty selection state
    elif name == 'symbols':
        page.dblclick(f'#world .node[data-i="{sel["focus"]}"]')
    elif name == 'symbols_symbol_selected':
        page.dblclick(f'#world .node[data-i="{sel["focus"]}"]')
        page.wait_for_timeout(120)
        # A plain .click() times out: the .calledge paths in #fedges are painted after
        # the pills and take the hit test at the pill's vertical middle (edges attach at
        # y+9). force=True would not help either — the event target would be the path and
        # the viewer's closest('[data-sym]') returns null. Clicking near the corner works.
        page.locator('#world .pill').first.click(position={'x': 8, 'y': 4})
    elif name == 'flow_usecase':
        set_panel(page, name, '#uchdr', '#ucwrap')
        page.click(f'#uclist .uc[data-j="{sel["uc"]}"]')
        page.click('#bflow')
    elif name == 'flow_entry_point':
        set_panel(page, name, '#ephdr', '#eplist')
        page.click('#eplist .ep >> nth=0')
        page.click('#bflow')
    elif name == 'flow_call_tree':
        page.dblclick(f'#world .node[data-i="{sel["focus"]}"]')
        page.wait_for_timeout(120)
        page.click('#dbody [data-tree="file"]')
    elif name == 'flow_empty':
        set_panel(page, name, '#ephdr', '#eplist')
        page.click('#eplist .ep >> nth=0')
        page.click('#bflow')
        page.wait_for_timeout(120)
        page.click('#bep')  # clears the lens while the scene stays 'flow'
    elif name == 'packages_usecase_overlay':
        set_panel(page, name, '#uchdr', '#ucwrap')
        page.click(f'#uclist .uc[data-j="{sel["uc"]}"]')
    elif name == 'context_entry_point_lens':
        page.click('#bctx')
        set_panel(page, name, '#ephdr', '#eplist')
        page.click('#eplist .ep >> nth=0')
    elif name == 'file_selected_detail':
        page.click(f'#world .node[data-i="{sel["rev"]}"]')
    elif name == 'entry_points_panel_open':
        set_panel(page, name, '#ephdr', '#eplist')
    elif name == 'stars_panel_open':
        set_panel(page, name, '#starhdr', '#starlist')
    elif name == 'search_results':
        page.fill('#search', sel['query'])
    else:
        fail(f'unknown state: {name}')


def check_state(name, st):
    """What each state's name claims, checked against the probe. Returns the failures.

    A wrong state must fail here, by name, rather than quietly producing metrics and a
    screenshot of something else: a panel captured closed in `*_panel_open` is a silent
    lie, and silent lies are what this harness exists to prevent.
    """
    bad = []

    def want(ok, what):
        if not ok:
            bad.append(what)

    scene, g, cr, p = st['scene'], st['svg'], st['crumbs']['visible'], st['panels']
    # Two checkboxes the harness deliberately never drives (see the state list above);
    # every metric assumes they are off, so assert it instead of assuming it.
    want(not st['toggles']['muted'], 'the muted-categories toggle (#tgtests) is on')
    want(not st['toggles']['stars'], 'the star-halo toggle (#tgstars) is on')

    def in_scene(expected):
        want(scene == expected, f'the scene is "{scene}", not "{expected}"')

    if name == 'context':
        in_scene('context')
    elif name == 'packages':
        in_scene('packages')
        want(p['detail']['empty'], 'the detail pane is not the empty state')
        want(not p['search']['open'], 'the search results are open')
    elif name == 'symbols':
        in_scene('symbols')
    elif name == 'symbols_symbol_selected':
        in_scene('symbols')
        want(st['selected_symbol'] is not None, 'no symbol pill is selected')
    elif name == 'flow_usecase':
        in_scene('flow')
        want(p['usecases']['open'], 'the use-cases panel is closed')
        want(g['flow_nodes'] > 0, 'the flow is empty')
    elif name == 'flow_entry_point':
        in_scene('flow')
        want('bep' in cr, 'no entry-point crumb (#bep): the lens is not set')
        want(g['flow_nodes'] > 0, 'the flow is empty')
    elif name == 'flow_call_tree':
        in_scene('flow')
        want('btree' in cr, 'no call-tree crumb (#btree)')
    elif name == 'flow_empty':
        in_scene('flow')
        want('bep' not in cr, 'the entry-point lens (#bep) is still set')
        want(g['flow_nodes'] == 0, f"the flow still draws {g['flow_nodes']} nodes")
    elif name == 'packages_usecase_overlay':
        in_scene('packages')
        want(p['usecases']['open'], 'the use-cases panel is closed')
        want(g['nodes_dimmed'] > 0, 'no node is dimmed: no use-case overlay is active')
    elif name == 'context_entry_point_lens':
        in_scene('context')
        want('bep' in cr, 'no entry-point crumb (#bep): the lens is not set')
    elif name == 'file_selected_detail':
        in_scene('packages')
        want(g['nodes_selected'] > 0, 'no file node is selected')
        want(not p['detail']['empty'], 'the detail pane is still the empty state')
    elif name == 'entry_points_panel_open':
        want(p['entry_points']['open'], 'the entry-points panel is closed')
        want(p['entry_points']['items'] > 0, 'the entry-points panel is empty')
    elif name == 'stars_panel_open':
        want(p['stars']['open'], 'the stars panel is closed')
    elif name == 'search_results':
        want(p['search']['open'], 'the search results are closed')
        want(p['search']['items'] > 0, 'the search results are empty')
    return bad


def precondition(name, pre):
    """Returns a reason string when the state cannot be reached, else None."""
    if name in ('flow_entry_point', 'flow_empty', 'context_entry_point_lens',
                'entry_points_panel_open') and pre['entry_points'] < 1:
        return 'no entry points'
    if name in ('flow_usecase', 'packages_usecase_overlay') and pre['uc_hops'] < 1:
        return 'no use-case with hops'
    if name in ('symbols', 'symbols_symbol_selected', 'flow_call_tree') \
            and pre['focus_symbols'] < 1:
        return 'no visible file with symbols'
    if name == 'search_results' and pre['query_len'] < 2:
        return 'no search query'
    return None


# ---------------------------------------------------------------- run command
def cmd_run(args):
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except ImportError:
        fail('Playwright is not installed; run "pip install -r requirements-dev.txt" '
             'and then "python -m playwright install chromium"')

    started = time.time()
    repo_root = Path(args.repo_root).resolve()
    # Both are fixed positions inside the checkout --repo-root names, which is what
    # makes the merge-base recipe (one harness, two worktrees) work.
    golden = repo_root / 'tests' / 'golden'
    template = repo_root / 'viewer' / 'template.html'
    for p, what in ((repo_root, '--repo-root'), (golden, '<repo-root>/tests/golden')):
        if not p.is_dir():
            fail(f'{what}: not a directory: {p}')
    if not template.is_file():
        fail(f'<repo-root>/viewer/template.html: not a file: {template}')

    out = Path(args.out).resolve()
    # Principle 5: scripts never write into the repository being MAPPED. That repository
    # is the fixture, not this checkout, and this is the one place --out could land in it.
    mapped = (repo_root / 'examples' / 'sample-drf').resolve()
    if out == mapped or mapped in out.parents:
        fail(f'--out must not be inside the repository being mapped ({mapped}); '
             'the harness never writes there')
    # EVERY argument is validated before anything is removed: --out holds the previous
    # run, which a reviewer may still be reading, and a typo must cost them nothing.
    m = re.fullmatch(r'(\d+)x(\d+)', args.viewport)
    if not m:
        fail(f'--viewport: expected WxH, got "{args.viewport}"')
    vw, vh = int(m.group(1)), int(m.group(2))
    if vw < MIN_VIEWPORT or vh < MIN_VIEWPORT:
        fail(f'--viewport: expected WxH with both sides at least {MIN_VIEWPORT}, '
             f'got "{args.viewport}"')

    runs = RUNS
    if args.only:
        wanted = [s.strip() for s in args.only.split(',') if s.strip()]
        known = {r['id'] for r in RUNS}
        for w in wanted:
            if w not in known:
                fail(f'--only: unknown run "{w}" (see "{PROG} list")')
        runs = [r for r in RUNS if r['id'] in wanted]
    states = STATES
    if args.states:
        wanted = [s.strip() for s in args.states.split(',') if s.strip()]
        for w in wanted:
            if w not in STATES:
                fail(f'--states: unknown state "{w}" (see "{PROG} list")')
        states = [s for s in STATES if s in wanted]
    if args.focus_file and not (mapped / args.focus_file).is_file():
        # resolve_focus_file() stays the authoritative check, against the built map;
        # this one only has to catch a typo while the previous --out is still intact.
        fail(f'--focus-file: no such file under {mapped}: {args.focus_file}')

    if out.exists():
        if not out.is_dir():
            fail(f'--out: not a directory: {out}')
        if any(out.iterdir()) and not (out / MARKER).exists():
            fail(f'--out {out} exists, is not empty and was not created by {PROG} '
                 f'(no {MARKER} in it); remove it or choose another')
        shutil.rmtree(out)
    out.mkdir(parents=True)
    # First write, before the build and the browser: a crash after this point leaves a
    # directory the identical command can still reuse.
    (out / MARKER).write_text(MARKER_TEXT, encoding='utf-8')

    metrics = {
        'schema': SCHEMA,
        'harness': HARNESS,
        'viewport': f'{vw}x{vh}',
        'webfonts': 'allowed' if args.allow_webfonts else 'blocked',
        'template_digest': digest(template.read_bytes()),
        'states': list(states),
        'runs': {},
    }
    shots = 0
    exe = os.environ.get('MATRYOSHKER_CHROMIUM') or None

    with sync_playwright() as pw:
        try:
            browser = pw.chromium.launch(
                executable_path=exe, args=['--no-sandbox', '--disable-dev-shm-usage'])
        except PlaywrightError:
            fail('no Chromium available to Playwright; run '
                 '"python -m playwright install chromium", or set MATRYOSHKER_CHROMIUM '
                 'to an existing Chrome/Chromium executable')

        # One HTML per (config, lang), shared by the runs that need it. Built only once
        # the browser is known to work, so a missing browser leaves nothing behind but
        # the marker file.
        builds = {}
        for r in runs:
            key = (r['config'], r['lang'])
            if key not in builds:
                builds[key] = build_html(repo_root, golden, template, out, *key)

        for r in runs:
            html, data_digest = builds[(r['config'], r['lang'])]
            url = html.as_uri()
            run_out = {
                'config': r['config'], 'theme': r['theme'], 'lang': r['lang'],
                'html': html.relative_to(out).as_posix(),
                'data_digest': data_digest,
            }

            def open_page(r=r, state='(run probe)'):  # r bound per iteration
                ctx = browser.new_context(
                    viewport={'width': vw, 'height': vh}, reduced_motion='reduce',
                    color_scheme='dark' if r['theme'] == 'dark' else 'light')
                if not args.allow_webfonts:
                    ctx.route(re.compile(r'https?://fonts\.(googleapis|gstatic)\.com/'),
                              lambda route: route.abort())
                page = ctx.new_page()
                errs, reqs = [], []
                page.on('pageerror', lambda e: errs.append(str(e).split('\n')[0]))
                page.on('request', lambda q: reqs.append(q.url)
                        if not q.url.startswith('file:') else None)
                page.goto(url)
                # Defence in depth, one line after the load: a page with no charset
                # declaration is decoded by Chromium's own file:// guess, which is
                # timing-dependent, and a single mojibake label changes its width and
                # therefore world.w, the aspect ratio and the overrun numbers. A harness
                # that silently emits wrong numbers is worse than one that stops.
                charset = page.evaluate('() => document.characterSet')
                if (charset or '').upper() != 'UTF-8':
                    fail(f'run "{r["id"]}", state "{state}": the browser decoded the '
                         f'page as {charset}, not UTF-8, so every text measurement '
                         'taken from it would be wrong')
                page.evaluate("t => document.documentElement.setAttribute('data-theme', t)",
                              r['theme'])
                page.wait_for_selector('#world *')
                page.wait_for_timeout(120)
                return ctx, page, errs, reqs

            # Run-level facts, on their own cold page so they never depend on --states.
            ctx, page, _e, _q = open_page()
            probe = page.evaluate(RUN_PROBE_JS)
            ctx.close()
            pre = probe.pop('_pre')
            sel = probe['selection']
            if args.focus_file:
                idx = resolve_focus_file(builds, r, args.focus_file)
                sel['focus'] = idx[0]
                sel['focus_path'] = idx[1]
                pre['focus_symbols'] = idx[2]
            for key in ('selection', 'data', 'entry_points', 'usecases', 'stars',
                        'legend', 'theme_tokens', 'i18n'):
                run_out[key] = probe[key]
            run_out['i18n'].update({'compared_with': None, 'same_as_en': None,
                                    'same_as_en_keys': None})

            run_states = {}
            for name in states:
                reason = precondition(name, pre)
                if reason:
                    run_states[name] = {'skipped': reason}
                    continue
                ctx, page, errs, reqs = open_page(state=name)
                drive(page, name, sel)
                page.wait_for_timeout(150)
                st = page.evaluate(STATE_PROBE_JS)
                shot = None
                if not args.no_screenshots:
                    shot_path = out / 'shots' / r['id'] / f'{name}.png'
                    shot_path.parent.mkdir(parents=True, exist_ok=True)
                    page.screenshot(path=str(shot_path))
                    shot = shot_path.relative_to(out).as_posix()
                    shots += 1
                # Screenshot first, then assert: the PNG of the wrong state is the most
                # useful thing to look at when a post-condition fails.
                bad = check_state(name, st)
                if bad:
                    fail(f'run "{r["id"]}", state "{name}" is not what its name claims: '
                         + '; '.join(bad)
                         + (f' (see {shot_path})' if shot else ''))
                hosts = sorted({re.sub(r'^[a-z]+://([^/]+).*$', r'\1', u) for u in reqs})
                ordered = {'scene': st['scene'], 'screenshot': shot, 'world': st['world'],
                           'svg': st['svg'], 'labels': st['labels'], 'crumbs': st['crumbs'],
                           'panels': st['panels'],
                           'page': {'errors': len(errs), 'error_messages': errs[:5],
                                    'external_requests': len(reqs), 'external_hosts': hosts}}
                if name == 'symbols_symbol_selected':
                    ordered['selected_symbol'] = st['selected_symbol']
                run_states[name] = ordered
                ctx.close()

            run_out['states'] = run_states
            metrics['runs'][r['id']] = run_out
        browser.close()

    # i18n: what a non-en run still shows in English (a silently missing translation).
    for rid, run in metrics['runs'].items():
        if run['lang'] == 'en':
            continue
        base = next((o for k, o in metrics['runs'].items()
                     if o['config'] == run['config'] and o['lang'] == 'en'), None)
        if not base:
            continue
        same = sorted(k for k in I18N_KEYS
                      if run['i18n']['strings'].get(k) is not None
                      and run['i18n']['strings'].get(k) == base['i18n']['strings'].get(k))
        run['i18n']['compared_with'] = next(k for k, o in metrics['runs'].items() if o is base)
        run['i18n']['same_as_en'] = len(same)
        run['i18n']['same_as_en_keys'] = same

    if not args.keep_build:
        shutil.rmtree(out / 'build', ignore_errors=True)

    (out / 'metrics.json').write_text(
        json.dumps(metrics, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    (out / 'report.md').write_text(render_report(metrics), encoding='utf-8')
    mb = dir_size(out) / (1024 * 1024)
    print(f'runs={len(runs)} states={len(states)} shots={shots} -> {out} '
          f'({mb:.1f}MB) in {time.time() - started:.1f}s')
    return 0


def resolve_focus_file(builds, r, focus_file):
    """Resolves --focus-file to a file index, from the built data of this run."""
    html = builds[(r['config'], r['lang'])][0]
    text = html.read_text(encoding='utf-8')
    m = re.search(r'<script type="application/json" id="data">(.*?)</script>', text, re.S)
    if not m:
        fail('could not read the embedded data of the built HTML')
    data = json.loads(m.group(1).replace('<\\/', '</'))
    # A muted category (tests, by default) is in `files` but is never drawn, so the
    # scene has no node to click. RUN_PROBE_JS derives the default focus from the same
    # filter; the override has to obey it too, or a perfectly real path sails through
    # both checks and stalls on a node that is not there.
    muted = {c.get('id') for c in (data.get('meta') or {}).get('categories') or []
             if c.get('muted')}
    for i, f in enumerate(data.get('files') or []):
        if f.get('p') != focus_file:
            continue
        if f.get('g') in muted:
            fail(f'--focus-file: {focus_file} is in the muted category '
                 f'"{f.get("g")}", so the map never draws it; pick a file the '
                 f'scene shows')
        return i, f['p'], len(f.get('c') or []) + len(f.get('f') or [])
    fail(f'--focus-file: no such file in the map: {focus_file}')


# ---------------------------------------------------------------- report
def md(v):
    if isinstance(v, bool):
        return 'true' if v else 'false'
    if v is None:
        return '—'
    if isinstance(v, (list, dict)):
        return '`' + json.dumps(v, ensure_ascii=False, separators=(',', ':')) + '`'
    return str(v).replace('|', r'\|')


def panel_cell(panels):
    """`ep o/8 · stars c/20 · uc o/5 · search c/0` — open/closed and item count.

    Which panels start open, and how many rows each holds, is a viewer decision a pull
    request can change; without this column the table cannot tell the reviewer that it
    did. `—` means the panel is not present at all (no entry points in the map).
    """
    cells = []
    for label, key in (('ep', 'entry_points'), ('stars', 'stars'), ('uc', 'usecases')):
        p = panels[key]
        cells.append(f'{label} —' if not p['present']
                     else f"{label} {'o' if p['open'] else 'c'}/{p['items']}")
    se = panels['search']
    cells.append(f"search {'o' if se['open'] else 'c'}/{se['items']}")
    return ' · '.join(cells)


def render_report(metrics):
    L = []
    L.append('# Visual review — bundled fixture (`examples/sample-drf`)')
    L.append('')
    L.append(f"Viewport {metrics['viewport']} · web fonts {metrics['webfonts']} · "
             f"template `{metrics['template_digest']}` · harness `{metrics['harness']}`. "
             'Screenshots are comparable within one environment only; fonts differ '
             'between environments.')
    L.append('')
    for rid, run in metrics['runs'].items():
        st = run['states']
        L.append(f'## `{rid}`')
        L.append('')
        ep, uc, dat = run['entry_points'], run['usecases'], run['data']
        kinds = ', '.join(f'{k} {n}' for k, n in ep['by_kind'].items() if n) or '—'
        stat = ', '.join(f'{k} {n}' for k, n in uc['by_status'].items() if n) or '—'
        tt = run['theme_tokens']
        errs = sum(s['page']['errors'] for s in st.values() if 'page' in s)
        reqc = sorted({s['page']['external_requests'] for s in st.values() if 'page' in s})
        hosts = sorted({h for s in st.values() if 'page' in s for h in s['page']['external_hosts']})
        reqtxt = (f'{reqc[0]} per state' if len(reqc) == 1
                  else f'{reqc[0]}–{reqc[-1]} per state') if reqc else '—'
        if hosts:
            reqtxt += ' (' + ', '.join(hosts) + ')'
        rows = [
            ('config / theme / lang', f"`{run['config']}` / {run['theme']} / {run['lang']}"),
            ('files / imports / use-cases', f"{dat['files']} / {dat['imports']} / {dat['ucs']}"),
            ('entry points', f"{ep['total']} ({kinds})"),
            ('use-case status', stat),
            ('hops resolved', uc['hops_total']),
            ('calls', f"{dat['calls_internal']} internal / {dat['calls_cross']} cross "
                      f"in {dat['calls_files']} files"),
            ('stars', f"{run['stars']['rows']} rows, {run['stars']['zero_rows']} all-zero"),
            ('theme tokens', f"{tt['root']} / {tt['media_dark']} / {tt['attr_dark']}, "
                             f"missing {md(tt['missing_in_some_block'])}"),
        ]
        if run['i18n']['same_as_en'] is not None:
            rows.append(('i18n same as en',
                         f"{run['i18n']['same_as_en']} of {len(I18N_KEYS)} "
                         f"{md(run['i18n']['same_as_en_keys'])}"))
        rows += [
            ('page errors', errs),
            ('external requests', reqtxt),
            ('symbols focus / reverse index',
             f"`{run['selection']['focus_path']}` / `{run['selection']['rev_path']}`"),
            ('data digest', f"`{run['data_digest']}`"),
        ]
        L.append('| key | value |')
        L.append('|---|---|')
        for k, v in rows:
            L.append(f'| {k} | {md(v)} |')
        L.append('')
        L.append('| state | scene | world w×h | aspect | elems | edges | labels over/ovl '
                 '| panels o/c + items | detail | err |')
        L.append('|---|---|---|---|---|---|---|---|---|---|')
        for name in metrics['states']:
            s = st.get(name)
            if s is None:
                continue
            if 'skipped' in s:
                L.append(f"| `{name}` | — | — | — | — | — | — | — "
                         f"| skipped: {md(s['skipped'])} | — |")
                continue
            w, g, lb = s['world'], s['svg'], s['labels']
            edges = (g['agg_edges'] + g['call_edges'] + g['flow_lines']
                     + g['import_edges_in'] + g['import_edges_out'])
            L.append(f"| `{name}` | {s['scene']} | {w['w']:g}×{w['h']:g} | {w['aspect']:g} "
                     f"| {g['total_elements']} | {edges} "
                     f"| {lb['overrun_count']}/{lb['overlap_pairs']} "
                     f"| {panel_cell(s['panels'])} "
                     f"| {md(s['panels']['detail']['title'])} | {s['page']['errors']} |")
        L.append('')
    L.append('Panels column: `o`pen / `c`losed and the number of rows in each sidebar '
             'panel (`—` when the panel is absent), so a change to which panels start '
             'open shows up here.')
    L.append('')
    L.append('Full key set in `metrics.json`.')
    L.append('')
    return '\n'.join(L)


# ---------------------------------------------------------------- diff
def flatten(obj, prefix=''):
    out = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.update(flatten(v, f'{prefix}.{k}' if prefix else k))
    elif isinstance(obj, list):
        out[prefix] = json.dumps(obj, ensure_ascii=False, separators=(',', ':'))
    else:
        out[prefix] = obj
    return out


ABSENT = object()


def cell(v):
    if v is ABSENT:
        return '(absent)'
    if isinstance(v, bool):
        return 'true' if v else 'false'
    if v is None:
        return '—'
    return str(v).replace('|', r'\|')


def cmd_diff(args):
    before_path, after_path = Path(args.before), Path(args.after)
    for p, what in ((before_path, '--before'), (after_path, '--after')):
        if not p.is_file():
            fail(f'{what}: not a file: {p}')
    try:
        before = json.loads(before_path.read_text(encoding='utf-8'))
        after = json.loads(after_path.read_text(encoding='utf-8'))
    except json.JSONDecodeError as e:
        fail(f'not a metrics.json: {e}')

    rows = []            # (run, state, metric, before, after)
    changed_states, changed_runs = set(), set()
    run_ids = sorted(set(before.get('runs', {})) | set(after.get('runs', {})))
    state_order = list(after.get('states') or before.get('states') or STATES)
    for rid in run_ids:
        b_run, a_run = before.get('runs', {}).get(rid), after.get('runs', {}).get(rid)
        if b_run is None or a_run is None:
            rows.append((rid, '(run)', '(present)',
                         'yes' if b_run else '(absent)', 'yes' if a_run else '(absent)'))
            changed_runs.add(rid)
            continue
        b_flat = flatten({k: v for k, v in b_run.items() if k != 'states'})
        a_flat = flatten({k: v for k, v in a_run.items() if k != 'states'})
        for key in sorted(set(b_flat) | set(a_flat)):
            bv, av = b_flat.get(key, ABSENT), a_flat.get(key, ABSENT)
            if bv != av or args.all:
                rows.append((rid, '(run)', key, cell(bv), cell(av)))
                if bv != av:
                    changed_runs.add(rid)
        b_states, a_states = b_run.get('states', {}), a_run.get('states', {})
        names = [s for s in state_order if s in b_states or s in a_states]
        names += sorted((set(b_states) | set(a_states)) - set(names))
        for name in names:
            bs, as_ = b_states.get(name), a_states.get(name)
            if bs is None or as_ is None:
                rows.append((rid, name, '(state)',
                             '(absent)' if bs is None else 'present',
                             '(absent)' if as_ is None else 'present'))
                changed_states.add((rid, name))
                changed_runs.add(rid)
                continue
            if ('skipped' in bs) != ('skipped' in as_):
                rows.append((rid, name, '(state)',
                             f"skipped: {bs['skipped']}" if 'skipped' in bs else 'present',
                             f"skipped: {as_['skipped']}" if 'skipped' in as_ else 'present'))
                changed_states.add((rid, name))
                changed_runs.add(rid)
                continue
            b_flat, a_flat = flatten(bs), flatten(as_)
            for key in sorted(set(b_flat) | set(a_flat)):
                if key == 'screenshot':
                    continue  # a path, not a measurement
                bv, av = b_flat.get(key, ABSENT), a_flat.get(key, ABSENT)
                if bv != av or args.all:
                    rows.append((rid, name, key, cell(bv), cell(av)))
                    if bv != av:
                        changed_states.add((rid, name))
                        changed_runs.add(rid)

    n_changed = sum(1 for r in rows if r[3] != r[4])
    L = ['## Visual review diff', '']
    if before.get('schema') != after.get('schema'):
        L.append(f"**Metric schema changed ({before.get('schema')} → "
                 f"{after.get('schema')}); rows may not be comparable.**")
        L.append('')
    L.append(f"before `{before_path}` (template `{before.get('template_digest')}`) → "
             f"after `{after_path}` (template `{after.get('template_digest')}`)")
    L.append('')
    n_runs = len(after.get('runs', {}))
    n_states = len(after.get('states') or [])
    L.append(f'{n_runs} runs × {n_states} states · **{n_changed} metrics changed** in '
             f'{len(changed_states)} states across {len(changed_runs)} runs.')

    dig = [rid for rid in run_ids
           if before.get('runs', {}).get(rid, {}).get('data_digest')
           != after.get('runs', {}).get(rid, {}).get('data_digest')]
    L.append('Data digest: unchanged in every run.' if not dig
             else 'Data digest: changed in ' + ', '.join(f'`{r}`' for r in dig) + '.')

    def errsum(doc):
        return sum(s.get('page', {}).get('errors', 0)
                   for run in doc.get('runs', {}).values()
                   for s in run.get('states', {}).values())
    eb, ea = errsum(before), errsum(after)
    L.append(f'Page errors: {eb} → **{ea}**.' if ea else f'Page errors: {eb} → {ea}.')

    sb, sa = set(before.get('states') or []), set(after.get('states') or [])
    if sb == sa:
        L.append('State list: unchanged.')
    else:
        moved = ['`+' + s + '`' for s in sorted(sa - sb)] + \
                ['`-' + s + '`' for s in sorted(sb - sa)]
        L.append('State list: ' + ', '.join(moved) + '.')

    sel = [r for r in rows if r[2].startswith('selection.') and r[3] != r[4]]
    if sel:
        L.append('**The derived selection moved** (' +
                 ', '.join(sorted({r[2] for r in sel})) +
                 '), so several states change together.')
    L.append('')
    if not rows:
        L.append(f'No metric changed across {n_runs} runs × {n_states} states.')
        L.append('')
    else:
        L.append('| run | state | metric | before | after |')
        L.append('|---|---|---|---|---|')
        for rid, state, key, bv, av in rows:
            L.append(f'| `{rid}` | `{state}` | `{key}` | {bv} | {av} |')
        L.append('')
    text = '\n'.join(L)
    if args.out:
        Path(args.out).write_text(text, encoding='utf-8')
        print(f'{n_changed} metrics changed -> {args.out}')
    else:
        sys.stdout.write(text)
    return 0


def cmd_list(args):
    print('runs (id, config, theme, lang):')
    for r in RUNS:
        print(f"  {r['id']:<22} {r['config']:<12} {r['theme']:<6} {r['lang']}")
    print(f'\nstates ({len(STATES)}, canonical order):')
    for i, s in enumerate(STATES, 1):
        print(f'  {i:>2}. {s}')
    return 0


# ---------------------------------------------------------------- CLI
def parse_args(argv=None):
    ap = argparse.ArgumentParser(
        prog=PROG,
        description='Screenshots and metrics of the bundled fixture, in a real browser.',
        epilog='Playwright is a development-only dependency (requirements-dev.txt); '
               '"diff" and "list" never need it.')
    sub = ap.add_subparsers(dest='cmd', required=True)

    here = Path(__file__).resolve().parent.parent

    r = sub.add_parser('run', help='build the fixture and capture every state')
    r.add_argument('--out', default=str(here / 'visual-review'), metavar='DIR',
                   help='where to write build/, html/, shots/, metrics.json and '
                        'report.md; removed and recreated on every run, never inside '
                        'the repository being mapped (default: <this checkout>/'
                        'visual-review, which .gitignore already covers)')
    r.add_argument('--repo-root', default=str(here), metavar='DIR',
                   help='checkout to drive: viewer/, pipeline/, config/, tests/golden/ and '
                        'examples/ are read from here, so one harness can run against a '
                        'git worktree of the merge base (default: this checkout)')
    r.add_argument('--only', default=None, metavar='RUN[,RUN...]',
                   help='subset of run ids (see "list")')
    r.add_argument('--states', default=None, metavar='STATE[,STATE...]',
                   help='subset of state names (see "list")')
    r.add_argument('--viewport', default='1600x1000', metavar='WxH',
                   help='browser viewport; screenshots only — every metric is '
                        'viewport-independent by construction (default: 1600x1000)')
    r.add_argument('--focus-file', default=None, metavar='PATH',
                   help='repo-relative file to open in the Symbols scene, instead of the '
                        'one derived from the call graph')
    r.add_argument('--allow-webfonts', action='store_true',
                   help='do not block fonts.googleapis.com; slow and environment-'
                        'dependent, never for CI')
    r.add_argument('--no-screenshots', action='store_true', help='metrics only')
    r.add_argument('--keep-build', action='store_true',
                   help='keep <out>/build/ (data.json, extra.json, derived config)')
    r.set_defaults(func=cmd_run)

    d = sub.add_parser('diff', help='render what moved between two metrics.json')
    d.add_argument('--before', required=True, metavar='FILE')
    d.add_argument('--after', required=True, metavar='FILE')
    d.add_argument('--out', default=None, metavar='FILE',
                   help='write the Markdown here instead of stdout')
    d.add_argument('--all', action='store_true', help='also list unchanged metrics')
    d.set_defaults(func=cmd_diff)

    li = sub.add_parser('list', help='print the run matrix and the state names')
    li.set_defaults(func=cmd_list)
    return ap.parse_args(argv)


def main():
    args = parse_args()
    return args.func(args)


if __name__ == '__main__':
    sys.exit(main())
