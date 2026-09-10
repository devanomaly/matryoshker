"""test_pipeline.py — unit tests for the pipeline modules.

Runs against the pipeline's Python API directly (no subprocess), so these tests
are fast and pin down behavior module by module. End-to-end behavior (running the
CLIs against the golden extraction) lives in test_e2e.py.

Reference: docs/data-contract.md, sections 3, 4, 5, 6, 8 and 9.
"""
import json
import os
import sys

import pytest

from pipeline import config as config_mod
from pipeline import inject, prep_data, prep_extra, usecases
from pipeline import entry_points as entry_points_pkg
from pipeline.entry_points import django_drf, merge_entry_points


# ---------------------------------------------------------------------------
# Categorizer (prep_data.build_categorizer) — data-contract section 3.3
# ---------------------------------------------------------------------------

def _categorizer(rules, fallback='other', test_marker='/tests', test_category='tests'):
    config = {'rules': rules, 'fallback_category': fallback,
              'test_path_marker': test_marker, 'test_category': test_category}
    return prep_data.build_categorizer(config)


def test_categorizer_first_matching_rule_wins():
    categorize = _categorizer([['src/app/', 'app'], ['src/', 'other-src']])
    assert categorize('src/app/main.py') == 'app'
    assert categorize('src/lib/util.py') == 'other-src'


def test_categorizer_more_specific_rule_must_be_listed_first():
    # src/app/ is a prefix of src/apple/ too — rule order, not rule specificity,
    # decides. This documents the ordering contract rather than "smart" matching.
    categorize = _categorizer([['src/app', 'app'], ['src/apple', 'apple']])
    assert categorize('src/apple/x.py') == 'app'


def test_categorizer_test_marker_overrides_fallback():
    categorize = _categorizer([], fallback='other', test_marker='/tests')
    assert categorize('pkg/tests/test_x.py') == 'tests'


def test_categorizer_fallback_when_nothing_matches():
    categorize = _categorizer([['src/', 'app']], fallback='misc', test_marker='/tests')
    assert categorize('docs/readme.py') == 'misc'


def test_categorizer_rules_win_over_test_marker():
    categorize = _categorizer([['pkg/tests/fixtures/', 'fixtures']], test_marker='/tests')
    assert categorize('pkg/tests/fixtures/data.py') == 'fixtures'


def test_categorizer_disabled_test_marker():
    categorize = _categorizer([], fallback='other', test_marker='')
    assert categorize('pkg/tests/test_x.py') == 'other'


# ---------------------------------------------------------------------------
# File finder (usecases.make_file_finder) — data-contract section 5.3
# ---------------------------------------------------------------------------

def test_find_file_exact_match():
    find_file = usecases.make_file_finder({'src/a.py': 0, 'src/b.py': 1})
    assert find_file('src/a.py') == (0, None)


def test_find_file_configured_prefix():
    find_file = usecases.make_file_finder({'src/app/a.py': 0}, hop_path_prefixes=['src/app'])
    assert find_file('a.py') == (0, None)


def test_find_file_configured_prefix_multiple_tried_in_order():
    find_file = usecases.make_file_finder({'lib/a.py': 0}, hop_path_prefixes=['src/', 'lib/'])
    assert find_file('a.py') == (0, None)


def test_find_file_unique_basename_match():
    find_file = usecases.make_file_finder({'pkg/deep/nested/x.py': 3})
    assert find_file('x.py') == (3, None)


def test_find_file_ambiguous_basename_is_dropped_with_reason():
    find_file = usecases.make_file_finder({'a/x.py': 0, 'b/x.py': 1})
    index, reason = find_file('x.py')
    assert index is None
    assert reason == 'ambiguous file name (2 files end with /x.py)'


def test_find_file_not_found():
    find_file = usecases.make_file_finder({'a/x.py': 0})
    index, reason = find_file('missing.py')
    assert index is None
    assert reason == 'file not found in the extraction'


# ---------------------------------------------------------------------------
# Hop citation grammar — data-contract section 5.1 / 5.3
# ---------------------------------------------------------------------------

def test_parse_hop_em_dash_separator():
    find_file = usecases.make_file_finder({'src/a.py': 0})
    hop, reason = usecases.parse_hop('src/a.py:Foo.bar — validates the payload', find_file)
    assert reason is None
    assert hop == {'i': 0, 's': 'Foo.bar', 'r': 'validates the payload'}


