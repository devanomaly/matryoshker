"""test_frames.py — the call stack behind a use-case's hops (data-contract 4.4, 7.4).

Everything here runs against `tests/fixtures/stack-frames/`: a small English repo
(`repo/orders/…`) and the extraction the real extractor produced from it, committed
beside it. The registry of that fixture exercises the five proof states, the status
ceiling and every edge kind the stack view draws, so these tests assert on a build of
real code rather than on hand-written index arithmetic.

One test needs `node` (it re-runs the extractor to prove the committed extraction is
still what the extractor emits, and that the function-body import really is invisible
to it); every other test is pure Python.

Reference: docs/data-contract.md, sections 4.4, 5.5, 7.4, 10.3 and 11.
"""
import json
import os
import re
import subprocess
import sys

import pytest

from conftest import REPO_ROOT, skip_without_node

from pipeline import prep_data, usecases
from pipeline.config import load_config

FIXTURE = os.path.join(REPO_ROOT, 'tests', 'fixtures', 'stack-frames')
FIXTURE_REPO = os.path.join(FIXTURE, 'repo')
ES = os.path.join(FIXTURE, 'es-output.json')
IM = os.path.join(FIXTURE, 'im-output.json')
CONFIG = os.path.join(FIXTURE, 'config.json')
USECASES = os.path.join(FIXTURE, 'usecases.json')

# The use-case of the fixture registry that carries frames, and the one that does not.
WITH_FRAMES = 0
WITHOUT_FRAMES = 1


def read(path):
    with open(path, encoding='utf-8') as fh:
        return json.load(fh)


@pytest.fixture(scope='module')
def extraction():
    """files, imports and the file finder of the fixture extraction."""
    config = load_config(CONFIG, '--config')
    files, path_index = prep_data.build_files(read(ES), prep_data.build_categorizer(config))
    imports = prep_data.build_imports(read(IM), path_index)
    return files, imports, usecases.make_file_finder(path_index, config['hop_path_prefixes'])


def index_of(files, path):
    """Index of `path` in the extraction, so a test never hardcodes a number."""
    for n, record in enumerate(files):
        if record['p'] == path:
            return n
    raise AssertionError(f'{path} is not in the fixture extraction')


def build(extraction, registry_path):
    """Run the pipeline over one registry file; returns (ucs, totals)."""
    files, imports, find_file = extraction
    totals = {'hops': 0, 'dropped': 0, 'use_cases': 0}
    ucs = prep_data.build_ucs(usecases.load_usecases(registry_path, '--ucs'),
                              files, find_file, totals, imports)
    return ucs, totals


def write_registry(tmp_path, entries, name='usecases.json'):
    path = tmp_path / name
    path.write_text(json.dumps(entries), encoding='utf-8')
    return str(path)


def one_uc(frames, hops=(), status='inferred', name='UC'):
    """A registry with a single use-case carrying `frames`."""
    return [{'name': name, 'status': status, 'hops': list(hops), 'frames': frames}]


def frames_of(ucs, index=WITH_FRAMES):
    return ucs[index]['frames']


def by_id(frames):
    return {f['id']: f for f in frames}


# ---------------------------------------------------------------------------
# the fixture registry, built end to end
# ---------------------------------------------------------------------------

def test_every_fixture_frame_resolves_to_the_file_it_cites(extraction):
    files, _, _ = extraction
    ucs, _ = build(extraction, USECASES)
    cited = [files[f['i']]['p'] for f in frames_of(ucs)]
    assert cited == ['orders/api/views.py', 'orders/common/mixins.py',
                     'orders/services/checkout.py', 'orders/services/checkout.py',
                     'orders/gateway/payments.py', 'orders/common/queue.py',
                     'orders/tasks/notify.py', 'orders/models/order.py']


def test_a_frame_emits_exactly_the_fourteen_contract_keys(extraction):
    ucs, _ = build(extraction, USECASES)
    for frame in frames_of(ucs):
        assert tuple(frame) == prep_data.FRAME_KEYS, (
            'a frame emits exactly the keys of data-contract 7.4, in that order')


