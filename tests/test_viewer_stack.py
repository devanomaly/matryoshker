"""test_viewer_stack.py — the Flow scene's stack view, run under node.

Extracts the stack-view block of viewer/template.html between its sentinel comments
and runs `stackSvg()` under bare `node` against one synthetic use-case. The block is
required to depend on nothing but `F`, `t`, `esc`, `baseName` and `CATCOLOR` — five
stubs is the whole harness — precisely so this extraction can execute it and so the
drawing stays a pure function of the embedded data (data-contract 13.6).

`t` is stubbed as the key itself, with the substituted values appended: the assertions
below are about how many strings the drawing asks for and where, never about English
or Portuguese text, which lives in UI_STRINGS and in the contract's 13.2 table.

Reference: docs/data-contract.md, sections 7.4 and 13.5.
"""
import json
import re
import subprocess

import pytest

from conftest import skip_without_node_binary

BEGIN = '// --- stack view (data-contract 7.4 frames) ---'
END = '// --- end stack view ---'

# The six files the synthetic use-case cites. The fourth carries markup in its path
# so the escaping assertion has something to find.
FILES = [
    {'p': 'orders/api/views.py', 'g': 'views'},
    {'p': 'orders/services/checkout.py', 'g': 'services'},
    {'p': 'orders/gateway/<b>payments</b>.py', 'g': 'gateway'},
    {'p': 'orders/common/queue.py', 'g': 'other'},
    {'p': 'orders/tasks/notify.py', 'g': 'tasks'},
    {'p': 'orders/models/an_unusually_long_module_name_for_one_order.py', 'g': 'models'},
]

# entry -> call -> queue -> worker -> call, plus one `other`.
FRAMES = [
    {'id': 'S1', 'parent': None, 'e': 'entry', 'i': 0, 's': 'CheckoutView',
     'r': 'audits and delegates', 'd': 0, 'reg': 'hop 1', 'st': 'inferred', 'en': '',
     'sr': '', 'proof': 'entry', 'why': 'entry point of the stack', 'ok': True},
    {'id': 'S2', 'parent': 'S1', 'e': 'call', 'i': 1, 's': 'CheckoutService.place',
     'r': 'the <b>central</b> rule', 'd': 1, 'reg': 'hop 2', 'st': 'inferred', 'en': '',
     'sr': '', 'proof': 'import', 'why': 'the parent file imports the child file', 'ok': True},
    {'id': 'S3', 'parent': 'S2', 'e': 'other', 'i': 2, 's': 'PaymentGateway.charge',
     'r': 'charges the total', 'd': 2, 'reg': 'hop 3', 'st': 'inferred',
     'en': 'into the provider library, outside the extraction', 'sr': 'mock: no-op gateway',
     'proof': 'import', 'why': 'the parent file imports the child file', 'ok': True},
    {'id': 'S4', 'parent': 'S2', 'e': 'queue', 'i': 3, 's': 'enqueue',
     'r': 'publishes the job by name', 'd': 2, 'reg': 'frame only', 'st': 'inferred',
     'en': '', 'sr': '', 'proof': 'import', 'why': 'the parent file imports the child file',
     'ok': True},
    {'id': 'S5', 'parent': 'S4', 'e': 'worker', 'i': 4, 's': 'send_receipt',
     'r': 'another process picks the job up', 'd': 0, 'reg': 'hop 4', 'st': 'inferred',
     'en': '', 'sr': '', 'proof': 'unprovable',
     'why': 'a worker edge is not provable by the import graph', 'ok': True},
    {'id': 'S6', 'parent': 'S5', 'e': 'call', 'i': 5,
     's': 'AnUnusuallyLongAggregateName.mark_as_shipped_and_notify_every_subscriber',
     'r': 'moves the order on', 'd': 1, 'reg': 'hop 5', 'st': 'outdated', 'en': '',
     'sr': '', 'proof': 'fail',
     'why': 'orders/tasks/notify.py does not import the model in the import graph',
     'ok': False},
]

USE_CASE = {'name': 'Customer checks a basket out', 'hops': [{}, {}, {}, {}, {}],
            'frames': FRAMES}

STUBS = """
const F = __FILES__;
function esc(s){ return String(s).replace(/[&<>"]/g, ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[ch])); }
const baseName = p => p.split('/').pop();
const CATCOLOR = g => 'var(--' + g + ')';
function t(key, vars){
  return vars ? key + '[' + Object.keys(vars).map(k => k + '=' + vars[k]).join(',') + ']' : key;
}
"""

HARNESS = """
const U = __UC__;
const drawn = stackSvg(U);
console.log(JSON.stringify({
  svg: drawn.svg, sub: drawn.sub, width: drawn.width,
  toggleOn: stackToggleSvg(0, -74, true), toggleOff: stackToggleSvg(0, -74, false),
  cap: Math.floor((STACK.W - 20) / STACK.CHARW)}));
"""


def extract_block(template_path):
    """The source between the sentinels, or fail loudly if they are not there."""
    with open(template_path, encoding='utf-8') as fh:
        html = fh.read()
    start = html.find(BEGIN)
    end = html.find(END)
    assert start >= 0, f'sentinel not found in {template_path}: {BEGIN}'
    assert end > start, f'sentinel not found after the opening one: {END}'
    return html[start + len(BEGIN):end]