def test_parse_hop_en_dash_separator():
    find_file = usecases.make_file_finder({'src/a.py': 0})
    hop, reason = usecases.parse_hop('src/a.py:Foo.bar – validates the payload', find_file)
    assert reason is None
    assert hop['r'] == 'validates the payload'


def test_parse_hop_hyphen_separator():
    find_file = usecases.make_file_finder({'src/a.py': 0})
    hop, reason = usecases.parse_hop('src/a.py:Foo.bar - validates the payload', find_file)
    assert reason is None
    assert hop['r'] == 'validates the payload'


def test_parse_hop_role_truncated_at_140_chars():
    find_file = usecases.make_file_finder({'src/a.py': 0})
    long_role = 'x' * 200
    hop, reason = usecases.parse_hop(f'src/a.py:Foo.bar — {long_role}', find_file)
    assert reason is None
    assert len(hop['r']) == 140
    assert hop['r'] == 'x' * 140


def test_parse_hop_no_separator_keeps_role():
    # No separator at all: the whole remainder after the citation is the role
    # (data-contract 5.3, a superset of the v1 grammar).
    find_file = usecases.make_file_finder({'src/a.py': 0})
    hop, reason = usecases.parse_hop('src/a.py:Foo.bar validates the payload', find_file)
    assert reason is None
    assert hop['r'] == 'validates the payload'


def test_parse_hop_no_citation_is_dropped():
    find_file = usecases.make_file_finder({'src/a.py': 0})
    hop, reason = usecases.parse_hop('nothing that looks like a file here', find_file)
    assert hop is None
    assert reason == 'no file citation'


def test_parse_hop_line_reference_symbol():
    find_file = usecases.make_file_finder({'src/a.py': 0})
    hop, reason = usecases.parse_hop('src/a.py:120-145 — the whole block', find_file)
    assert reason is None
    assert hop['s'] == '120-145'


def test_parse_hop_parens_stripped_from_symbol():
    find_file = usecases.make_file_finder({'src/a.py': 0})
    hop, reason = usecases.parse_hop('src/a.py:bar() — role', find_file)
    assert reason is None
    assert hop['s'] == 'bar'


# ---------------------------------------------------------------------------
# Entry-point citation grammar — data-contract section 5.2 / 5.3
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('kind, raw', [
    ('http', 'http: POST /v1/books (src/api/views.py:BookViewSet)'),
    ('command', 'command: src/domain/commands.py:RegisterBook — register'),
    ('event', 'event: src/events/x.py:Handler'),
    ('cli', 'cli: src/cli/x.py:Command'),
    ('cron', 'cron: src/jobs/x.py:Job'),
])
def test_parse_entry_point_kind_prefix(kind, raw):
    find_file = usecases.make_file_finder({
        'src/api/views.py': 0, 'src/domain/commands.py': 1, 'src/events/x.py': 2,
        'src/cli/x.py': 3, 'src/jobs/x.py': 4})
    entry, reason = usecases.parse_entry_point(raw, find_file, 'fallback name')
    assert reason is None
    assert entry['kind'] == kind


def test_parse_entry_point_default_kind_is_other():
    find_file = usecases.make_file_finder({'src/jobs/nightly.py': 0})
    entry, reason = usecases.parse_entry_point(
        'src/jobs/nightly.py:rebuild_index', find_file, 'fallback name')
    assert reason is None
    assert entry['kind'] == 'other'
    assert entry['label'] == 'fallback name'
    assert entry['symbol'] == 'rebuild_index'


def test_parse_entry_point_http_url_is_not_a_kind_prefix():
    # "http://..." must not be read as the kind prefix "http:".
    find_file = usecases.make_file_finder({'src/x.py': 0})
    entry, reason = usecases.parse_entry_point(
        'http://example.com src/x.py:Handler', find_file, 'fallback')
    assert reason is None
    assert entry['kind'] == 'other'


def test_parse_entry_point_label_precedence_label_over_text():
    find_file = usecases.make_file_finder({'src/api/views.py': 0})
    entry, reason = usecases.parse_entry_point(
        'http: POST /v1/books (src/api/views.py:BookViewSet) — trailing text',
        find_file, 'fallback')
    assert reason is None
    assert entry['label'] == 'POST /v1/books'
    assert entry['symbol'] == 'BookViewSet'


def test_parse_entry_point_label_falls_back_to_text_then_name():
    find_file = usecases.make_file_finder({'src/x.py': 0})
    entry, _ = usecases.parse_entry_point('src/x.py — does the thing', find_file, 'UC name')
    assert entry['label'] == 'does the thing'

    entry2, _ = usecases.parse_entry_point('src/x.py', find_file, 'UC name')
    assert entry2['label'] == 'UC name'