def test_depth_comes_from_the_parent_chain_and_a_worker_reopens_at_zero(extraction):
    ucs, _ = build(extraction, USECASES)
    depths = {f['id']: f['d'] for f in frames_of(ucs)}
    assert depths == {'S1': 0, 'S2': 1, 'S3': 1, 'S4': 2, 'S5': 2, 'S6': 2,
                      'S7': 0, 'S8': 1}, (
        'S7 is a worker frame: it reopens the stack at 0 although its parent sits at 2, '
        'and S8 is one call deeper than S7')


def test_the_five_proof_states_all_appear_in_the_fixture(extraction):
    ucs, _ = build(extraction, USECASES)
    proofs = {f['id']: f['proof'] for f in frames_of(ucs)}
    assert proofs == {'S1': 'entry',        # no parent
                      'S2': 'import',       # views.py imports mixins.py
                      'S3': 'import',
                      'S4': 'same_file',    # both in checkout.py
                      'S5': 'import',
                      'S6': 'import',
                      'S7': 'unprovable',   # worker hand-off: the graph cannot speak
                      'S8': 'fail'}         # a plain call with no import edge
    assert {f['id']: f['ok'] for f in frames_of(ucs)}['S8'] is False
    assert all(f['ok'] for f in frames_of(ucs) if f['id'] != 'S8')


def test_the_failing_frame_names_both_files_in_its_reason(extraction):
    ucs, _ = build(extraction, USECASES)
    failing = by_id(frames_of(ucs))['S8']
    assert failing['why'] == ('orders/tasks/notify.py does not import '
                              'orders/models/order.py in the import graph')


def test_an_other_edge_keeps_its_note_and_a_mock_reason_keeps_its_prefix(extraction):
    ucs, _ = build(extraction, USECASES)
    gateway = by_id(frames_of(ucs))['S5']
    assert gateway['e'] == 'other'
    assert gateway['en'].startswith('into the payment provider')
    assert gateway['sr'].startswith('mock:'), (
        "the mock: prefix is a note inside status_reason, not a status value")
    assert gateway['st'] in usecases.STATUSES


def test_a_registry_without_frames_emits_no_frames_key(extraction):
    ucs, _ = build(extraction, USECASES)
    assert 'frames' not in ucs[WITHOUT_FRAMES], (
        'frames is optional: a use-case that declares none must be byte for byte '
        'what it was before frames existed')
    assert 'frames' in ucs[WITH_FRAMES]


def test_the_fixture_registry_reports_nothing_on_stderr(extraction, capsys):
    build(extraction, USECASES)
    assert capsys.readouterr().err == '', (
        'the committed fixture must build clean: every hop is a frame, every citation '
        'resolves and every symbol is declared')


# ---------------------------------------------------------------------------
# status ceiling
# ---------------------------------------------------------------------------

def test_a_frame_never_outranks_its_use_case_even_through_an_alias(extraction, tmp_path):
    """The fixture's S4 asks for `verificado-agente` under an `inferred` use-case."""
    ucs, _ = build(extraction, USECASES)
    assert by_id(frames_of(ucs))['S4']['st'] == 'inferred'

    registry = write_registry(tmp_path, one_uc(
        status='hypothesis',
        hops=['orders/api/views.py:CheckoutView — enters'],
        frames=[{'id': 'A', 'parent': None, 'edge': 'entry',
                 'hop': 'orders/api/views.py:CheckoutView',
                 'status': 'verificado-humano'}]))
    built, _ = build(extraction, registry)
    assert frames_of(built)[0]['st'] == 'hypothesis', (
        'human-verified through its v1 alias is still capped at the use-case status')


def test_a_frame_below_the_use_case_keeps_its_own_status(extraction):
    ucs, _ = build(extraction, USECASES)
    assert by_id(frames_of(ucs))['S8']['st'] == 'outdated', (
        'the ceiling only ever lowers a status')


def test_a_frame_without_a_status_inherits_the_use_case(extraction):
    ucs, _ = build(extraction, USECASES)
    assert by_id(frames_of(ucs))['S1']['st'] == ucs[WITH_FRAMES]['status'] == 'inferred'


# ---------------------------------------------------------------------------
# what is dropped, and what only warns
# ---------------------------------------------------------------------------

