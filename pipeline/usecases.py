"""usecases.py — loading, aliasing and citation resolution for the use-case registry.

This module has no CLI. It is imported by prep_data.py and prep_extra.py so both
read `data/<repo>/usecases.json` exactly the same way: same key aliases, same status
aliases, same citation grammar and the same file finder. Fatal problems are raised as
SystemExit('<flag>: <message>'), where <flag> is the CLI argument the caller passed
(usually '--ucs'), so the message points at the right argument.

Reference: docs/data-contract.md, sections 4 and 5.
"""
import re

try:
    from _common import norm_path, read_json, warn
except ImportError:  # imported as part of the package: from pipeline.usecases import ...
    from pipeline._common import norm_path, read_json, warn

# A citation: "file.ext" optionally followed by ":Symbol", ":method()", ":123" or
# ":123-145". Used for hops and for entry points alike (data-contract 5.3).
CITATION = re.compile(r'([\w/.\-]+\.\w+)\s*(?::\s*([\w.\-]+(?:\(\))?|\d+(?:-\d+)?))?')

# Entry-point kind prefix, e.g. "http: ". The (?!//) keeps "http://host/x" from
# being read as a kind prefix.
KIND_PREFIX = re.compile(r'^\s*(http|command|event|cli|cron|other)\s*:(?!//)\s*', re.I)

# Trailing "(" of a label such as 'POST /v1/books (views.py:X)'.
LEAD_TRIM = re.compile(r'\s*[(\[{]*\s*$')

# Leading ")" after the citation, then one role separator: em dash (U+2014),
# en dash (U+2013) or a plain hyphen.
TAIL_TRIM = re.compile('^' + r'\s*[)\]}]*\s*(?:[' + chr(0x2014) + chr(0x2013) + r'-]\s*)?')

# The role of a hop (and the free text of an entry point) is truncated here.
ROLE_MAX_LEN = 140

# Entry-point kinds, in the order the viewer groups them.
KINDS = ('http', 'command', 'event', 'cli', 'cron', 'other')

# Canonical status values, in the order the viewer cycles through them.
STATUSES = ('human-verified', 'agent-verified', 'inferred', 'hypothesis', 'outdated')

DEFAULT_STATUS = 'inferred'

# v1 (Portuguese) status values, still accepted in registries written before v2.
STATUS_ALIASES = {
    'verificado-humano': 'human-verified',
    'verificado-agente': 'agent-verified',
    'inferido': 'inferred',
    'hipotese': 'hypothesis',
    'hipótese': 'hypothesis',
    'desatualizado': 'outdated',
}

# v1 (Portuguese) key names, mapped to the canonical v2 keys. When both are present
# the canonical key wins.
KEY_ALIASES = {
    'nome': 'name',
    'ator': 'actor',
    'objetivo': 'goal',
    'regras_envolvidas': 'rules',
}

# Keys the pipeline reads, with the default applied when they are missing.
DEFAULTS = {
    'actor': '',
    'goal': '',
    'entry_points': (),
    'hops': (),
    'rules': (),
    'seam_crossing': False,
}

# Keys whose items must all be strings.
STRING_LISTS = ('entry_points', 'hops', 'rules')


def canonical_status(value, name, report=True):
    """Map a raw status to its canonical value, warning once about unknown ones."""
    if isinstance(value, str):
        text = value.strip()
        if text in STATUSES:
            return text
        if text in STATUS_ALIASES:
            return STATUS_ALIASES[text]
    if value is None or value == '':
        return DEFAULT_STATUS
    if report:
        warn(f'warning: UC {name}: unknown status "{value}", using "{DEFAULT_STATUS}"')
    return DEFAULT_STATUS


def load_usecases(path, label='--ucs', report_status=True):
    """Read the registry and return use-cases with canonical keys and status.

    Extra keys (notes, preconditions, async_legs, ...) are preserved untouched; the
    pipeline ignores them. `report_status` exists so that the second script reading
    the same registry in one build does not print the same warnings twice.
    """
    raw = read_json(path, label)
    if not isinstance(raw, list):
        raise SystemExit(f'{label}: expected a JSON array of use-cases, got {type(raw).__name__}')

    ucs, seen = [], {}
    for n, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise SystemExit(f'{label}: use-case [{n}] must be an object, got {type(entry).__name__}')

        uc = dict(entry)
        for alias, canonical in KEY_ALIASES.items():
            if alias in uc:
                value = uc.pop(alias)
                uc.setdefault(canonical, value)

        name = uc.get('name')
        if not isinstance(name, str) or not name.strip():
            raise SystemExit(f'{label}: use-case [{n}] needs a non-empty "name" (v1 alias: "nome")')
        name = name.strip()
        uc['name'] = name
        if name in seen:
            raise SystemExit(f'{label}: duplicate use-case name "{name}" (entries [{seen[name]}] and [{n}])')
        seen[name] = n

        for key, default in DEFAULTS.items():
            if uc.get(key) is None:
                uc[key] = list(default) if isinstance(default, tuple) else default
        for key in STRING_LISTS:
            value = uc[key]
            if not isinstance(value, list):
                raise SystemExit(f'{label}: use-case "{name}": {key} must be an array of strings')
            for k, item in enumerate(value):
                if not isinstance(item, str):
                    raise SystemExit(f'{label}: use-case "{name}": {key}[{k}] must be a string')
        uc['seam_crossing'] = bool(uc['seam_crossing'])
        uc['status'] = canonical_status(uc.get('status'), name, report_status)
        ucs.append(uc)
    return ucs


