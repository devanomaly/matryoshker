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
kept but reported too. A use-case may also carry `frames`, the call stack behind its
hops: frames resolve like hops, every hop must be cited by one, and the edge between
a frame and its parent is checked against the import graph. The exit code stays 0
unless --strict is given.

Reference: docs/data-contract.md, sections 7 and 10.3.
"""
import argparse
import json
import re

try:
    from _common import kb, norm_path, read_json, warn, warn_python_version, write_text
    from config import load_config
    from usecases import (ROLE_MAX_LEN, STATUSES, canonical_status, load_usecases,
                          make_file_finder, parse_hop, report_citations, report_total,
                          resolve_use_case)
except ImportError:  # run as a module: python -m pipeline.prep_data
    from pipeline._common import (kb, norm_path, read_json, warn, warn_python_version,
                                  write_text)
    from pipeline.config import load_config
    from pipeline.usecases import (ROLE_MAX_LEN, STATUSES, canonical_status,
                                   load_usecases, make_file_finder, parse_hop,
                                   report_citations, report_total, resolve_use_case)

# Contract version written into meta; see docs/data-contract.md.
CONTRACT = 2

# A hop symbol that is a line reference (":120", ":120-145") instead of a name.
LINE_REF = re.compile(r'^\d+(?:-\d+)?$')

# Exit code used when --strict is given and a citation or a frame was dropped, or a
# hop has no frame.
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
                    help=f'exit {STRICT_EXIT} when a hop or a frame was dropped, or a hop has no frame')
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

# --- stack frames (data-contract 7.4) -------------------------------------------
# A use-case may carry `frames`: the same citations as its hops, but each with a
# `parent` and an `edge`, so a flow can be read as the call stack it really is
# instead of a flat list of levels. The pipeline resolves the citation exactly like
# a hop, derives the depth from the parent chain, caps the frame status at the
# use-case status and checks the edge against the extractor's import graph: a
# `call` edge holds when the parent's file imports the child's file, or when both
# are the same file. Every other edge crosses a process, a transaction or a library
# boundary the import graph cannot see, so it is reported as not provable instead
# of red. Frames are a derived reading of the code, produced outside this tool: it
# resolves, checks and draws them, and ships no generator.

# The seven edge kinds a frame may declare (data-contract 7.4).
FRAME_EDGES = ('entry', 'call', 'queue', 'on_commit', 'worker', 'inbound', 'other')

# Edges that reopen the stack at depth 0: execution resumes in another process.
FRAME_REOPEN_EDGES = ('worker', 'inbound')

# The five proof states of an edge, in the order frame_proof() evaluates them.
FRAME_PROOFS = ('entry', 'same_file', 'import', 'unprovable', 'fail')

# The keys of an emitted frame, in the order they are written (data-contract 7.4).
FRAME_KEYS = ('id', 'parent', 'e', 'i', 's', 'r', 'd', 'reg', 'st', 'en', 'sr',
              'proof', 'why', 'ok')


def status_ceiling(status, uc_status):
    """A frame status never rises above the status of its use-case.

    STATUSES is ordered from the strongest claim to the weakest, so the ceiling is
    whichever of the two sits later in it.
    """
    return uc_status if STATUSES.index(status) < STATUSES.index(uc_status) else status


def frame_depth(frame, by_id):
    """Distance of a frame from the root of its stack.

    `worker` and `inbound` reopen the stack in another process, so they restart at
    0. Every frame that gets here reaches a root (build_frames drops the ones that do
    not), so the walk terminates.
    """
    depth, current = 0, frame
    while current['parent'] and current['e'] not in FRAME_REOPEN_EDGES:
        depth += 1
        if depth > len(by_id):  # unreachable while build_frames drops unrooted frames
            raise ValueError(f'frame {frame["id"]}: parent chain does not end')
        current = by_id[current['parent']]
    return depth


def reaches_root(frame, by_id):
    """Whether following `parent` from `frame` ends at a frame that has none.

    False for a frame whose parent is missing and for every member of a parent cycle,
    a frame that names itself included.
    """
    seen, current = set(), frame
    while current['parent']:
        if current['id'] in seen or current['parent'] not in by_id:
            return False
        seen.add(current['id'])
        current = by_id[current['parent']]
    return True


def frame_proof(frame, parent, files, edge_set):
    """The proof state of the edge into `frame`, and the sentence explaining it.

    Five states: `entry` (no parent), `same_file`, `import` (the graph has the
    edge), `unprovable` (an edge the import graph cannot speak about) and `fail`,
    which is reserved for a plain `call` the graph does not back.
    """
    if parent is None:
        return 'entry', 'entry point of the stack'
    if parent['i'] == frame['i']:
        return 'same_file', 'the parent frame is in the same file'
    if (parent['i'], frame['i']) in edge_set:
        return 'import', 'the parent file imports the child file (extractor import graph)'
    if frame['e'] != 'call':
        return 'unprovable', f"a {frame['e']} edge is not provable by the import graph"
    return 'fail', (f"{files[parent['i']]['p']} does not import "
                    f"{files[frame['i']]['p']} in the import graph")


def hops_without_frame(hops, hop_raw, frames, files):
    """Every hop of a use-case that no frame cites, as (raw hop, explanation).

    Every hop is a frame; not every frame is a hop. A hop matches a frame when both
    cite the same file and the same symbol; a hop with no symbol matches any frame
    of its file.
    """
    pairs = {(f['i'], f['s']) for f in frames}
    anywhere = {f['i'] for f in frames}
    missing = []
    for hop, raw in zip(hops, hop_raw):
        if (hop['i'], hop['s']) in pairs or (not hop['s'] and hop['i'] in anywhere):
            continue
        cited = files[hop['i']]['p'] + (':' + hop['s'] if hop['s'] else '')
        missing.append((raw, f'no frame cites {cited}'))
    return missing


def build_frames(uc, resolved, files, find_file, imports, totals):
    """Resolve the `frames` of one use-case, or None when it declares none.

    Frames whose citation does not resolve are dropped; a frame whose parent is not
    among the kept frames is dropped with it, cascading; a frame whose parent chain
    never reaches a root (a cycle) is dropped; a duplicate id keeps the first frame
    and warns. Every drop and every hop that no frame cites is reported in the stderr
    block of data-contract 5.5 and counted for --strict; an undeclared symbol and a
    rule of 4.4 that was bent (an `other` edge with no note, a line reference, an
    `entry` edge under a parent) are reported and never fatal.
    """
    raw_frames = uc.get('frames') or []
    if not raw_frames:
        return None

    name = uc['name']
    frames, citation_of, dropped, notes, bent = [], {}, [], [], {}
    for raw in raw_frames:
        if not isinstance(raw, dict):
            dropped.append((str(raw), 'frame must be an object'))
            continue
        citation = str(raw.get('hop') or '')
        frame_id = str(raw.get('id') or '')
        if not frame_id:
            dropped.append((citation, 'frame without an "id"'))
            continue
        if frame_id in citation_of:
            warn(f'warning: UC {name}: duplicate frame id "{frame_id}", keeping the first')
            continue
        hop, reason = parse_hop(citation, find_file)
        if hop is None:
            dropped.append((citation, reason))
            continue
        edge, coerced = raw.get('edge') or 'call', False
        if edge not in FRAME_EDGES:
            warn(f'warning: UC {name}: frame {frame_id}: unknown edge "{edge}", using "other"')
            edge, coerced = 'other', True
        parent_id = str(raw.get('parent') or '') or None
        bent[frame_id] = []
        if edge == 'other' and not coerced and not str(raw.get('edge_note') or '').strip():
            bent[frame_id].append('edge "other" without an edge_note')
        if edge == 'entry' and parent_id:
            bent[frame_id].append('edge "entry" on a frame that has a parent')
        if LINE_REF.match(hop['s']):
            bent[frame_id].append(f'line reference "{hop["s"]}" in a frame citation')
        note = unverified_symbol(hop['s'], files[hop['i']])
        if note:
            notes.append((citation, note))
        citation_of[frame_id] = citation
        frames.append({'id': frame_id, 'parent': parent_id,
                       'e': edge, 'i': hop['i'], 's': hop['s'],
                       'r': str(raw.get('role') or '')[:ROLE_MAX_LEN],
                       'reg': str(raw.get('registry') or ''),
                       'st': status_ceiling(canonical_status(raw.get('status') or uc['status'],
                                                             name), uc['status']),
                       'en': str(raw.get('edge_note') or ''),
                       'sr': str(raw.get('status_reason') or '')})

    # A frame is only as reachable as its parent: dropping one drops its subtree.
    by_id = {f['id']: f for f in frames}
    orphans = [f for f in frames if f['parent'] and f['parent'] not in by_id]
    while orphans:
        for frame in orphans:
            dropped.append((citation_of[frame['id']],
                            f'parent "{frame["parent"]}" not in frames'))
            del by_id[frame['id']]
        frames = [f for f in frames if f['id'] in by_id]
        orphans = [f for f in frames if f['parent'] and f['parent'] not in by_id]

    # What is left has every parent present, so a frame that still cannot reach a root
    # sits on a parent cycle (or names itself). Such a stack has no top to draw from.
    unrooted = [f for f in frames if not reaches_root(f, by_id)]
    for frame in unrooted:
        dropped.append((citation_of[frame['id']],
                        f'parent chain of "{frame["id"]}" never reaches a root'))
        del by_id[frame['id']]
    frames = [f for f in frames if f['id'] in by_id]

    # Rules of 4.4 that were bent: said once, and only about a frame that is drawn.
    for frame in frames:
        for complaint in bent[frame['id']]:
            warn(f'warning: UC {name}: frame {frame["id"]}: {complaint}')

    edge_set = {(source, target) for source, target in imports}
    for frame in frames:
        parent = by_id.get(frame['parent']) if frame['parent'] else None
        frame['d'] = frame_depth(frame, by_id)
        frame['proof'], frame['why'] = frame_proof(frame, parent, files, edge_set)
        frame['ok'] = frame['proof'] != 'fail'
    frames = [{key: frame[key] for key in FRAME_KEYS} for frame in frames]

    unframed = hops_without_frame(resolved['hops'], resolved['hop_raw'], frames, files)
    report_citations(name, 'frames', len(frames), len(frames) + len(dropped), dropped, notes,
                     [('hop without frame', why, raw) for raw, why in unframed])

    totals['frames'] = totals.get('frames', 0) + len(frames)
    totals['frames_dropped'] = totals.get('frames_dropped', 0) + len(dropped)
    totals['unframed_hops'] = totals.get('unframed_hops', 0) + len(unframed)
    if dropped:
        totals['frame_use_cases'] = totals.get('frame_use_cases', 0) + 1
    return frames
# --- end stack frames ------------------------------------------------------------


def build_ucs(raw_ucs, files, find_file, totals, imports=()):
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

        record = {'name': uc['name'], 'actor': uc['actor'], 'goal': uc['goal'],
                  'seam': uc['seam_crossing'], 'rules': uc['rules'],
                  'status': uc['status'], 'hops': hops}
        frames = build_frames(uc, resolved, files, find_file, imports, totals)
        if frames:
            record['frames'] = frames
        ucs.append(record)
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
    totals = {'hops': 0, 'dropped': 0, 'use_cases': 0, 'frames': 0, 'frames_dropped': 0,
              'unframed_hops': 0, 'frame_use_cases': 0}
    ucs = build_ucs(raw_ucs, files, find_file, totals, imports)
    report_total('hops', totals['hops'], totals['dropped'], totals['use_cases'])
    report_total('frames', totals['frames'], totals['frames_dropped'],
                 totals['frame_use_cases'])

    if args.strict:
        problems = []
        if totals['dropped']:
            problems.append(f"{totals['dropped']} citations dropped")
        if totals['frames_dropped']:
            problems.append(f"{totals['frames_dropped']} frames dropped")
        if totals['unframed_hops']:
            problems.append(f"{totals['unframed_hops']} hops without a frame")
        if problems:
            warn('strict: ' + ', '.join(problems))
            raise SystemExit(STRICT_EXIT)

    data = {'meta': {'contract': CONTRACT, 'repo': config['repo'], 'commit': config['commit'],
                     'date': config['date'], 'lang': config['lang'],
                     'categories': config['categories'], 'nfiles': len(files),
                     'nimports': len(imports), 'nucs': len(ucs)},
            'files': files, 'imports': imports, 'ucs': ucs}
    nbytes = write_text(args.out, json.dumps(data, ensure_ascii=False, separators=(',', ':')))
    # `frames=` only appears for a registry that declares frames, so the counter line
    # of every other build is the one it has always been.
    frames = f" frames={totals['frames']}" if totals['frames'] else ''
    print(f'files={len(files)} imports={len(imports)} ucs={len(ucs)} '
          f"hops={totals['hops']}{frames} -> {args.out} ({kb(nbytes)}KB)")


if __name__ == '__main__':
    main()