# ---------------------------------------------------------------------------
# Use-case key aliases (PT -> EN) and status aliases — data-contract section 4
# ---------------------------------------------------------------------------

def test_load_usecases_pt_aliases_mapped_to_canonical_keys(tmp_path):
    # The v1 keys are deliberately Portuguese (that is what the aliases exist for);
    # the values are English like the rest of the suite.
    raw = [{
        'nome': 'Actor does something',
        'ator': 'Actor',
        'objetivo': 'Business goal',
        'regras_envolvidas': ['RULE-01'],
        'hops': [],
        'status': 'inferido',
    }]
    path = tmp_path / 'usecases.json'
    path.write_text(json.dumps(raw), encoding='utf-8')

    ucs = usecases.load_usecases(str(path))
    assert len(ucs) == 1
    uc = ucs[0]
    assert uc['name'] == 'Actor does something'
    assert uc['actor'] == 'Actor'
    assert uc['goal'] == 'Business goal'
    assert uc['rules'] == ['RULE-01']
    assert uc['status'] == 'inferred'


def test_load_usecases_canonical_key_wins_when_both_present(tmp_path):
    raw = [{'nome': 'old name', 'name': 'new name', 'hops': []}]
    path = tmp_path / 'usecases.json'
    path.write_text(json.dumps(raw), encoding='utf-8')

    ucs = usecases.load_usecases(str(path))
    assert ucs[0]['name'] == 'new name'


def test_load_usecases_requires_unique_name(tmp_path):
    raw = [{'name': 'dup', 'hops': []}, {'name': 'dup', 'hops': []}]
    path = tmp_path / 'usecases.json'
    path.write_text(json.dumps(raw), encoding='utf-8')

    with pytest.raises(SystemExit, match='duplicate use-case name'):
        usecases.load_usecases(str(path))


@pytest.mark.parametrize('alias, canonical', [
    ('verificado-humano', 'human-verified'),
    ('verificado-agente', 'agent-verified'),
    ('inferido', 'inferred'),
    ('hipotese', 'hypothesis'),
    ('hipótese', 'hypothesis'),
    ('desatualizado', 'outdated'),
])
def test_status_aliases_mapped_to_canonical(alias, canonical):
    assert usecases.canonical_status(alias, 'uc', report=False) == canonical


@pytest.mark.parametrize('canonical', list(usecases.STATUSES))
def test_canonical_status_values_pass_through(canonical):
    assert usecases.canonical_status(canonical, 'uc', report=False) == canonical


def test_canonical_status_missing_defaults_to_inferred():
    assert usecases.canonical_status(None, 'uc', report=False) == 'inferred'
    assert usecases.canonical_status('', 'uc', report=False) == 'inferred'


def test_canonical_status_unknown_value_warns_and_defaults(capsys):
    result = usecases.canonical_status('not-a-status', 'My UC', report=True)
    assert result == 'inferred'
    captured = capsys.readouterr()
    assert 'unknown status "not-a-status"' in captured.err
    assert 'My UC' in captured.err


# ---------------------------------------------------------------------------
# django-drf entry-point parser — data-contract section 6.4
# ---------------------------------------------------------------------------

def test_django_drf_router_register(tmp_path):
    urls = tmp_path / 'urls.py'
    urls.write_text("router.register('books', BookViewSet)\n", encoding='utf-8')
    class_file = {'BookViewSet': 'src/api/views.py'}

    entries = django_drf.parse([str(urls)], class_file, {})
    assert entries == [{'label': '/books', 'kind': 'http', 'path': 'src/api/views.py',
                        'symbol': 'BookViewSet'}]


def test_django_drf_path_as_view(tmp_path):
    urls = tmp_path / 'urls.py'
    urls.write_text("path('health/', HealthView.as_view())\n", encoding='utf-8')
    class_file = {'HealthView': 'src/api/health.py'}

    entries = django_drf.parse([str(urls)], class_file, {})
    assert entries == [{'label': '/health/', 'kind': 'http', 'path': 'src/api/health.py',
                        'symbol': 'HealthView'}]


def test_django_drf_route_prefix_prepended(tmp_path):
    urls = tmp_path / 'urls.py'
    urls.write_text("router.register('books', BookViewSet)\n", encoding='utf-8')
    class_file = {'BookViewSet': 'src/api/views.py'}

    entries = django_drf.parse([str(urls)], class_file, {'route_prefix': '/v1'})
    assert entries[0]['label'] == '/v1/books'


