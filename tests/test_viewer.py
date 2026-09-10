"""test_viewer.py — static guards over viewer/template.html.

The viewer is a single vanilla-JS file with no test harness of its own, so these
tests assert on its source text. They cover the parts of the viewer contract that
a silent edit would otherwise regress:

- docs/data-contract.md 13.2: the `UI_STRINGS` tables must stay key-for-key aligned
  between `en` and `pt-BR` (a key missing in `pt-BR` falls back to English, which is
  invisible until a Portuguese reader sees an English sentence), and the contract's
  table must list exactly those keys, in the same order.
- docs/data-contract.md 13.3: the entry-points section starts open when the map has
  entries and stays hidden (header and list) when it has none.
- docs/data-contract.md 13.4: the use-case overlay and the entry-point lens may be
  active at the same time, so the Flow scene draws whichever was selected LAST
  rather than following a fixed precedence.
- docs/data-contract.md 13.6: the stars ranking has a qualification floor and a cap,
  the badge counts what is rendered, and the empty state is an explicit message.

Behaviour that only a browser can prove (actual row counts, labels, toggles) is
checked manually with the four-scene walkthrough of CONTRIBUTING.md.
"""
import json
import os
import re
import subprocess

import pytest

from conftest import REPO_ROOT, skip_without_node_binary

UI_BLOCK = re.compile(r"const UI_STRINGS = \{\n(.*?)\n\};\n", re.S)
EN_BLOCK = re.compile(r"^  en: \{\n(.*?)^  \},\n", re.S | re.M)
PT_BLOCK = re.compile(r"^  'pt-BR': \{\n(.*?)^  \}\s*$", re.S | re.M)
KEY = re.compile(r"^\s*'([^']+)':", re.M)
DOC_ROW = re.compile(r"^\| `([^`]+)` \|", re.M)

CONTRACT = os.path.join(REPO_ROOT, 'docs', 'data-contract.md')


@pytest.fixture(scope='module')
def html(viewer_template):
    with open(viewer_template, encoding='utf-8') as fh:
        return fh.read()


@pytest.fixture(scope='module')
def contract():
    with open(CONTRACT, encoding='utf-8') as fh:
        return fh.read()


def ui_strings_keys(template_text):
    """The key lists of UI_STRINGS.en and UI_STRINGS['pt-BR'], in source order."""
    block = UI_BLOCK.search(template_text)
    assert block, 'UI_STRINGS table not found in viewer/template.html'
    body = block.group(1)
    en = EN_BLOCK.search(body)
    pt = PT_BLOCK.search(body)
    assert en, "the 'en' entry of UI_STRINGS was not found"
    assert pt, "the 'pt-BR' entry of UI_STRINGS was not found"
    return KEY.findall(en.group(1)), KEY.findall(pt.group(1))


def doc_ui_keys(contract_text):
    """The keys listed by the UI-strings table of docs/data-contract.md 13.2."""
    start = contract_text.index('### 13.2 UI strings')
    end = contract_text.index('### 13.3', start)
    return DOC_ROW.findall(contract_text[start:end])


def test_ui_strings_tables_have_the_same_keys_in_the_same_order(html):
    en, pt = ui_strings_keys(html)
    missing = [k for k in en if k not in pt]
    extra = [k for k in pt if k not in en]
    assert en == pt, (
        'UI_STRINGS.en and UI_STRINGS["pt-BR"] must hold the same keys in the same '
        'order — a key present only in en silently falls back to English for a '
        f'pt-BR reader. Missing from pt-BR: {missing}; only in pt-BR: {extra}')


def test_stars_empty_state_string_exists_in_both_languages(html):
    en, pt = ui_strings_keys(html)
    assert 'stars.none' in en, "UI_STRINGS.en must define 'stars.none' (contract 13.6)"
    assert 'stars.none' in pt, "UI_STRINGS['pt-BR'] must define 'stars.none' (contract 13.6)"
    texts = re.findall(r"^\s*'stars\.none': '(.*)',$", html, re.M)
    assert len(texts) == 2, f"expected exactly two 'stars.none' rows, found {len(texts)}"
    assert texts[0] != texts[1], (
        "the pt-BR 'stars.none' text must be a translation, not a copy of the English one")


