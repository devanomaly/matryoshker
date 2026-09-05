"""prep_data.py — builds the viewer's data.json from the structural extraction.

Usage:
  python pipeline/prep_data.py --es es-output.json --imports im-output.json \
      --config config/<repo>.json [--ucs data/<repo>/usecases.json] --out data.json [--strict]

Inputs:
  --es       output of the extractor's extract-structure step (deterministic)
  --imports  output of the extractor's import-map step
  --config   repo config: {repo, commit, date, lang, categories, rules, ...}
  --ucs      versioned use-case registry (optional)
Output: the JSON {meta, files, imports, ucs} the viewer reads.

Use-case hops that do not resolve (unreadable citation, or a file outside the
extraction) are dropped, and every drop is reported on stderr with its reason plus a
per-use-case summary. A hop whose symbol is not declared in the file it points at is
kept but reported too. The exit code stays 0 unless --strict is given.

Reference: docs/data-contract.md, sections 7 and 10.3.
"""
import argparse
import json
import re

try:
    from _common import kb, norm_path, read_json, warn, warn_python_version, write_text
    from config import load_config
    from usecases import (load_usecases, make_file_finder, report_citations, report_total,
                          resolve_use_case)
except ImportError:  # run as a module: python -m pipeline.prep_data
    from pipeline._common import (kb, norm_path, read_json, warn, warn_python_version,
                                  write_text)
    from pipeline.config import load_config
    from pipeline.usecases import (load_usecases, make_file_finder, report_citations,
                                   report_total, resolve_use_case)

# Contract version written into meta; see docs/data-contract.md.
CONTRACT = 2

# A hop symbol that is a line reference (":120", ":120-145") instead of a name.
LINE_REF = re.compile(r'^\d+(?:-\d+)?$')

# Exit code used when --strict is given and at least one citation was dropped.
STRICT_EXIT = 3


def parse_args():
    ap = argparse.ArgumentParser(
        description="Builds the viewer's data.json from the structural extraction.")
    ap.add_argument('--es', required=True, metavar='FILE',
                    help='output of the extractor (extract-structure)')
    ap.add_argument('--imports', required=True, metavar='FILE',
                    help='output of the extractor (import map)')
    ap.add_argument('--config', required=True, metavar='FILE',
                    help='repo config: {repo, commit, date, lang, categories, rules, ...}')
    ap.add_argument('--ucs', default=None, metavar='FILE',
                    help='versioned use-case registry (optional)')
    ap.add_argument('--out', required=True, metavar='FILE',
                    help='path of the data.json to write')
    ap.add_argument('--strict', action='store_true',
                    help=f'exit {STRICT_EXIT} when at least one hop was dropped')
    return ap.parse_args()


def build_categorizer(config):
    """Return the function that maps a file path to its configured category."""
    rules = [(prefix, category) for prefix, category in config['rules']]
    fallback = config['fallback_category']
    test_marker = config['test_path_marker']
    test_category = config['test_category']

    def categorize(path):
        for prefix, category in rules:
            if path.startswith(prefix):
                return category
        if test_marker and test_marker in path:
            return test_category
        return fallback

    return categorize


def build_files(es, categorize):
    """Flatten the structural extraction into file records + a path -> index map."""
    if 'results' not in es:
        raise SystemExit("--es: JSON has no 'results' key (expected the extract-structure output)")

    files, path_index = [], {}
    for result in es['results']:
        path = norm_path(result['path'])
        classes = [[c['name'], c.get('startLine', 0), c.get('endLine', 0), c.get('methods', [])]
                   for c in (result.get('classes') or [])]
        functions = []
        for fn in (result.get('functions') or []):
            if isinstance(fn, dict):
                line_range = fn.get('lineRange') or [fn.get('startLine', 0), fn.get('endLine', 0)]
                functions.append([fn['name'], line_range[0], line_range[1]])
            else:
                functions.append([fn, 0, 0])
        path_index[path] = len(files)
        files.append({'p': path, 'n': result.get('totalLines', 0), 'g': categorize(path),
                      'c': classes, 'f': functions})
    return files, path_index


