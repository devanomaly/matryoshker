"""test_e2e.py — end-to-end tests against the golden extraction and the sample repo.

Two groups:

- Fast, deterministic tests that run prep_data.py, prep_extra.py and inject.py as
  subprocesses against the committed golden extraction (tests/golden/) — no Node,
  no filesystem scan, so these always run.
- Tests that need a real extraction (pipeline/build.py end to end, and the
  extractor's own golden_check.py) — these call node and skip cleanly, with a
  message, when node or extractor/node_modules is not available.
- Layout tests that run a pure JavaScript block extracted from viewer/template.html
  under node — these need the node binary only, never the extractor.

Reference: docs/data-contract.md, sections 1, 6, 8 and 10.
"""
import json
import os
import re
import subprocess
import sys

import pytest

from conftest import skip_without_node, skip_without_node_binary

SCRIPT_TAG = re.compile(r'<script(?:\s[^>]*)?>(.*?)</script>', re.S)


def run_pipeline_script(repo_root, script, args):
    """Run one pipeline/<script> as a subprocess, the way the CLI contract requires."""
    script_path = os.path.join(repo_root, 'pipeline', script)
    return subprocess.run([sys.executable, script_path, *args], cwd=repo_root,
                          capture_output=True, text=True, encoding='utf-8')


def parsers_count(stderr):
    match = re.search(r'(\d+) from parsers', stderr)
    assert match, f'expected the entry-points breakdown line in stderr, got: {stderr!r}'
    return int(match.group(1))


@pytest.fixture(params=['example.json', 'example-ddd.json'])
def config_name(request):
    return request.param


def test_build_data_extra_and_html_for_each_config(
        tmp_path, repo_root, golden_dir, config_dir, example_usecases,
        viewer_template, config_name):
    config_path = os.path.join(config_dir, config_name)
    es = os.path.join(golden_dir, 'es-output.json')
    im = os.path.join(golden_dir, 'im-output.json')
    data_path = tmp_path / 'data.json'
    extra_path = tmp_path / 'extra.json'
    out_path = tmp_path / 'matryoshker.html'

    raw_usecases = json.loads(open(example_usecases, encoding='utf-8').read())
    total_hops_written = sum(len(uc.get('hops', [])) for uc in raw_usecases)

    data_result = run_pipeline_script(repo_root, 'prep_data.py', [
        '--es', es, '--imports', im, '--config', config_path,
        '--ucs', example_usecases, '--out', str(data_path)])
    assert data_result.returncode == 0, data_result.stderr

    data = json.loads(data_path.read_text(encoding='utf-8'))
    assert data['meta']['nfiles'] > 0
    assert data['meta']['nimports'] > 0
    assert data['meta']['nucs'] == len(raw_usecases)
    resolved_hops = sum(len(uc['hops']) for uc in data['ucs'])
    assert resolved_hops == total_hops_written, (
        f'expected every hop of examples/sample-drf/usecases.json to resolve against '
        f'the golden extraction; stderr was: {data_result.stderr!r}')

    extra_result = run_pipeline_script(repo_root, 'prep_extra.py', [
        '--es', es, '--imports', im, '--config', config_path,
        '--ucs', example_usecases, '--repo', os.path.join(repo_root, 'examples', 'sample-drf'),
        '--out', str(extra_path)])
    assert extra_result.returncode == 0, extra_result.stderr

    extra = json.loads(extra_path.read_text(encoding='utf-8'))
    assert extra['nfiles'] == data['meta']['nfiles']

    kinds = {e['kind'] for e in extra['entry_points']}
    if config_name == 'example.json':
        # config/example.json configures the django-drf parser: it contributes
        # HTTP routes on top of the use-cases' own declared/fallback entry points.
        assert {'http', 'command', 'other'} <= kinds
        assert parsers_count(extra_result.stderr) > 0
    else:
        # config/example-ddd.json has no entry_points.parsers: no route comes from
        # a parser, only from what the use-cases declare or fall back to. 'http'
        # can still appear here — some use-cases declare "http: ..." entry points
        # themselves, independently of any parser (data-contract 5.2/6.2) — so the
        # real signal that distinguishes the two configs is the parser count, not
        # the presence of the 'http' kind.
        assert parsers_count(extra_result.stderr) == 0

    inject_result = run_pipeline_script(repo_root, 'inject.py', [
        '--template', viewer_template, '--data', str(data_path),
        '--extra', str(extra_path), '--out', str(out_path)])
    assert inject_result.returncode == 0, inject_result.stderr
    assert out_path.exists()
    assert out_path.stat().st_size > 0

    html = out_path.read_text(encoding='utf-8')
    assert '__MATRYOSHKER_DATA__' not in html


