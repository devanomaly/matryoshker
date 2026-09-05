"""prep_extra.py — builds extra.json: the entry points and the resolved call edges.

Usage:
  python pipeline/prep_extra.py --es es-output.json --imports im-output.json --out extra.json \
      [--config config/<repo>.json] [--ucs data/<repo>/usecases.json] [--repo <target repo>] [--strict]

Entry points come from three sources, merged in this order: the route parsers listed
in the config, the entry points declared by the use-cases, and — for a use-case with
no resolvable declared entry point — its first resolved hop. Duplicates (same file,
same symbol) collapse into the first occurrence.

Call edges: the callee is resolved against the symbols of the same file (internal) or
against the exports of the imported files (cross-file). Builtins are skipped.

Reference: docs/data-contract.md, sections 6, 8 and 10.4.
"""
import argparse
import json
import os
import re

try:
    from _common import kb, norm_path, read_json, warn, warn_python_version, write_text
    from config import load_config
    from entry_points import (get_parser, merge_entry_points, parser_drops,
                              reset_parser_drops)
    from usecases import (KINDS, load_usecases, make_file_finder, report_citations,
                          report_total, resolve_use_case)
except ImportError:  # run as a module: python -m pipeline.prep_extra
    from pipeline._common import (kb, norm_path, read_json, warn, warn_python_version,
                                  write_text)
    from pipeline.config import load_config
    from pipeline.entry_points import (get_parser, merge_entry_points, parser_drops,
                                       reset_parser_drops)
    from pipeline.usecases import (KINDS, load_usecases, make_file_finder,
                                   report_citations, report_total, resolve_use_case)

# Builtins and common exceptions: calls to these names never become edges.
SKIP = {'len', 'range', 'list', 'dict', 'set', 'str', 'int', 'float', 'print', 'enumerate', 'zip',
        'isinstance', 'getattr', 'setattr', 'hasattr', 'super', 'sorted', 'min', 'max', 'sum',
        'any', 'all', 'type', 'id', 'abs', 'round', 'open', 'format', 'repr', 'iter', 'next',
        'map', 'filter', 'tuple', 'bool', 'vars', 'Exception', 'ValueError', 'TypeError', 'KeyError'}

IDENTIFIER = re.compile(r'[A-Za-z_]\w*')

# How many leading identifiers of a call expression are tried against the exports of
# the imported files (`a.b.c()` -> a, b, c).
MAX_CALLEE_IDS = 3

# Exit code used when --strict is given and at least one citation or route was dropped.
STRICT_EXIT = 3


def parse_args():
    ap = argparse.ArgumentParser(
        description='Builds extra.json: the entry points and the resolved call edges.')
    ap.add_argument('--es', required=True, metavar='FILE',
                    help='output of the extractor (extract-structure)')
    ap.add_argument('--imports', required=True, metavar='FILE',
                    help='output of the extractor (import map)')
    ap.add_argument('--config', default=None, metavar='FILE',
                    help='repo config; provides entry_points.parsers and hop_path_prefixes')
    ap.add_argument('--ucs', default=None, metavar='FILE',
                    help='versioned use-case registry (declared entry points and hops)')
    ap.add_argument('--repo', default=None, metavar='DIR',
                    help='target repository root, joined with the files a parser declares')
    ap.add_argument('--out', required=True, metavar='FILE',
                    help='path of the extra.json to write')
    ap.add_argument('--strict', action='store_true',
                    help=f'exit {STRICT_EXIT} when an entry-point citation or route was dropped')
    return ap.parse_args()


def build_symbols(results):
    """Index, per file, the declared classes / methods / functions / exports."""
    symbols = {}
    for path, result in results.items():
        classes = {c['name']: c for c in (result.get('classes') or [])}
        methods = {}
        for c in (result.get('classes') or []):
            for m in (c.get('methods') or []):
                methods.setdefault(m, c['name'])
        funcs = {(f['name'] if isinstance(f, dict) else f) for f in (result.get('functions') or [])}
        exports = {e['name'] for e in (result.get('exports') or [])} | set(classes) | funcs
        symbols[path] = {'classes': classes, 'methods': methods, 'funcs': funcs, 'exports': exports}
    return symbols


def run_parsers(config, repo_root, class_file, path_index):
    """Run the configured route parsers and return their entry points, with file indices."""
    parsers = config['entry_points']['parsers'] if config else []
    if not parsers:
        return []

    declares_files = any(parser['files'] for parser in parsers)
    if declares_files and not repo_root:
        raise SystemExit('--repo: required because entry_points.parsers declares files')

    reset_parser_drops()
    entry_points = []
    for n, entry in enumerate(parsers):
        module = get_parser(entry['name'], '--config')
        files = []
        for relative in entry['files']:
            path = os.path.join(repo_root, *norm_path(relative).split('/'))
            if not os.path.isfile(path):
                raise SystemExit(f'--config: entry_points.parsers[{n}].files: file not found: {path}')
            files.append(path)
        options = {k: v for k, v in entry.items() if k not in ('name', 'files')}
        for parsed in module.parse(files, class_file, options):
            index = path_index.get(parsed['path'])
            if index is None:      # a parser only returns paths taken from class_file
                continue
            kind = parsed.get('kind') or 'other'
            if kind not in KINDS:
                # The viewer only renders the six declared groups, so an unknown kind
                # would make the entry point disappear from the panel.
                warn(f'warning: parser {entry["name"]}: unknown kind "{kind}", using "other"')
                kind = 'other'
            entry_points.append({'label': parsed['label'], 'kind': kind,
                                 'i': index, 'symbol': parsed.get('symbol')})
    return entry_points