def test_django_drf_ignore_views_skips_silently(tmp_path):
    urls = tmp_path / 'urls.py'
    urls.write_text(
        "router.register('schema', SpectacularSchemaView)\n"
        "router.register('books', BookViewSet)\n",
        encoding='utf-8')
    class_file = {'SpectacularSchemaView': 'src/api/schema.py', 'BookViewSet': 'src/api/views.py'}

    entries = django_drf.parse([str(urls)], class_file, {'ignore_views': ['Spectacular']})
    assert [e['symbol'] for e in entries] == ['BookViewSet']


def test_django_drf_view_not_in_extraction_is_dropped(tmp_path, capsys):
    urls = tmp_path / 'urls.py'
    urls.write_text("router.register('books', BookViewSet)\n", encoding='utf-8')

    entries = django_drf.parse([str(urls)], {}, {})
    assert entries == []
    captured = capsys.readouterr()
    assert 'dropped [view class not found in the extraction]' in captured.err


def test_django_drf_unknown_option_warns(tmp_path, capsys):
    urls = tmp_path / 'urls.py'
    urls.write_text("router.register('books', BookViewSet)\n", encoding='utf-8')
    django_drf.parse([str(urls)], {'BookViewSet': 'x.py'}, {'not_an_option': 1})
    captured = capsys.readouterr()
    assert 'unknown option "not_an_option"' in captured.err


# ---------------------------------------------------------------------------
# Parser kind validation (prep_extra.run_parsers) — data-contract section 6.3
# ---------------------------------------------------------------------------

class _FakeParserModule:
    """Stand-in for a third-party parser module, returning one fixed entry point."""

    def __init__(self, kind):
        self.kind = kind

    def parse(self, files, class_file, options):
        return [{'label': 'made up', 'kind': self.kind, 'path': 'src/x.py', 'symbol': 'X'}]


def _run_fake_parser(monkeypatch, kind):
    monkeypatch.setitem(entry_points_pkg.PARSERS, 'fake', _FakeParserModule(kind))
    config = {'entry_points': {'parsers': [{'name': 'fake', 'files': []}]}}
    return prep_extra.run_parsers(config, None, {'X': 'src/x.py'}, {'src/x.py': 7})


def test_run_parsers_unknown_kind_warns_and_falls_back_to_other(monkeypatch, capsys):
    entries = _run_fake_parser(monkeypatch, 'webhook')
    captured = capsys.readouterr()
    assert 'parser fake: unknown kind "webhook", using "other"' in captured.err
    assert entries == [{'label': 'made up', 'kind': 'other', 'i': 7, 'symbol': 'X'}]


def test_run_parsers_known_kind_passes_through(monkeypatch, capsys):
    entries = _run_fake_parser(monkeypatch, 'cron')
    assert 'unknown kind' not in capsys.readouterr().err
    assert entries[0]['kind'] == 'cron'


# ---------------------------------------------------------------------------
# Entry-point merge — data-contract section 6.2
# ---------------------------------------------------------------------------

def test_merge_entry_points_declaration_wins_the_label_over_a_parser():
    parsed = [{'label': '/api/books', 'kind': 'http', 'i': 5, 'symbol': 'X'}]
    declared = [{'label': 'POST /api/books/{id}/borrow', 'kind': 'http', 'i': 5,
                 'symbol': 'X', 'uc': 'UC'}]
    merged = merge_entry_points(parsed, declared, [])
    assert len(merged) == 1
    assert merged[0] == {'label': 'POST /api/books/{id}/borrow', 'kind': 'http', 'i': 5,
                         'symbol': 'X', 'route': '/api/books', 'ucs': ['UC']}


def test_merge_entry_points_same_label_different_key_both_survive():
    parsed = [{'label': 'same', 'kind': 'http', 'i': 1, 'symbol': None}]
    declared = [{'label': 'same', 'kind': 'http', 'i': 2, 'symbol': None}]
    merged = merge_entry_points(parsed, declared, [])
    assert len(merged) == 2


def test_merge_entry_points_source_precedence_declared_then_parsers_then_fallback():
    parsed = [{'label': 'p', 'kind': 'http', 'i': 1, 'symbol': None}]
    declared = [{'label': 'd', 'kind': 'http', 'i': 1, 'symbol': None, 'uc': 'UC d'}]
    fallback = [{'label': 'f', 'kind': 'other', 'i': 1, 'symbol': None, 'uc': 'UC f'}]
    merged = merge_entry_points(parsed, declared, fallback)
    assert len(merged) == 1
    assert merged[0]['label'] == 'd'
    assert merged[0]['route'] == 'p'
    assert merged[0]['ucs'] == ['UC d', 'UC f']