def test_ui_strings_match_the_data_contract_table(html, contract):
    en, _ = ui_strings_keys(html)
    doc = doc_ui_keys(contract)
    assert doc == en, (
        'the UI-strings table of docs/data-contract.md 13.2 must list exactly the keys '
        'of UI_STRINGS.en, in the same order (project principle: the contract is '
        f'updated in the same change). Only in the doc: {[k for k in doc if k not in en]}; '
        f'only in the viewer: {[k for k in en if k not in doc]}')


def test_stars_ranking_has_a_qualification_floor_and_a_cap(html):
    assert re.search(
        r"ucCount\[i\]\s*>\s*0\s*\|\|\s*impIn\[i\]\s*>\s*0\s*\|\|\s*callIn\[i\]\s*>\s*0", html), (
        'the stars ranking must keep its qualification floor: a file appears only when a '
        'use-case, an inbound import or an inbound call points at it (contract 13.6)')
    assert 'const STAR_MAX = 20;' in html, 'the stars list must keep its named cap STAR_MAX'
    assert re.search(r"\.slice\(0,\s*STAR_MAX\)", html), (
        'the stars ranking must be capped with .slice(0, STAR_MAX)')
    assert re.search(r"starn'\)\.textContent = starRank\.length", html), (
        'the stars badge must count the rows actually rendered, never a padded 20')
    assert "t('stars.none')" in html, (
        'the stars panel must render an explicit message when nothing qualifies')


def test_entry_points_panel_starts_open_and_disappears_when_empty(html):
    assert '<h2 class="sec" id="ephdr" hidden>' in html, (
        'the entry-points header must start open (no "closed" class) and hidden until the '
        'viewer unhides it (contract 13.3)')
    assert '<h2 class="sec closed" id="ephdr"' not in html
    assert '<div id="eplist" hidden></div>' in html, (
        'the entry-points list must stay hidden in the markup so an empty map shows no panel')
    block = re.search(r"if \(ENTRY_POINTS\.length\)\{(.*?)\n\}", html, re.S)
    assert block, 'the "if (ENTRY_POINTS.length)" block was not found'
    assert 'ephdr.hidden = false;' in block.group(1)
    assert 'eplist.hidden = false;' in block.group(1), (
        'the entry-points list must be unhidden when the map has entry points, so the '
        'panel is rendered open rather than folded')


def test_template_loads_exactly_one_off_file_resource(html):
    """Only one `src=`/`href=` in the template points off the file.

    This is a source-text check, not a network trace: it looks at the attributes the
    browser resolves into a fetch (`src=`, `href=`) and keeps every value that is not a
    same-document fragment, so a sibling file next to the HTML counts too. A URL written
    in a comment or a JS string is not a request and is deliberately out of scope here; a
    page that grew, say, an `<img src>` or a second stylesheet would be caught.
    """
    attrs = re.findall(r'\b(?:src|href)\s*=\s*"([^"]*)"' + r"|\b(?:src|href)\s*=\s*'([^']*)'", html)
    values = [(a or b).strip() for a, b in attrs]
    off_file = [v for v in values if v and not v.startswith('#')]
    assert len(off_file) == 1, (
        'the template must load exactly one resource from off the file — the Google Fonts '
        'stylesheet — as README.md and QUICKSTART.md now state. '
        f'src=/href= values pointing off-file: {off_file}')
    assert off_file[0].startswith('https://fonts.googleapis.com/')


