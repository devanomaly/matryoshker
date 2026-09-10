"""test_viewer_fanout.py — topology of the Flow scene's fan-out grouping.

Extracts groupHops() from viewer/template.html between its sentinel comments and
runs it under `node` against the hops of tests/fixtures/branching-usecases.json,
resolved through the pipeline. The function is required to be pure (no DOM, no
globals, no layout constants) precisely so this extraction can execute it.

Reference: docs/data-contract.md, section 5.1.
"""
import json
import os
import re
import subprocess

from conftest import skip_without_node_binary

from pipeline import usecases

FIXTURE_UCS = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           'fixtures', 'branching-usecases.json')

BEGIN = '// --- fan-out grouping (data-contract 5.1) ---'
END = '// --- end fan-out grouping ---'


def extract_group_hops(template_path):
    """The source between the sentinels, or fail loudly if they are not there."""
    html = open(template_path, encoding='utf-8').read()
    start = html.find(BEGIN)
    end = html.find(END)
    assert start >= 0, f'sentinel not found in {template_path}: {BEGIN}'
    assert end > start, f'sentinel not found after the opening one: {END}'
    return html[start + len(BEGIN):end]


def resolved_fixture_hops():
    """The ten fixture hops as the viewer receives them, with their derived `k`."""
    raw = json.load(open(FIXTURE_UCS, encoding='utf-8'))
    paths, seen = [], set()
    for line in raw[0]['hops']:
        path = line.split(':', 1)[0].strip()
        if path not in seen:
            seen.add(path)
            paths.append(path)
    find_file = usecases.make_file_finder({p: n for n, p in enumerate(paths)})
    hops = []
    for line in raw[0]['hops']:
        hop, reason = usecases.parse_hop(line, find_file)
        assert hop is not None, reason
        hops.append(hop)
    return hops


def run_group_hops(tmp_path, viewer_template, hops):
    """Run the extracted groupHops() over `hops` and return the levels it built."""
    skip_without_node_binary()
    script = tmp_path / 'fanout.js'
    script.write_text(
        extract_group_hops(viewer_template)
        + '\nconst HOPS = ' + json.dumps(hops) + ';\n'
        + 'console.log(JSON.stringify(groupHops(HOPS)));\n',
        encoding='utf-8')
    result = subprocess.run(['node', str(script)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def edge_count(levels):
    """Cartesian product between consecutive levels, per data-contract 5.1."""
    return sum(len(a['hops']) * len(b['hops']) for a, b in zip(levels, levels[1:]))


def test_fixture_groups_into_six_levels(tmp_path, viewer_template):
    levels = run_group_hops(tmp_path, viewer_template, resolved_fixture_hops())
    assert len(levels) == 6
    assert [lv['n'] for lv in levels] == [1, 2, 3, 4, 5, 6]


def test_fixture_has_three_fans_of_three_two_and_two(tmp_path, viewer_template):
    levels = run_group_hops(tmp_path, viewer_template, resolved_fixture_hops())
    fans = [len(lv['hops']) for lv in levels if lv['fan']]
    assert fans == [3, 2, 2]
    assert [lv['n'] for lv in levels if lv['fan']] == [2, 4, 6]


def test_levels_three_and_five_are_non_fan_reconvergences(tmp_path, viewer_template):
    levels = run_group_hops(tmp_path, viewer_template, resolved_fixture_hops())
    for n in (1, 3, 5):
        level = levels[n - 1]
        assert level['fan'] is False
        assert len(level['hops']) == 1


def test_last_level_is_a_fan_that_ends_the_chain(tmp_path, viewer_template):
    levels = run_group_hops(tmp_path, viewer_template, resolved_fixture_hops())
    assert levels[-1]['fan'] is True
    assert levels[-1]['n'] == 6
    assert len(levels[-1]['hops']) == 2


def test_fixture_draws_twelve_edges(tmp_path, viewer_template):
    # 1x3 + 3x1 + 1x2 + 2x1 + 1x2 = 12, derived from the cartesian-product rule.
    levels = run_group_hops(tmp_path, viewer_template, resolved_fixture_hops())
    assert edge_count(levels) == 12


def test_hops_without_k_keep_one_level_per_hop(tmp_path, viewer_template):
    """Backward compatibility: a registry with no role prefixes numbers 1..N."""
    hops = [{'i': n, 's': f'f{n}', 'r': 'does a thing'} for n in range(5)]
    levels = run_group_hops(tmp_path, viewer_template, hops)
    assert len(levels) == len(hops)
    assert not any(lv['fan'] for lv in levels)
    assert [lv['n'] for lv in levels] == [1, 2, 3, 4, 5]
    assert edge_count(levels) == 4


def test_a_leading_branch_hop_opens_a_fan_with_no_incoming_edge(tmp_path, viewer_template):
    hops = [{'i': 0, 's': 'a', 'r': 'branch: a', 'k': 'branch'},
            {'i': 1, 's': 'b', 'r': 'branch: b', 'k': 'branch'},
            {'i': 2, 's': 'c', 'r': 'reconverges'}]
    levels = run_group_hops(tmp_path, viewer_template, hops)
    assert levels[0]['fan'] is True
    assert levels[0]['n'] == 1
    assert len(levels[0]['hops']) == 2
    assert len(levels) == 2
    assert edge_count(levels) == 2  # only the fan -> reconvergence edges


def test_a_fan_of_one_sibling_is_still_a_fan(tmp_path, viewer_template):
    hops = [{'i': 0, 's': 'a', 'r': 'selects'},
            {'i': 1, 's': 'b', 'r': 'branch: lone lateral', 'k': 'branch'},
            {'i': 2, 's': 'c', 'r': 'reconverges'}]
    levels = run_group_hops(tmp_path, viewer_template, hops)
    assert [lv['fan'] for lv in levels] == [False, True, False]
    assert edge_count(levels) == 2


# ---------------------------------------------------------------------------
# Map overlay (paintState) — file-level, so it dedups where the Flow scene does not
# ---------------------------------------------------------------------------

def map_rows(levels):
    """The rows the map overlay builds from `levels`: distinct files per level,
    dropping a file that just repeats the single file of the previous row."""
    rows = []
    for level in levels:
        row = []
        for hop in level['hops']:
            if hop['i'] in row:
                continue
            if rows and len(rows[-1]) == 1 and rows[-1][0] == hop['i']:
                continue
            row.append(hop['i'])
        if row:
            rows.append(row)
    return rows


def test_map_overlay_shows_the_level_two_fan(tmp_path, viewer_template):
    """The level-2 siblings live in three distinct files, so the file-level
    overlay can draw them as a fan of three."""
    levels = run_group_hops(tmp_path, viewer_template, resolved_fixture_hops())
    rows = map_rows(levels)
    assert len(rows[1]) == 3
    assert len(set(rows[1])) == 3


def test_map_overlay_collapses_the_level_six_fan(tmp_path, viewer_template):
    """Documented limitation: level 6's siblings and its selector are all the same
    file, so nothing of that fan survives the overlay's file-level dedup."""
    levels = run_group_hops(tmp_path, viewer_template, resolved_fixture_hops())
    selector_file = levels[4]['hops'][0]['i']
    assert {h['i'] for h in levels[5]['hops']} == {selector_file}
    rows = map_rows(levels)
    assert len(rows) == 5, 'the level-6 fan collapses into its selector row'