def collect_from_usecases(raw_ucs, find_file, totals):
    """Declared entry points and first-hop fallbacks, in registry order."""
    declared, fallback = [], []
    for uc in raw_ucs:
        resolved = resolve_use_case(uc, find_file)
        entries, dropped = resolved['entry_points'], resolved['entry_points_dropped']

        totals['resolved'] += len(entries)
        totals['dropped'] += len(dropped)
        if dropped:
            totals['use_cases'] += 1
        report_citations(resolved['name'], 'entry points', len(entries),
                         len(entries) + len(dropped), dropped)

        declared.extend(entries)
        if not entries and resolved['hops']:
            hop = resolved['hops'][0]
            fallback.append({'label': resolved['name'], 'kind': 'other', 'i': hop['i'],
                             'symbol': hop['s'] or None})
    return declared, fallback


def build_calls(results, symbols, imported, path_index):
    """Resolve the call graph into internal and cross-file edges.

    Returns (calls, total_internal, total_cross).
    """
    calls = {}
    total_internal = total_cross = 0
    for path, result in results.items():
        own = symbols[path]
        internal, cross, seen = [], [], set()
        for edge in (result.get('callGraph') or []):
            caller = edge.get('caller', '?')
            callee = edge.get('callee', '')
            line = edge.get('lineNumber', 0)
            ids = IDENTIFIER.findall(callee)
            if not ids:
                continue
            root = ids[0]
            if root == 'self' and len(ids) > 1:
                root = ids[1]
            if root in SKIP:
                continue
            key = (caller, root)
            if key in seen:
                continue

            if root in own['methods'] or root in own['funcs'] or root in own['classes']:
                seen.add(key)
                internal.append([caller, root, line])
                total_internal += 1
                continue

            target, target_symbol = None, root
            for candidate in ids[:MAX_CALLEE_IDS]:
                for imported_path in imported[path]:
                    if candidate in symbols[imported_path]['exports']:
                        target, target_symbol = imported_path, candidate
                        break
                if target:
                    break
            if target:
                seen.add(key)
                cross.append([caller, path_index[target], target_symbol, line])
                total_cross += 1

        if internal or cross:
            calls[path_index[path]] = {'n': internal, 'x': cross}
    return calls, total_internal, total_cross


def main():
    warn_python_version()
    args = parse_args()

    es = read_json(args.es, '--es')
    im = read_json(args.imports, '--imports')
    if 'results' not in es:
        raise SystemExit("--es: JSON has no 'results' key (expected the extract-structure output)")

    config = load_config(args.config, '--config') if args.config else None
    # Hops are resolved here exactly as in prep_data.py, but silently: prep_data has
    # already reported them, and only the entry-point citations are news here.
    raw_ucs = load_usecases(args.ucs, '--ucs', report_status=False) if args.ucs else []

    results = {norm_path(r['path']): r for r in es['results']}
    path_index = {p: i for i, p in enumerate(results)}

    symbols = build_symbols(results)
    class_file = {}
    for path, s in symbols.items():
        for class_name in s['classes']:
            class_file.setdefault(class_name, path)

    parsed = run_parsers(config, args.repo, class_file, path_index)

    totals = {'resolved': 0, 'dropped': 0, 'use_cases': 0}
    find_file = make_file_finder(path_index, config['hop_path_prefixes'] if config else ())
    declared, fallback = collect_from_usecases(raw_ucs, find_file, totals)
    report_total('entry points', totals['resolved'], totals['dropped'], totals['use_cases'])

    entry_points = merge_entry_points(parsed, declared, fallback)
    if entry_points:
        merged_away = len(parsed) + len(declared) + len(fallback) - len(entry_points)
        warn(f'entry points: {len(parsed)} from parsers, {len(declared)} declared, '
             f'{len(fallback)} fallback, {merged_away} duplicates merged')

    dropped = totals['dropped'] + parser_drops()
    if args.strict and dropped:
        warn(f'strict: {dropped} citations dropped')
        raise SystemExit(STRICT_EXIT)

    import_map = im.get('importMap', {})
    imported = {p: [d for d in map(norm_path, import_map.get(p, [])) if d in path_index]
                for p in results}
    calls, total_internal, total_cross = build_calls(results, symbols, imported, path_index)

    extra = {'nfiles': len(results), 'entry_points': entry_points, 'calls': calls}
    nbytes = write_text(args.out, json.dumps(extra, ensure_ascii=False, separators=(',', ':')))
    print(f'entry_points={len(entry_points)} calls: internal={total_internal} '
          f'cross={total_cross} -> {args.out} ({kb(nbytes)}KB)')


if __name__ == '__main__':
    main()