def test_merge_entry_points_parser_kind_survives_an_unprefixed_declaration():
    parsed = [{'label': '/api/books', 'kind': 'http', 'i': 1, 'symbol': 'X'}]
    declared = [{'label': 'the borrow route', 'kind': 'other', 'i': 1, 'symbol': 'X',
                 'uc': 'UC'}]
    merged = merge_entry_points(parsed, declared, [])
    assert merged[0]['kind'] == 'http'          # 'other' never demotes a known kind
    assert merged[0]['label'] == 'the borrow route'


def test_merge_entry_points_an_explicit_declared_kind_wins():
    parsed = [{'label': '/api/books', 'kind': 'http', 'i': 1, 'symbol': 'X'}]
    declared = [{'label': 'borrow', 'kind': 'command', 'i': 1, 'symbol': 'X', 'uc': 'UC'}]
    assert merge_entry_points(parsed, declared, [])[0]['kind'] == 'command'


def test_merge_entry_points_method_inherits_the_route_of_its_class():
    parsed = [{'label': '/api/books', 'kind': 'http', 'i': 1, 'symbol': 'BookViewSet'}]
    declared = [{'label': 'GET /api/books', 'kind': 'http', 'i': 1,
                 'symbol': 'BookViewSet.list', 'uc': 'UC'}]
    merged = merge_entry_points(parsed, declared, [])
    assert len(merged) == 2                      # different symbols: two entry points
    assert {e['route'] for e in merged} == {'/api/books'}


def test_merge_entry_points_route_is_none_without_a_parser():
    merged = merge_entry_points([], [{'label': 'd', 'kind': 'http', 'i': 0,
                                      'symbol': 'X'}], [])
    assert merged[0]['route'] is None and merged[0]['ucs'] == []


def test_merge_entry_points_lists_every_use_case_of_one_entry_point():
    declared = [{'label': 'first', 'kind': 'http', 'i': 2, 'symbol': 'X', 'uc': 'UC one'},
                {'label': 'second', 'kind': 'http', 'i': 2, 'symbol': 'X', 'uc': 'UC two'}]
    merged = merge_entry_points([], declared, [])
    assert len(merged) == 1
    assert merged[0]['label'] == 'first'         # first declaration wins the label
    assert merged[0]['ucs'] == ['UC one', 'UC two']


def test_merge_entry_points_does_not_repeat_a_use_case_name():
    declared = [{'label': 'a', 'kind': 'http', 'i': 2, 'symbol': 'X', 'uc': 'UC'},
                {'label': 'b', 'kind': 'http', 'i': 2, 'symbol': 'X', 'uc': 'UC'}]
    assert merge_entry_points([], declared, [])[0]['ucs'] == ['UC']


def test_merge_entry_points_lists_the_use_cases_in_registry_order_not_source_order():
    # The merge walks the whole declared list before the whole fallback list, so a
    # use-case that comes first in the registry but arrives through the fallback must
    # still be named first: the panel truncates ucs to the first three names.
    declared = [{'label': 'declared by B', 'kind': 'http', 'i': 1, 'symbol': 'X',
                 'uc': 'B', 'ucpos': 1}]
    fallback = [{'label': 'A', 'kind': 'other', 'i': 1, 'symbol': 'X',
                 'uc': 'A', 'ucpos': 0}]
    merged = merge_entry_points([], declared, fallback)
    assert len(merged) == 1
    assert merged[0]['ucs'] == ['A', 'B']
    assert merged[0]['label'] == 'declared by B'   # the merge order itself is unchanged


def test_merge_entry_points_sorts_the_entries_of_one_route_together():
    # 'GET /api/books' sorts before '/api/health' by label, so a label-first sort would
    # put HealthView between the two entries of /api/books. Sorting on the route keeps
    # the viewset and the method a use-case declared under it adjacent.
    parsed = [{'label': '/api/books', 'kind': 'http', 'i': 1, 'symbol': 'BookViewSet'},
              {'label': '/api/health', 'kind': 'http', 'i': 2, 'symbol': 'HealthView'}]
    declared = [{'label': 'GET /api/books', 'kind': 'http', 'i': 1,
                 'symbol': 'BookViewSet.list', 'uc': 'UC'}]
    merged = merge_entry_points(parsed, declared, [])
    assert [e['symbol'] for e in merged] == ['BookViewSet', 'BookViewSet.list',
                                             'HealthView']
    assert [e['route'] for e in merged] == ['/api/books', '/api/books', '/api/health']