def test_a_frame_whose_citation_does_not_resolve_is_dropped_and_reported(
        extraction, tmp_path, capsys):
    registry = write_registry(tmp_path, one_uc(frames=[
        {'id': 'A', 'parent': None, 'edge': 'entry', 'hop': 'orders/api/views.py:CheckoutView'},
        {'id': 'B', 'parent': 'A', 'edge': 'call', 'hop': 'orders/nowhere/gone.py:Missing'}]))
    ucs, totals = build(extraction, registry)
    assert [f['id'] for f in frames_of(ucs)] == ['A']
    err = capsys.readouterr().err
    assert 'UC UC: 1/2 frames resolved' in err
    assert '  dropped [file not found in the extraction]: orders/nowhere/gone.py:Missing' in err
    assert totals['frames_dropped'] == 1


def test_dropping_a_frame_cascades_to_its_whole_subtree(extraction, tmp_path, capsys):
    registry = write_registry(tmp_path, one_uc(frames=[
        {'id': 'A', 'parent': None, 'edge': 'entry', 'hop': 'orders/api/views.py:CheckoutView'},
        {'id': 'B', 'parent': 'A', 'edge': 'call', 'hop': 'orders/nowhere/gone.py'},
        {'id': 'C', 'parent': 'B', 'edge': 'call', 'hop': 'orders/models/order.py:Order'},
        {'id': 'D', 'parent': 'C', 'edge': 'call', 'hop': 'orders/models/order.py:Order.total'}]))
    ucs, totals = build(extraction, registry)
    assert [f['id'] for f in frames_of(ucs)] == ['A'], (
        'C lost its parent with B, and D lost its parent with C: a detached frame must '
        'not be silently redrawn as a root of the stack')
    err = capsys.readouterr().err
    assert '  dropped [parent "B" not in frames]: orders/models/order.py:Order' in err
    assert '  dropped [parent "C" not in frames]: orders/models/order.py:Order.total' in err
    assert totals['frames_dropped'] == 3


def test_a_frame_pointing_at_a_parent_that_never_existed_is_dropped(extraction, tmp_path, capsys):
    registry = write_registry(tmp_path, one_uc(frames=[
        {'id': 'A', 'parent': None, 'edge': 'entry', 'hop': 'orders/api/views.py:CheckoutView'},
        {'id': 'B', 'parent': 'TYPO', 'edge': 'call', 'hop': 'orders/models/order.py:Order'}]))
    ucs, _ = build(extraction, registry)
    assert [f['id'] for f in frames_of(ucs)] == ['A']
    assert 'dropped [parent "TYPO" not in frames]' in capsys.readouterr().err


def test_an_unknown_edge_warns_and_becomes_other_instead_of_a_false_red(
        extraction, tmp_path, capsys):
    registry = write_registry(tmp_path, one_uc(frames=[
        {'id': 'A', 'parent': None, 'edge': 'entry', 'hop': 'orders/api/views.py:CheckoutView'},
        {'id': 'B', 'parent': 'A', 'edge': 'websocket',
         'hop': 'orders/models/order.py:Order'}]))
    ucs, _ = build(extraction, registry)
    frame = frames_of(ucs)[1]
    assert frame['e'] == 'other'
    assert frame['proof'] == 'unprovable', (
        'coercing an unknown edge to call would paint a red that the registry never '
        'claimed: views.py does not import order.py')
    assert ('warning: UC UC: frame B: unknown edge "websocket", using "other"'
            in capsys.readouterr().err)


def test_a_duplicate_frame_id_keeps_the_first_and_warns(extraction, tmp_path, capsys):
    registry = write_registry(tmp_path, one_uc(frames=[
        {'id': 'A', 'parent': None, 'edge': 'entry', 'hop': 'orders/api/views.py:CheckoutView'},
        {'id': 'A', 'parent': None, 'edge': 'entry', 'hop': 'orders/models/order.py:Order'}]))
    ucs, _ = build(extraction, registry)
    frames = frames_of(ucs)
    assert len(frames) == 1 and frames[0]['s'] == 'CheckoutView'
    assert 'warning: UC UC: duplicate frame id "A", keeping the first' in capsys.readouterr().err