def extract_function(html, signature):
    """Lift one top-level function out of the template: from `function <signature>{`
    to the first line that is exactly `}` (the template indents every nested block)."""
    start = html.find('function ' + signature)
    assert start >= 0, f'function {signature} not found in viewer/template.html'
    end = html.find('\n}\n', start)
    assert end > start, f'could not find the end of function {signature}'
    return html[start:end + 2]


# (pick, uc, ep, tree) -> expected pick after the resolver runs
FLOW_PICK_TABLE = [
    (None, False, False, False, None),
    ('uc', True, True, False, 'uc'),
    ('ep', True, True, False, 'ep'),      # the ticket case: the entry point was last
    ('tree', True, False, True, 'tree'),
    ('ep', True, False, False, 'uc'),     # the entry point was cleared: fall back
    ('tree', True, False, False, 'uc'),
    ('uc', False, True, False, 'ep'),
    ('uc', False, False, True, 'tree'),
    ('uc', False, False, False, None),
    (None, True, True, False, 'ep'),
    (None, True, False, False, 'uc'),
]


def test_resolve_flow_pick_truth_table(tmp_path, viewer_template):
    """The pure resolver keeps `flowPick` on a selection that is still active."""
    skip_without_node_binary()
    with open(viewer_template, encoding='utf-8') as fh:
        html = fh.read()
    fn = extract_function(html, 'resolveFlowPick(pick, live)')

    cases = [{'pick': pick, 'live': {'uc': uc, 'ep': ep, 'tree': tree}, 'want': want}
             for pick, uc, ep, tree, want in FLOW_PICK_TABLE]
    harness = fn + '\n' + (
        'const cases = %s;\n'
        'const bad = [];\n'
        'for (const c of cases){\n'
        '  const got = resolveFlowPick(c.pick, c.live);\n'
        '  if (got !== c.want) bad.push(JSON.stringify(c) + " -> " + JSON.stringify(got));\n'
        '}\n'
        'if (bad.length){ console.error(bad.join("\\n")); process.exit(1); }\n'
    ) % json.dumps(cases)

    script = tmp_path / 'flow_pick.js'
    script.write_text(harness, encoding='utf-8')
    proc = subprocess.run(['node', str(script)], capture_output=True, text=True)
    assert proc.returncode == 0, (
        'resolveFlowPick does not match the Flow-source truth table '
        '(data-contract 13.4):\n' + proc.stderr)


def test_flow_scene_dispatches_on_flow_pick(viewer_template):
    """renderFlow branches on `flowPick`, not on a fixed selection precedence.

    Matched with whitespace-tolerant patterns: reformatting the viewer must not fail CI,
    only a change of meaning may."""
    with open(viewer_template, encoding='utf-8') as fh:
        html = fh.read()
    fn = extract_function(html, 'renderFlow()')
    message = ('the Flow scene must follow flowPick (data-contract 13.4), '
               'not a fixed precedence')
    for source in ('uc', 'ep', 'tree'):
        assert re.search(r"flowPick\s*===\s*'%s'" % source, fn), (
            f"{message}: missing the {source} branch")
    stale_branches = (
        r'if\s*\(\s*activeUC\s*>=\s*0\s*\)\s*\{',
        r'if\s*\(\s*activeEp\s*>=\s*0\s*\)\s*\{',
        r'else\s+if\s*\(\s*treeRoot\s*\)\s*\{',
    )
    for stale in stale_branches:
        assert not re.search(stale, fn), (
            f'{message}: found an old precedence branch matching {stale}')


def test_every_flow_source_records_the_pick(viewer_template):
    """Each of the three selection sites records which source Flow should draw, and the
    Flow crumb is shown exactly when there is one.

    Whitespace-tolerant, as above: `flowPick='uc'` and `flowPick = 'uc'` both count."""
    with open(viewer_template, encoding='utf-8') as fh:
        html = fh.read()
    for source in ('uc', 'ep', 'tree'):
        hits = re.findall(r"flowPick\s*=\s*'%s'" % source, html)
        assert len(hits) == 1, (
            "exactly one site must record flowPick = '%s' (data-contract 13.4), found %d"
            % (source, len(hits)))
    assert re.search(r'bfl\.hidden\s*=\s*flowPick\s*===\s*null\s*;', html), (
        'the Flow crumb must be visible exactly when flowPick is not null '
        '(data-contract 13.4)')