# The HTML spec only scans the first 1024 bytes for an encoding declaration, and a
# document without one is decoded by guessing: over HTTP with no charset in the
# Content-Type, Chromium falls back to windows-1252 and the map renders mojibake.
CHARSET_PRESCAN_BYTES = 1024
CHARSET_META = re.compile(rb'<meta[^>]+charset\s*=\s*["\']?utf-8', re.I)


def test_template_declares_utf8_in_the_prescan_window(viewer_template):
    """The viewer template must declare UTF-8 early enough for a browser to see it.

    The viewer's own text carries non-ASCII characters (the middle-dot separator,
    em dashes, ellipses, arrows, and every accented character of the pt-BR
    UI_STRINGS table), so a missing declaration is not cosmetic.
    """
    with open(viewer_template, 'rb') as fh:
        head = fh.read(CHARSET_PRESCAN_BYTES)
    assert CHARSET_META.search(head), (
        'viewer/template.html must declare <meta charset="utf-8"> within the first '
        f'{CHARSET_PRESCAN_BYTES} bytes; without it a browser guesses the encoding '
        'and non-ASCII UI text renders as mojibake')


def test_injected_html_keeps_the_charset_declaration(
        tmp_path, repo_root, golden_dir, config_dir, example_usecases, viewer_template):
    """inject.py must not push the declaration out of the browser's prescan window."""
    data_path = tmp_path / 'data.json'
    out_path = tmp_path / 'matryoshker.html'

    assert run_pipeline_script(repo_root, 'prep_data.py', [
        '--es', os.path.join(golden_dir, 'es-output.json'),
        '--imports', os.path.join(golden_dir, 'im-output.json'),
        '--config', os.path.join(config_dir, 'example.json'),
        '--ucs', example_usecases, '--out', str(data_path)]).returncode == 0
    assert run_pipeline_script(repo_root, 'inject.py', [
        '--template', viewer_template, '--data', str(data_path),
        '--out', str(out_path)]).returncode == 0

    head = out_path.read_bytes()[:CHARSET_PRESCAN_BYTES]
    assert CHARSET_META.search(head), (
        'the generated HTML lost its charset declaration, or it was pushed past the '
        f'first {CHARSET_PRESCAN_BYTES} bytes')
    assert 'Â·' not in out_path.read_text(encoding='utf-8')