def test_a_frame_with_an_undeclared_symbol_is_kept_and_warned_like_a_hop(
        extraction, tmp_path, capsys):
    registry = write_registry(tmp_path, one_uc(frames=[
        {'id': 'A', 'parent': None, 'edge': 'entry',
         'hop': 'orders/api/views.py:CheckoutView.deleted_method'}]))
    ucs, _ = build(extraction, registry)
    assert len(frames_of(ucs)) == 1, 'an undeclared symbol warns, it never drops the frame'
    err = capsys.readouterr().err
    assert ('unverified symbol [CheckoutView.deleted_method not declared in '
            'orders/api/views.py]') in err
    assert 'sym_ok' not in json.dumps(ucs), 'the result of that check is not stored'


# ---------------------------------------------------------------------------
# the invariant: every hop is a frame
# ---------------------------------------------------------------------------

def test_a_hop_with_no_frame_is_reported(extraction, tmp_path, capsys):
    registry = write_registry(tmp_path, one_uc(
        hops=['orders/api/views.py:CheckoutView — enters',
              'orders/models/order.py:Order.mark_paid — never made it into the stack'],
        frames=[{'id': 'A', 'parent': None, 'edge': 'entry',
                 'hop': 'orders/api/views.py:CheckoutView'}]))
    _, totals = build(extraction, registry)
    err = capsys.readouterr().err
    assert ('  hop without frame [no frame cites orders/models/order.py:Order.mark_paid]: '
            'orders/models/order.py:Order.mark_paid — never made it into the stack') in err
    assert totals['unframed_hops'] == 1


def test_a_hop_without_a_symbol_matches_any_frame_of_its_file(extraction, tmp_path, capsys):
    registry = write_registry(tmp_path, one_uc(
        hops=['orders/services/checkout.py — the whole file is the step'],
        frames=[{'id': 'A', 'parent': None, 'edge': 'entry',
                 'hop': 'orders/services/checkout.py:validate_items'}]))
    _, totals = build(extraction, registry)
    assert totals['unframed_hops'] == 0
    assert 'hop without frame' not in capsys.readouterr().err


def test_a_frame_that_is_not_a_hop_is_never_reported(extraction, capsys):
    """Not every frame is a hop: that asymmetry is the point of the feature."""
    ucs, totals = build(extraction, USECASES)
    registry_only = [f['id'] for f in frames_of(ucs) if f['reg'] == 'frame only']
    assert registry_only, 'the fixture must carry frames the flat registry never lists'
    assert totals['unframed_hops'] == 0
    assert 'hop without frame' not in capsys.readouterr().err


def test_use_cases_without_frames_are_not_subject_to_the_invariant(extraction, capsys):
    _, totals = build(extraction, USECASES)
    assert totals['unframed_hops'] == 0, (
        'the second fixture use-case has three hops and no frames at all')
    assert 'frames resolved' not in capsys.readouterr().err


# ---------------------------------------------------------------------------
# a stack must reach a root
# ---------------------------------------------------------------------------

VIEW = 'orders/api/views.py:CheckoutView'
SERVICE = 'orders/services/checkout.py:CheckoutService.place'


def test_a_parent_cycle_is_dropped_because_it_never_reaches_a_root(extraction, tmp_path, capsys):
    registry = write_registry(tmp_path, one_uc(frames=[
        {'id': 'R', 'parent': None, 'edge': 'entry', 'hop': VIEW},
        {'id': 'A', 'parent': 'B', 'edge': 'call', 'hop': VIEW},
        {'id': 'B', 'parent': 'A', 'edge': 'call', 'hop': SERVICE}]))
    ucs, totals = build(extraction, registry)
    assert [f['id'] for f in frames_of(ucs)] == ['R'], 'the rooted frame survives, the cycle does not'
    assert totals['frames_dropped'] == 2
    stderr = capsys.readouterr().err
    assert 'dropped [parent chain of "A" never reaches a root]' in stderr
    assert 'dropped [parent chain of "B" never reaches a root]' in stderr