def build_imports(im, path_index):
    """Turn the import map into deduplicated [source, target] index pairs."""
    imports, seen = [], set()
    for src, dsts in im.get('importMap', {}).items():
        s = path_index.get(norm_path(src))
        if s is None:
            continue
        for dst in dsts:
            t = path_index.get(norm_path(dst))
            if t is None or t == s or (s, t) in seen:
                continue
            seen.add((s, t))
            imports.append([s, t])
    return imports


def unverified_symbol(symbol, record):
    """Explain why a hop symbol is not declared in the file, or None when it is.

    'A.b' asks for a class A with a method b; 'X' accepts a class, a function or a
    method of any class. Line references and empty symbols are not checked.
    """
    if not symbol or LINE_REF.match(symbol):
        return None
    classes = {c[0]: (c[3] or []) for c in record['c']}
    functions = {f[0] for f in record['f']}
    if '.' in symbol:
        class_name, _, method = symbol.rpartition('.')
        if method in classes.get(class_name, ()):
            return None
    else:
        if symbol in classes or symbol in functions:
            return None
        if any(symbol in methods for methods in classes.values()):
            return None
    return f'{symbol} not declared in {record["p"]}'


def build_ucs(raw_ucs, files, find_file, totals):
    """Resolve every use-case into the viewer's shape, reporting what did not check out."""
    ucs = []
    for uc in raw_ucs:
        resolved = resolve_use_case(uc, find_file)
        hops, dropped = resolved['hops'], resolved['hops_dropped']

        notes = []
        for hop, raw in zip(hops, resolved['hop_raw']):
            note = unverified_symbol(hop['s'], files[hop['i']])
            if note:
                notes.append((raw, note))

        totals['hops'] += len(hops)
        totals['dropped'] += len(dropped)
        if dropped:
            totals['use_cases'] += 1
        report_citations(resolved['name'], 'hops', len(hops), len(hops) + len(dropped),
                         dropped, notes)

        ucs.append({'name': uc['name'], 'actor': uc['actor'], 'goal': uc['goal'],
                    'seam': uc['seam_crossing'], 'rules': uc['rules'],
                    'status': uc['status'], 'hops': hops})
    return ucs


def main():
    warn_python_version()
    args = parse_args()

    es = read_json(args.es, '--es')
    im = read_json(args.imports, '--imports')
    config = load_config(args.config, '--config')
    raw_ucs = load_usecases(args.ucs, '--ucs') if args.ucs else []

    files, path_index = build_files(es, build_categorizer(config))
    imports = build_imports(im, path_index)

    find_file = make_file_finder(path_index, config['hop_path_prefixes'])
    totals = {'hops': 0, 'dropped': 0, 'use_cases': 0}
    ucs = build_ucs(raw_ucs, files, find_file, totals)
    report_total('hops', totals['hops'], totals['dropped'], totals['use_cases'])

    if args.strict and totals['dropped']:
        warn(f"strict: {totals['dropped']} citations dropped")
        raise SystemExit(STRICT_EXIT)

    data = {'meta': {'contract': CONTRACT, 'repo': config['repo'], 'commit': config['commit'],
                     'date': config['date'], 'lang': config['lang'],
                     'categories': config['categories'], 'nfiles': len(files),
                     'nimports': len(imports), 'nucs': len(ucs)},
            'files': files, 'imports': imports, 'ucs': ucs}
    nbytes = write_text(args.out, json.dumps(data, ensure_ascii=False, separators=(',', ':')))
    print(f'files={len(files)} imports={len(imports)} ucs={len(ucs)} '
          f"hops={totals['hops']} -> {args.out} ({kb(nbytes)}KB)")


if __name__ == '__main__':
    main()