def test_only_a_real_selection_claims_the_flow_source(viewer_template):
    """setUC() repaints the detail panel for two different reasons: a use-case was
    selected, and the status of the active use-case changed. Only the first is a choice
    of Flow source (data-contract 13.4), so the refresh opts out with `pick: false`."""
    with open(viewer_template, encoding='utf-8') as fh:
        html = fh.read()
    fn = extract_function(html, 'setUC(j')
    assert re.search(r"opts\.pick\s*!==\s*false\s*\)\s*flowPick\s*=\s*'uc'", fn), (
        "setUC must claim the Flow source only when the caller did not opt out "
        "(data-contract 13.4)")
    # the internal repaint after a status change opts out ...
    assert re.search(r"setUC\(\s*activeUC\s*,\s*\{\s*pick\s*:\s*false\s*\}\s*\)", html), (
        'the status-change refresh must call setUC with pick: false: repainting the '
        'panel is not a new selection (data-contract 13.4)')
    # ... and it is the only caller that does.
    optouts = re.findall(r"setUC\([^)]*pick\s*:\s*false", html)
    assert len(optouts) == 1, (
        'only the status-change refresh may opt out of claiming the Flow source, '
        'found %d such calls' % len(optouts))


# (bbox, svg width, svg height) -> did fit() apply a transform?
FIT_TABLE = [
    ({'x': 0, 'y': 0, 'width': 400, 'height': 300}, 1600, 1000, True),
    ({'x': 0, 'y': 0, 'width': 400, 'height': 300}, 0, 0, False),     # no layout yet
    ({'x': 0, 'y': 0, 'width': 0, 'height': 0}, 1600, 1000, False),   # nothing drawn
    (None, 1600, 1000, False),                                       # getBBox() throws
]


def test_fit_reports_whether_it_applied_a_transform(tmp_path, viewer_template):
    """fit() must answer truthfully, because renderFlow only records the refit as done
    when it happened: a Flow drawn into a zero-width SVG has to be refitted later
    (data-contract 13.4)."""
    skip_without_node_binary()
    with open(viewer_template, encoding='utf-8') as fh:
        html = fh.read()
    fn = extract_function(html, 'fit()')

    cases = [{'bb': bb, 'w': w, 'h': h, 'want': want} for bb, w, h, want in FIT_TABLE]
    harness = (
        'let k = 1, tx = 0, ty = 0, applied = 0;\n'
        'let bb = null, W = 0, H = 0;\n'
        'function apply(){ applied++; }\n'
        'const world = { getBBox(){ if (!bb) throw new Error("no layout"); return bb; } };\n'
        'const svg = { get clientWidth(){ return W; }, get clientHeight(){ return H; } };\n'
        + fn + '\n' +
        'const cases = %s;\n'
        'const bad = [];\n'
        'for (const c of cases){\n'
        '  bb = c.bb; W = c.w; H = c.h; applied = 0;\n'
        '  const got = fit();\n'
        '  if (got !== c.want) bad.push(JSON.stringify(c) + " -> returned " + JSON.stringify(got));\n'
        '  else if (!!applied !== c.want) bad.push(JSON.stringify(c) + " -> applied " + applied);\n'
        '}\n'
        'if (bad.length){ console.error(bad.join("\\n")); process.exit(1); }\n'
    ) % json.dumps(cases)

    script = tmp_path / 'fit.js'
    script.write_text(harness, encoding='utf-8')
    proc = subprocess.run(['node', str(script)], capture_output=True, text=True)
    assert proc.returncode == 0, (
        'fit() must return true exactly when it applied a transform:\n' + proc.stderr)