def test_a_frame_that_is_its_own_parent_is_dropped(extraction, tmp_path, capsys):
    registry = write_registry(tmp_path, one_uc(frames=[
        {'id': 'A', 'parent': 'A', 'edge': 'call', 'hop': VIEW}]))
    ucs, totals = build(extraction, registry)
    assert 'frames' not in ucs[0]
    assert totals['frames_dropped'] == 1
    assert 'dropped [parent chain of "A" never reaches a root]' in capsys.readouterr().err


def test_a_worker_frame_is_still_a_frame_of_its_parents_stack(extraction):
    """Reopening the depth is not the same as being a root: S7 hangs off S6."""
    ucs, totals = build(extraction, USECASES)
    assert by_id(frames_of(ucs))['S7']['parent'] == 'S6'
    assert totals['frames_dropped'] == 0


# ---------------------------------------------------------------------------
# rules of 4.4 that are kept but warned about
# ---------------------------------------------------------------------------

def test_an_other_edge_without_a_note_warns(extraction, tmp_path, capsys):
    registry = write_registry(tmp_path, one_uc(frames=[
        {'id': 'A', 'parent': None, 'edge': 'entry', 'hop': VIEW},
        {'id': 'B', 'parent': 'A', 'edge': 'other', 'hop': SERVICE}]))
    ucs, _ = build(extraction, registry)
    assert len(frames_of(ucs)) == 2, 'warned, not dropped'
    assert 'warning: UC UC: frame B: edge "other" without an edge_note' in capsys.readouterr().err


def test_a_line_reference_in_a_frame_citation_warns(extraction, tmp_path, capsys):
    registry = write_registry(tmp_path, one_uc(frames=[
        {'id': 'A', 'parent': None, 'edge': 'entry', 'hop': VIEW},
        {'id': 'B', 'parent': 'A', 'edge': 'call', 'hop': 'orders/services/checkout.py:120'},
        {'id': 'C', 'parent': 'A', 'edge': 'call', 'hop': 'orders/services/checkout.py:10-20'}]))
    ucs, _ = build(extraction, registry)
    assert len(frames_of(ucs)) == 3
    stderr = capsys.readouterr().err
    assert 'warning: UC UC: frame B: line reference "120" in a frame citation' in stderr
    assert 'warning: UC UC: frame C: line reference "10-20" in a frame citation' in stderr


def test_an_entry_edge_with_a_parent_warns(extraction, tmp_path, capsys):
    registry = write_registry(tmp_path, one_uc(frames=[
        {'id': 'A', 'parent': None, 'edge': 'entry', 'hop': VIEW},
        {'id': 'B', 'parent': 'A', 'edge': 'entry', 'hop': SERVICE}]))
    ucs, _ = build(extraction, registry)
    assert len(frames_of(ucs)) == 2
    assert 'warning: UC UC: frame B: edge "entry" on a frame that has a parent' in capsys.readouterr().err


def test_the_committed_fixture_triggers_none_of_those_warnings(extraction, capsys):
    build(extraction, USECASES)
    assert 'warning:' not in capsys.readouterr().err


# ---------------------------------------------------------------------------
# one vocabulary, several places: the copies are compared, not trusted
# ---------------------------------------------------------------------------

CONTRACT = os.path.join(REPO_ROOT, 'docs', 'data-contract.md')
SCHEMA = os.path.join(REPO_ROOT, 'schemas', 'usecases.schema.json')
TEMPLATE = os.path.join(REPO_ROOT, 'viewer', 'template.html')


def text_of(path):
    with open(path, encoding='utf-8') as fh:
        return fh.read()


def contract_slice(start, end):
    text = text_of(CONTRACT)
    begin = text.index(start)
    return text[begin:text.index(end, begin + len(start))]


def js_object_keys(name):
    """The keys of the top-level `const <name> = {...};` literal of the viewer."""
    match = re.search(r'const %s = \{(.*?)\};' % name, text_of(TEMPLATE), re.S)
    assert match, f'const {name} not found in viewer/template.html'
    return re.findall(r"(\w+)\s*:\s*[\['\"]", match.group(1))