def test_merge_entry_points_emits_only_the_contract_keys():
    declared = [{'label': 'd', 'kind': 'http', 'i': 1, 'symbol': None, 'uc': 'UC'}]
    merged = merge_entry_points([], declared, [])
    assert set(merged[0]) == {'label', 'kind', 'i', 'symbol', 'route', 'ucs'}


def test_merge_entry_points_sort_order_kind_then_label_then_symbol_then_index():
    entries = [
        {'label': 'z', 'kind': 'other', 'i': 0, 'symbol': None},
        {'label': 'a', 'kind': 'http', 'i': 3, 'symbol': None},
        {'label': 'a', 'kind': 'http', 'i': 1, 'symbol': None},
        {'label': 'b', 'kind': 'command', 'i': 2, 'symbol': None},
    ]
    merged = merge_entry_points(entries, [], [])
    kinds = [e['kind'] for e in merged]
    assert kinds == ['http', 'http', 'command', 'other']
    # both 'a'/'http' entries keep their relative index order once label/symbol tie
    http_entries = [e for e in merged if e['kind'] == 'http']
    assert [e['i'] for e in http_entries] == [1, 3]


def test_collect_from_usecases_falls_back_to_first_hop_when_no_entry_point_declared():
    find_file = usecases.make_file_finder({'src/a.py': 0, 'src/b.py': 1})
    raw_ucs = [{
        'name': 'UC without a declared entry point',
        'hops': ['src/a.py:Handler.run — first hop', 'src/b.py:Other.step — second hop'],
        'entry_points': [],
    }]
    totals = {'resolved': 0, 'dropped': 0, 'use_cases': 0}
    declared, fallback = prep_extra.collect_from_usecases(raw_ucs, find_file, totals)
    assert declared == []
    assert fallback == [{'label': 'UC without a declared entry point', 'kind': 'other',
                         'i': 0, 'symbol': 'Handler.run',
                         'uc': 'UC without a declared entry point', 'ucpos': 0}]


def test_collect_from_usecases_prefers_declared_over_fallback():
    find_file = usecases.make_file_finder({'src/a.py': 0})
    raw_ucs = [{
        'name': 'UC with a declared entry point',
        'hops': ['src/a.py:Handler.run — the hop'],
        'entry_points': ['command: src/a.py:Handler.run'],
    }]
    totals = {'resolved': 0, 'dropped': 0, 'use_cases': 0}
    declared, fallback = prep_extra.collect_from_usecases(raw_ucs, find_file, totals)
    assert len(declared) == 1
    assert declared[0]['kind'] == 'command'
    assert declared[0]['uc'] == 'UC with a declared entry point'
    assert declared[0]['ucpos'] == 0             # registry position, for the ucs order
    assert fallback == []


def test_collect_from_usecases_no_fallback_when_no_hop_resolves_either():
    find_file = usecases.make_file_finder({'src/a.py': 0})
    raw_ucs = [{'name': 'UC with nothing resolvable', 'hops': [], 'entry_points': []}]
    totals = {'resolved': 0, 'dropped': 0, 'use_cases': 0}
    declared, fallback = prep_extra.collect_from_usecases(raw_ucs, find_file, totals)
    assert declared == []
    assert fallback == []


# ---------------------------------------------------------------------------
# Call resolution — data-contract section 8 (internal / cross-file / self.x / SKIP)
# ---------------------------------------------------------------------------

def _results_and_symbols():
    results = {
        'a.py': {
            'classes': [{'name': 'A', 'methods': ['run']}],
            'functions': [{'name': 'helper'}],
            'exports': [{'name': 'A'}, {'name': 'helper'}],
            'callGraph': [
                {'caller': 'A.run', 'callee': 'self.helper()', 'lineNumber': 10},
                {'caller': 'A.run', 'callee': 'len(items)', 'lineNumber': 11},
            ],
        },
        'b.py': {
            'classes': [],
            'functions': [{'name': 'main'}],
            'exports': [{'name': 'main'}],
            'callGraph': [
                {'caller': 'main', 'callee': 'a_module.A.create()', 'lineNumber': 20},
            ],
        },
    }
    symbols = prep_extra.build_symbols(results)
    return results, symbols