@pytest.fixture(scope='module')
def drawn(tmp_path_factory, viewer_template):
    """Run the extracted stack view over the synthetic use-case, under node."""
    skip_without_node_binary()
    script = tmp_path_factory.mktemp('stack') / 'stack.js'
    script.write_text(
        STUBS.replace('__FILES__', json.dumps(FILES))
        + extract_block(viewer_template)
        + HARNESS.replace('__UC__', json.dumps(USE_CASE)),
        encoding='utf-8')
    result = subprocess.run(['node', str(script)], capture_output=True, text=True,
                            encoding='utf-8')
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def count(text, needle):
    return text.count(needle)


TEXT = re.compile(r'<text[^>]*>(.*?)</text>', re.S)
# the only child elements a text node is allowed to carry
NESTED = re.compile(r'</?tspan[^>]*>|</?title>')


def text_bodies(svg):
    """The content of every <text> element, with its allowed child tags removed.

    Whatever '<' survives that removal was never escaped.
    """
    return [NESTED.sub('', match.group(1)) for match in TEXT.finditer(svg)]


def test_one_rect_per_frame(drawn):
    assert count(drawn['svg'], '<rect') == len(FRAMES), (
        'the stack draws one node per frame and nothing else with a rect')


def test_one_new_process_rule_for_the_single_worker(drawn):
    assert count(drawn['svg'], 'flow.stack.new_process') == 1, (
        'exactly one frame reopens the stack, so exactly one rule is labelled')
    assert count(drawn['svg'], 'stroke-dasharray="6 5"') == 1, (
        'the label comes with exactly one dashed rule across the drawing')


def test_the_reopening_edge_is_the_only_one_with_an_arrow_head(drawn):
    assert count(drawn['svg'], 'marker-end="url(#arra)"') == 1


def test_every_non_call_edge_is_dashed_and_call_edges_are_not(drawn):
    # five frames have a parent: S2 (call), S3 (other), S4 (queue), S5 (worker), S6 (call)
    assert count(drawn['svg'], '<path class="calledge"') == 5
    assert count(drawn['svg'], 'stroke-dasharray="5 4"') == 3


def test_a_long_label_is_clipped_with_an_ellipsis_and_never_exceeds_the_cap(drawn):
    cap = drawn['cap']
    labels = [body for body in text_bodies(drawn['svg']) if '…' in body]
    assert labels, 'the longest symbol of the fixture must have been clipped'
    for label in labels:
        assert len(label) <= cap, (
            f'a clipped label must fit the node: {len(label)} characters for a cap of {cap}')
    assert any(label.endswith('…') for label in labels)


def test_no_text_content_carries_an_unescaped_angle_bracket(drawn):
    for body in text_bodies(drawn['svg']):
        assert '<' not in body, f'unescaped markup reached a text node: {body!r}'
    assert '&lt;b&gt;' in drawn['svg'], (
        'the markup planted in a path and in a role must survive, escaped')
    assert '<b>' not in drawn['svg']


def test_the_mock_prefix_adds_its_own_note_once(drawn):
    assert count(drawn['svg'], 'flow.stack.mocked') == 1, (
        'only S3 has a status_reason starting with mock:')


def test_each_proof_state_is_named_through_a_ui_string(drawn):
    assert count(drawn['svg'], 'flow.stack.proof.entry') == 1
    assert count(drawn['svg'], 'flow.stack.proof.import') == 3
    assert count(drawn['svg'], 'flow.stack.proof.unprovable[edge=worker]') == 1, (
        'the unprovable string names the edge kind it could not prove')
    assert count(drawn['svg'], 'flow.stack.proof.fail') == 1


def test_the_failing_frame_is_the_only_one_drawn_in_the_critical_color(drawn):
    assert count(drawn['svg'], 'var(--crit)') == 1


def test_the_registry_text_is_printed_verbatim_and_never_parsed(drawn):
    for frame in FRAMES:
        assert frame['reg'] in drawn['svg']


def test_the_summary_counts_frames_hops_and_failures(drawn):
    assert drawn['sub'] == ('flow.stack.summary[frames=6,hops=5,fails=1]')


def test_the_toggle_is_clickable_and_names_both_directions(drawn):
    assert 'data-stacktoggle' in drawn['toggleOn']
    assert 'flow.stack.show' in drawn['toggleOn']
    assert 'flow.stack.hide' in drawn['toggleOff']
    assert '<rect' in drawn['toggleOn'], 'the toggle must have a hit area of its own'


def test_a_resize_keeps_the_stack_pinned_to_the_top(viewer_template):
    """fit() recentres vertically; a stack is read top-down, so a resize while the
    stack is drawn must go through fitTop() like every other refit (13.5)."""
    with open(viewer_template, encoding='utf-8') as fh:
        html = fh.read()
    handler = re.search(r"addEventListener\('resize',\s*(.*?)\);\n", html)
    assert handler, 'resize handler not found'
    assert re.search(r'isStackDrawn\(\)\s*\?\s*fitTop\(\)\s*:\s*fit\(\)', handler.group(1)), (
        'the resize handler must dispatch on isStackDrawn(), got: ' + handler.group(1))