def test_the_contract_key_table_lists_exactly_the_emitted_keys():
    table = contract_slice('#### `ucs[].frames`', 'Those fourteen keys')
    documented = re.findall(r'^\| `(\w+)` \|', table, re.M)
    assert tuple(documented) == prep_data.FRAME_KEYS, (
        'docs/data-contract.md 7.4 must list the emitted frame keys exactly, in order')
    assert len(prep_data.FRAME_KEYS) == 14, 'the contract says "fourteen keys"'


def test_the_contract_proof_table_lists_exactly_the_proof_states():
    table = contract_slice('**The five proof states**', '`fail` is the only red state')
    documented = re.findall(r'^\| `(\w+)` \|', table, re.M)
    assert documented[0] == 'proof', 'the header cell of the table'
    assert tuple(documented[1:]) == prep_data.FRAME_PROOFS
    assert len(prep_data.FRAME_PROOFS) == 5, 'the contract says "five proof states"'


def test_the_fixture_reaches_exactly_the_declared_proof_states(extraction):
    ucs, _ = build(extraction, USECASES)
    assert {f['proof'] for f in frames_of(ucs)} == set(prep_data.FRAME_PROOFS), (
        'the fixture reaches every declared state, so an undeclared one would show here')


def test_the_contract_names_exactly_the_edge_kinds():
    paragraph = contract_slice('**Edge kinds.**', '`worker` and `inbound` reopen')
    assert tuple(re.findall(r'`(\w+)` \(', paragraph)) == prep_data.FRAME_EDGES


def test_the_schema_edge_enum_is_the_pipeline_edge_list():
    enum = read(SCHEMA)['definitions']['frame']['properties']['edge']['enum']
    assert tuple(enum) == prep_data.FRAME_EDGES


def test_the_viewer_tables_cover_every_edge_and_every_proof():
    assert set(js_object_keys('STACK_GLYPH')) == set(prep_data.FRAME_EDGES)
    assert set(js_object_keys('STACK_PROOF')) == set(prep_data.FRAME_PROOFS)
    # entry and call draw no kind label and `other` shows its note; the rest need a string
    labelled = set(prep_data.FRAME_EDGES) - {'entry', 'call', 'other'}
    assert set(js_object_keys('STACK_EDGE')) == labelled
    html = text_of(TEMPLATE)
    for proof in prep_data.FRAME_PROOFS:
        assert f"'flow.stack.proof.{proof}'" in html
    for edge in labelled:
        assert f"'flow.stack.edge.{edge}'" in html


# ---------------------------------------------------------------------------
# --strict, through the CLI
# ---------------------------------------------------------------------------

def run_prep_data(out, ucs_path, strict=True):
    command = [sys.executable, os.path.join(REPO_ROOT, 'pipeline', 'prep_data.py'),
               '--es', ES, '--imports', IM, '--config', CONFIG, '--ucs', ucs_path,
               '--out', str(out)]
    if strict:
        command.append('--strict')
    # the child degrades what its console cannot encode (_common.warn); asking it for
    # UTF-8 keeps the em dash of a quoted hop readable on a cp1252 Windows runner
    env = dict(os.environ, PYTHONIOENCODING='utf-8')
    return subprocess.run(command, capture_output=True, text=True, encoding='utf-8', env=env)


def test_strict_is_green_on_the_committed_fixture(tmp_path):
    result = run_prep_data(tmp_path / 'data.json', USECASES)
    assert result.returncode == 0, result.stderr
    assert 'frames=8' in result.stdout


def test_strict_exits_three_on_a_hop_with_no_frame(tmp_path):
    registry = write_registry(tmp_path, one_uc(
        hops=['orders/api/views.py:CheckoutView — enters',
              'orders/models/order.py:Order.mark_paid — never made it into the stack'],
        frames=[{'id': 'A', 'parent': None, 'edge': 'entry',
                 'hop': 'orders/api/views.py:CheckoutView'}]))
    result = run_prep_data(tmp_path / 'data.json', registry)
    assert result.returncode == prep_data.STRICT_EXIT
    assert 'hop without frame [no frame cites orders/models/order.py:Order.mark_paid]' in result.stderr
    assert 'strict: 1 hops without a frame' in result.stderr