def test_build_calls_internal_and_self_dot():
    results, symbols = _results_and_symbols()
    path_index = {'a.py': 0, 'b.py': 1}
    imported = {'a.py': [], 'b.py': []}
    calls, internal, cross = prep_extra.build_calls(results, symbols, imported, path_index)
    assert internal == 1
    assert calls[0]['n'] == [['A.run', 'helper', 10]]


def test_build_calls_skips_builtins():
    results, symbols = _results_and_symbols()
    path_index = {'a.py': 0, 'b.py': 1}
    imported = {'a.py': [], 'b.py': []}
    calls, _, _ = prep_extra.build_calls(results, symbols, imported, path_index)
    callees = [c[1] for c in calls.get(0, {}).get('n', [])]
    assert 'len' not in callees


def test_build_calls_cross_file_tries_up_to_three_identifiers():
    results, symbols = _results_and_symbols()
    path_index = {'a.py': 0, 'b.py': 1}
    imported = {'a.py': [], 'b.py': ['a.py']}
    calls, internal, cross = prep_extra.build_calls(results, symbols, imported, path_index)
    assert cross == 1
    assert calls[1]['x'] == [['main', 0, 'A', 20]]


# ---------------------------------------------------------------------------
# Config validation errors — data-contract section 3.1
# ---------------------------------------------------------------------------

def test_load_config_unknown_parser_name(tmp_path):
    raw = {'repo': 'x', 'entry_points': {'parsers': [{'name': 'no-such-parser'}]}}
    path = tmp_path / 'config.json'
    path.write_text(json.dumps(raw), encoding='utf-8')

    with pytest.raises(SystemExit, match='unknown entry-point parser "no-such-parser"'):
        config_mod.load_config(str(path))


def test_load_config_malformed_rules_not_a_pair(tmp_path):
    raw = {'repo': 'x', 'rules': [['only-a-prefix']]}
    path = tmp_path / 'config.json'
    path.write_text(json.dumps(raw), encoding='utf-8')

    with pytest.raises(SystemExit, match=r'rules\[0\] must be a \[prefix, category\] pair'):
        config_mod.load_config(str(path))


def test_load_config_malformed_rules_empty_prefix(tmp_path):
    raw = {'repo': 'x', 'rules': [['', 'cat']]}
    path = tmp_path / 'config.json'
    path.write_text(json.dumps(raw), encoding='utf-8')

    with pytest.raises(SystemExit, match='the prefix cannot be empty'):
        config_mod.load_config(str(path))


def test_load_config_requires_repo(tmp_path):
    path = tmp_path / 'config.json'
    path.write_text(json.dumps({}), encoding='utf-8')
    with pytest.raises(SystemExit, match='"repo" is required'):
        config_mod.load_config(str(path))


def test_load_config_date_alias(tmp_path):
    raw = {'repo': 'x', 'data': '2026-01-01'}
    path = tmp_path / 'config.json'
    path.write_text(json.dumps(raw), encoding='utf-8')
    config = config_mod.load_config(str(path))
    assert config['date'] == '2026-01-01'


def test_load_config_deprecated_urls_files_warns_and_maps(tmp_path, capsys):
    raw = {'repo': 'x', 'urls_files': ['src/urls.py']}
    path = tmp_path / 'config.json'
    path.write_text(json.dumps(raw), encoding='utf-8')
    config = config_mod.load_config(str(path))
    assert config['entry_points']['parsers'] == [
        {'name': 'django-drf', 'files': ['src/urls.py'], 'route_prefix': '', 'ignore_views': []}]
    assert 'deprecated' in capsys.readouterr().err


# ---------------------------------------------------------------------------
# inject.py — placeholder abort (data-contract section 10.5)
# ---------------------------------------------------------------------------

def test_inject_aborts_when_placeholder_missing(tmp_path, monkeypatch):
    template = tmp_path / 'template.html'
    template.write_text('<html><body>no placeholder here</body></html>', encoding='utf-8')
    data_path = tmp_path / 'data.json'
    data_path.write_text(json.dumps({'meta': {'nfiles': 0}}), encoding='utf-8')
    out_path = tmp_path / 'out.html'

    argv = ['inject.py', '--template', str(template), '--data', str(data_path),
            '--out', str(out_path)]
    monkeypatch.setattr(sys, 'argv', argv)
    with pytest.raises(SystemExit, match='does not contain the placeholder'):
        inject.main()
    assert not out_path.exists()