def make_file_finder(path_index, hop_path_prefixes=()):
    """Resolve a cited path against the index of extracted files.

    Tries the path as written, then each configured prefix, and finally a basename
    match — accepted only when it is unambiguous. Returns (index, None) on success
    or (None, reason) when the citation has to be dropped (data-contract 5.3).
    """
    prefixes = [p if p.endswith('/') else p + '/' for p in hop_path_prefixes]

    def find_file(path):
        if path in path_index:
            return path_index[path], None
        for prefix in prefixes:
            candidate = prefix + path
            if candidate in path_index:
                return path_index[candidate], None
        basename = path.split('/')[-1]
        hits = [i for p, i in path_index.items() if p == basename or p.endswith('/' + basename)]
        if len(hits) == 1:
            return hits[0], None
        if len(hits) > 1:
            return None, f'ambiguous file name ({len(hits)} files end with /{basename})'
        return None, 'file not found in the extraction'

    return find_file


def _resolve_citation(text, find_file):
    """First citation candidate of `text` whose file resolves.

    Returns (match, index, None) on success, or (None, None, reason) when no
    candidate resolves — the reason is the one of the first candidate.
    """
    candidates = list(CITATION.finditer(text))
    if not candidates:
        return None, None, 'no file citation'
    first_reason = None
    for match in candidates:
        path = norm_path(match.group(1))
        index, reason = find_file(path)
        if index is not None:
            return match, index, None
        if first_reason is None:
            first_reason = reason
    return None, None, first_reason


def parse_hop(raw, find_file):
    """Parse one hop citation. Returns ({'i', 's', 'r'}, None) or (None, reason)."""
    text = norm_path(raw)
    match, index, reason = _resolve_citation(text, find_file)
    if match is None:
        return None, reason
    role = TAIL_TRIM.sub('', text[match.end():], count=1).strip()[:ROLE_MAX_LEN]
    return {'i': index, 's': (match.group(2) or '').rstrip('()'), 'r': role}, None


def parse_entry_point(raw, find_file, default_label=''):
    """Parse one entry-point citation.

    Returns ({'label', 'kind', 'i', 'symbol'}, None) or (None, reason). The label is
    the text before the citation, else the text after it, else `default_label`
    (the use-case name).
    """
    text = norm_path(raw)
    kind = 'other'
    prefix = KIND_PREFIX.match(text)
    if prefix:
        kind = prefix.group(1).lower()
        text = text[prefix.end():]

    match, index, reason = _resolve_citation(text, find_file)
    if match is None:
        return None, reason
    head = LEAD_TRIM.sub('', text[:match.start()]).strip()
    tail = TAIL_TRIM.sub('', text[match.end():], count=1).strip()[:ROLE_MAX_LEN]
    symbol = (match.group(2) or '').rstrip('()')
    return {'label': head or tail or default_label, 'kind': kind, 'i': index,
            'symbol': symbol or None}, None


def resolve_use_case(uc, find_file, report=None):
    """Resolve the hops and the declared entry points of one use-case.

    Returns {'name', 'hops', 'hop_raw', 'hops_dropped', 'entry_points',
    'entry_points_dropped'}: `hop_raw` is parallel to `hops` so the caller can quote
    the original line when a symbol does not check out, and the *_dropped lists hold
    (raw citation, reason) pairs. `report`, when given, is called with the result so
    a caller can print the stderr block of data-contract 5.5.
    """
    name = uc['name']
    hops, hop_raw, hops_dropped = [], [], []
    for raw in uc.get('hops', []):
        hop, reason = parse_hop(raw, find_file)
        if hop is None:
            hops_dropped.append((raw, reason))
            continue
        hops.append(hop)
        hop_raw.append(raw)

    entry_points, entry_points_dropped = [], []
    for raw in uc.get('entry_points', []):
        entry_point, reason = parse_entry_point(raw, find_file, name)
        if entry_point is None:
            entry_points_dropped.append((raw, reason))
            continue
        entry_points.append(entry_point)

    result = {'name': name, 'hops': hops, 'hop_raw': hop_raw, 'hops_dropped': hops_dropped,
              'entry_points': entry_points, 'entry_points_dropped': entry_points_dropped}
    if report is not None:
        report(result)
    return result


def report_citations(name, kind, resolved, total, dropped, notes=()):
    """Print the per-use-case stderr block of data-contract 5.5, when there is one.

    `kind` is the plural noun used in the header ('hops', 'entry points'); `notes`
    are (raw citation, explanation) pairs for citations that resolved but look wrong.
    """
    if not dropped and not notes:
        return
    warn(f'UC {name}: {resolved}/{total} {kind} resolved')
    for raw, reason in dropped:
        warn(f'  dropped [{reason}]: {raw}')
    for raw, note in notes:
        warn(f'  unverified symbol [{note}]: {raw}')


def report_total(kind, resolved, dropped, use_cases):
    """Print the totals line of data-contract 5.5, only when something was dropped."""
    if not dropped:
        return
    warn(f'total: {resolved}/{resolved + dropped} {kind} resolved '
         f'({dropped} dropped in {use_cases} use-cases)')