def test_strict_exits_three_on_a_dropped_frame(tmp_path):
    registry = write_registry(tmp_path, one_uc(frames=[
        {'id': 'A', 'parent': None, 'edge': 'entry', 'hop': 'orders/api/views.py:CheckoutView'},
        {'id': 'B', 'parent': 'A', 'edge': 'call', 'hop': 'orders/nowhere/gone.py'}]))
    result = run_prep_data(tmp_path / 'data.json', registry)
    assert result.returncode == prep_data.STRICT_EXIT
    assert 'strict: 1 frames dropped' in result.stderr


def test_strict_exits_three_on_a_parent_cycle(tmp_path):
    registry = write_registry(tmp_path, one_uc(frames=[
        {'id': 'A', 'parent': 'B', 'edge': 'call', 'hop': VIEW},
        {'id': 'B', 'parent': 'A', 'edge': 'call', 'hop': SERVICE}]))
    result = run_prep_data(tmp_path / 'data.json', registry)
    assert result.returncode == prep_data.STRICT_EXIT
    assert 'strict: 2 frames dropped' in result.stderr


def test_a_failing_proof_is_a_finding_not_a_gate(tmp_path):
    """`fail` is drawn red and never affects --strict: the registry often cannot fix
    it (the committed fixture carries one on purpose), so gating on it would make an
    honest registry unbuildable (data-contract 7.4, 10.3)."""
    result = run_prep_data(tmp_path / 'data.json', USECASES)
    assert result.returncode == 0, result.stderr
    data = read(str(tmp_path / 'data.json'))
    assert [f['id'] for f in data['ucs'][WITH_FRAMES]['frames'] if f['proof'] == 'fail'] == ['S8']


def test_without_strict_the_same_registry_exits_zero(tmp_path):
    registry = write_registry(tmp_path, one_uc(
        hops=['orders/models/order.py:Order.mark_paid — never made it into the stack'],
        frames=[{'id': 'A', 'parent': None, 'edge': 'entry',
                 'hop': 'orders/api/views.py:CheckoutView'}]))
    result = run_prep_data(tmp_path / 'data.json', registry, strict=False)
    assert result.returncode == 0, result.stderr
    assert 'hop without frame' in result.stderr, 'reported, but never fatal without --strict'


# ---------------------------------------------------------------------------
# the committed extraction, against the extractor of today
# ---------------------------------------------------------------------------

def test_the_committed_extraction_is_what_the_extractor_still_emits(tmp_path):
    """Re-extract `repo/` and compare, so a stale fixture fails here and nowhere else.

    It also pins the one property the `fail` proof state rests on: the import inside
    `send_receipt`'s body is invisible to the import graph.
    """
    skip_without_node()
    run_dir = tmp_path / 'extraction'
    run_dir.mkdir()
    result = subprocess.run(
        ['node', os.path.join(REPO_ROOT, 'extractor', 'extract.mjs'), FIXTURE_REPO,
         '--out', str(run_dir), '--lang', 'python'],
        capture_output=True, text=True, encoding='utf-8')
    assert result.returncode == 0, result.stderr

    fresh = read(str(run_dir / 'im-output.json'))['importMap']
    assert fresh == read(IM)['importMap'], (
        'tests/fixtures/stack-frames/im-output.json has drifted from repo/; regenerate '
        'it with extractor/extract.mjs (docs/data-contract.md 10.1)')

    assert fresh['orders/tasks/notify.py'] == [], (
        'send_receipt imports Order inside its function body: the import graph must stay '
        'blind to it, which is what makes the S8 frame a real `fail`')
    assert 'orders/models/order.py' in fresh['orders/services/checkout.py'], (
        'a module-level import of the same module is seen, so the blindness above is '
        'about where the import sits, not about the module')

    # whole records, not just their paths: a class that lost a method is drift too
    fresh_records = {r['path']: r for r in read(str(run_dir / 'es-output.json'))['results']}
    committed_records = {r['path']: r for r in read(ES)['results']}
    assert fresh_records == committed_records, (
        'tests/fixtures/stack-frames/es-output.json has drifted from repo/; regenerate '
        'it with extractor/extract.mjs (docs/data-contract.md 10.1)')