def test_inject_aborts_on_nfiles_mismatch(tmp_path, monkeypatch):
    template = tmp_path / 'template.html'
    template.write_text(f'<script>{inject.PLACEHOLDER}</script>', encoding='utf-8')
    data_path = tmp_path / 'data.json'
    data_path.write_text(json.dumps({'meta': {'nfiles': 3}}), encoding='utf-8')
    extra_path = tmp_path / 'extra.json'
    extra_path.write_text(json.dumps({'nfiles': 5, 'entry_points': [], 'calls': {}}),
                          encoding='utf-8')
    out_path = tmp_path / 'out.html'

    argv = ['inject.py', '--template', str(template), '--data', str(data_path),
            '--extra', str(extra_path), '--out', str(out_path)]
    monkeypatch.setattr(sys, 'argv', argv)
    with pytest.raises(SystemExit, match='does not match'):
        inject.main()
    assert not out_path.exists()


# ---------------------------------------------------------------------------
# Hop role prefixes -> derived hops[].k — data-contract sections 5.1 and 7.4
# ---------------------------------------------------------------------------

FIXTURE_UCS = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           'fixtures', 'branching-usecases.json')


def _branching_finder():
    """A file finder over the seven paths cited by the branching fixture.

    Built from the fixture itself rather than from the golden extraction, which
    contains no `ingest/` files at all.
    """
    raw = json.load(open(FIXTURE_UCS, encoding='utf-8'))
    paths, seen = [], set()
    for hop in raw[0]['hops']:
        path = hop.split(':', 1)[0].strip()
        if path not in seen:
            seen.add(path)
            paths.append(path)
    path_index = {p: n for n, p in enumerate(paths)}
    return raw, usecases.make_file_finder(path_index)


def test_branching_fixture_cites_seven_distinct_files():
    raw, _ = _branching_finder()
    assert len(raw[0]['hops']) == 10
    assert len({h.split(':', 1)[0] for h in raw[0]['hops']}) == 7


def test_parse_hop_derives_k_for_every_fixture_hop():
    raw, find_file = _branching_finder()
    kinds = []
    for line in raw[0]['hops']:
        hop, reason = usecases.parse_hop(line, find_file)
        assert hop is not None, reason
        kinds.append(hop.get('k'))
    assert kinds == [None, 'branch', 'branch', 'branch', None,
                     'branch', 'branch', None, 'branch', 'branch']


def test_parse_hop_omits_k_when_the_role_has_no_prefix():
    find_file = usecases.make_file_finder({'a/b.py': 0})
    hop, _ = usecases.parse_hop('a/b.py:f — plain role, no prefix', find_file)
    assert 'k' not in hop


@pytest.mark.parametrize('prefix,expected', [
    ('branch:', 'branch'), ('Branch:', 'branch'), ('BRANCH:', 'branch'),
    ('ramo:', 'branch'), ('Ramo:', 'branch'), ('RAMO:', 'branch'),
    ('seam:', 'seam'), ('Seam:', 'seam'), ('SEAM:', 'seam'),
    ('costura:', 'seam'), ('Costura:', 'seam'), ('COSTURA:', 'seam'),
])
def test_parse_hop_recognizes_both_languages_case_insensitively(prefix, expected):
    find_file = usecases.make_file_finder({'a/b.py': 0})
    hop, _ = usecases.parse_hop(f'a/b.py:f — {prefix} does something', find_file)
    assert hop['k'] == expected


def test_parse_hop_keeps_the_prefix_inside_r():
    find_file = usecases.make_file_finder({'a/b.py': 0})
    hop, _ = usecases.parse_hop('a/b.py:f — branch: layout A, best-effort', find_file)
    assert hop['r'] == 'branch: layout A, best-effort'
    assert hop['k'] == 'branch'


def test_parse_hop_ignores_a_prefix_word_that_is_not_at_the_start():
    find_file = usecases.make_file_finder({'a/b.py': 0})
    hop, _ = usecases.parse_hop('a/b.py:f — picks the branch: left or right', find_file)
    assert 'k' not in hop


def test_build_ucs_carries_k_through_to_the_viewer_shape():
    raw, find_file = _branching_finder()
    files = [{'p': 'ingest/x.py', 'c': [], 'f': []}] * 7
    ucs = prep_data.build_ucs(usecases.load_usecases(FIXTURE_UCS), files, find_file,
                              {'hops': 0, 'dropped': 0, 'use_cases': 0})
    assert [h.get('k') for h in ucs[0]['hops']] == [
        None, 'branch', 'branch', 'branch', None, 'branch', 'branch', None,
        'branch', 'branch']
