"""test_viewer.py — tests for the viewer's Flow-source model.

The viewer is one self-contained HTML file with no build step, so these tests work on
`viewer/template.html` directly: two of them assert on the source of the functions that
implement the model, and one lifts the pure resolver out of the template and runs its
truth table under node.

What is being guarded: the use-case overlay and the entry-point lens may be active at the
same time (the Context scene deliberately combines them), and the Flow scene draws
whichever of them was selected LAST rather than following a fixed precedence. See
docs/data-contract.md, section 13.4.

Reference: docs/data-contract.md, sections 13.3 and 13.4.
"""
import json
import re
import subprocess

from conftest import skip_without_node_binary


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