def test_last_script_of_injected_html_is_valid_javascript(
        tmp_path, repo_root, golden_dir, config_dir, example_usecases, viewer_template):
    """The template's second <script> (the viewer app) must still be syntactically
    valid JavaScript once the data has been injected into the first one."""
    skip_without_node()

    es = os.path.join(golden_dir, 'es-output.json')
    im = os.path.join(golden_dir, 'im-output.json')
    data_path = tmp_path / 'data.json'
    out_path = tmp_path / 'matryoshker.html'

    assert run_pipeline_script(repo_root, 'prep_data.py', [
        '--es', es, '--imports', im, '--config', os.path.join(config_dir, 'example.json'),
        '--ucs', example_usecases, '--out', str(data_path)]).returncode == 0
    assert run_pipeline_script(repo_root, 'inject.py', [
        '--template', viewer_template, '--data', str(data_path),
        '--out', str(out_path)]).returncode == 0

    html = out_path.read_text(encoding='utf-8')
    scripts = SCRIPT_TAG.findall(html)
    assert len(scripts) >= 2, 'expected at least the data script and the app script'
    app_script = scripts[-1]

    script_path = tmp_path / 'app.js'
    script_path.write_text(app_script, encoding='utf-8')
    result = subprocess.run(['node', '--check', str(script_path)],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_build_py_end_to_end_against_sample_drf(tmp_path, repo_root, config_dir, example_usecases):
    """python pipeline/build.py, all four steps, against the real sample repo."""
    skip_without_node()

    out_path = tmp_path / 'matryoshker.html'
    extract_out = tmp_path / 'out'
    result = subprocess.run([
        sys.executable, os.path.join(repo_root, 'pipeline', 'build.py'),
        '--repo', os.path.join(repo_root, 'examples', 'sample-drf'),
        '--config', os.path.join(config_dir, 'example.json'),
        '--ucs', example_usecases,
        '--out', str(out_path),
        '--extract-out', str(extract_out),
        '--lang', 'python',
    ], cwd=repo_root, capture_output=True, text=True, encoding='utf-8')

    assert result.returncode == 0, f'stdout={result.stdout!r} stderr={result.stderr!r}'
    assert out_path.exists()
    assert out_path.stat().st_size > 0
    html = out_path.read_text(encoding='utf-8')
    assert '__MATRYOSHKER_DATA__' not in html
    assert '<script type="application/json" id="data">' in html


def test_golden_check_against_fresh_extraction(tmp_path, repo_root, golden_dir):
    """extractor/golden_check.py, run against a fresh extraction of examples/sample-drf.

    Regenerated exactly as CONTRIBUTING/README document it (--lang python), so a
    failure here means the committed extraction in tests/golden/ has drifted from
    examples/sample-drf and needs to be regenerated — not a bug in this test.
    """
    skip_without_node()

    run_dir = tmp_path / 'golden-run'
    run_dir.mkdir()
    extract_result = subprocess.run([
        'node', os.path.join(repo_root, 'extractor', 'extract.mjs'),
        os.path.join(repo_root, 'examples', 'sample-drf'),
        '--out', str(run_dir), '--lang', 'python',
    ], capture_output=True, text=True, encoding='utf-8')
    assert extract_result.returncode == 0, extract_result.stderr

    check_result = subprocess.run([
        sys.executable, os.path.join(repo_root, 'extractor', 'golden_check.py'),
        '--run-dir', str(run_dir), '--golden-dir', golden_dir,
    ], capture_output=True, text=True, encoding='utf-8')

    assert check_result.returncode == 0, (
        'extractor/golden_check.py reported a divergence between a fresh extraction '
        'of examples/sample-drf and the committed tests/golden/ fixture (likely stale '
        'relative to the sample repo, not a test bug):\n' + check_result.stdout)


GEOMETRY_BLOCK = re.compile(
    r'// --- pure layout geometry.*?---\n(.*?)// --- end pure layout geometry ---', re.S)

# Drives the extracted block the way layoutPac does and reports what the ticket cares
# about: the shape of the packed map and whether every label fits inside its own box.
GEOMETRY_HARNESS = """
const spec = JSON.parse(process.argv[process.argv.length - 1]);
const cls = packClusters(spec.map(([key, n]) => [key, Array.from({length: n}, (_, i) => i)]));
const W = Math.max(...cls.map(c => c.x + c.w)), H = Math.max(...cls.map(c => c.y + c.h));
let overlap = false;
for (let i = 0; i < cls.length; i++) for (let j = i + 1; j < cls.length; j++) {
  const a = cls[i], b = cls[j];
  if (a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h) overlap = true;
}
console.log(JSON.stringify({
  w: W, h: H, overlap,
  labels: cls.map(c => ({shown: c.shown, full: c.label,
                         room: c.w - 2 * PAD, width: textW(c.shown, CLABEL_CHARW)}))}));
"""

FIXTURE_CLUSTERS = [['catalog', 5], ['lending/handlers', 3], ['lending/services', 3],
                    ['library', 3], ['catalog/services', 2], ['lending', 2],
                    ['lending/domain', 2], ['lending/tasks', 2], ['(root)', 1]]
STRESS_CLUSTERS = [[f'package{i}/subpackage_number_{i}', (i % 17) + 1] for i in range(48)]


def run_geometry(viewer_template, tmp_path, clusters):
    """Run the viewer's pure layout block under node against a list of [key, n_files]."""
    source = open(viewer_template, encoding='utf-8').read()
    match = GEOMETRY_BLOCK.search(source)
    assert match, 'viewer/template.html lost its "pure layout geometry" block'
    script = tmp_path / 'geometry.mjs'
    script.write_text(match.group(1) + GEOMETRY_HARNESS, encoding='utf-8')
    result = subprocess.run(['node', str(script), json.dumps(clusters)],
                            capture_output=True, text=True, encoding='utf-8')
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


@pytest.mark.parametrize('clusters', [FIXTURE_CLUSTERS, STRESS_CLUSTERS],
                         ids=['fixture', 'stress'])
def test_packages_layout_is_compact_and_labels_fit(viewer_template, tmp_path, clusters):
    """The packed map must stay near a screen aspect ratio for a small repo and for a
    much larger one, the cluster boxes must not overlap, and every drawn label must fit
    inside its own box (the width comes from the content, never from the viewport)."""
    # only the node binary: this runs a pure JS block out of the template and never
    # touches the extractor, so extractor/node_modules being absent is irrelevant.
    skip_without_node_binary()
    out = run_geometry(viewer_template, tmp_path, clusters)
    ratio = out['w'] / out['h']
    assert 0.7 <= ratio <= 2.6, f'aspect ratio {ratio:.2f} for {len(clusters)} clusters'
    assert not out['overlap'], 'two cluster boxes overlap'
    for label in out['labels']:
        assert label['width'] <= label['room'] + 1e-6, label
        assert label['shown'] == label['full'] or label['shown'].endswith('…'), label
