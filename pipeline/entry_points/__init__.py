"""entry_points — registry of route parsers and the entry-point merge.

An entry point is a place where execution enters the codebase: an HTTP route, a
command handler, an event consumer, a CLI command, a scheduled job. They come from
three sources (route parsers, use-case declarations, first-hop fallback) which
`merge_entry_points` merges into one entry per (file, symbol) — keeping the declared
label, the parser's route and the use-cases involved — and orders.

A parser module exposes `parse(files, class_file, options) -> list[dict]`, where each
dict is {'label', 'kind', 'path', 'symbol'} and `path` is a value taken from
`class_file`, so the caller can always turn it into a file index. A parser never sees
or invents file indices.

Reference: docs/data-contract.md, section 6.
"""
try:
    from _common import warn
    from usecases import KINDS
except ImportError:  # imported as part of the package
    from pipeline._common import warn
    from pipeline.usecases import KINDS

from . import django_drf

# Registry name -> parser module. A config names parsers by these keys.
PARSERS = {'django-drf': django_drf}

# Routes a parser could not map, since the last reset_parser_drops(). Parsers report
# each drop on stderr themselves; the log exists so that --strict can see them.
_DROPPED = []


def get_parser(name, label='--config'):
    """Return the parser module registered under `name`, or fail listing the names."""
    parser = PARSERS.get(name)
    if parser is None:
        available = ', '.join(sorted(PARSERS))
        raise SystemExit(f'{label}: unknown entry-point parser "{name}"; available: {available}')
    return parser


def reset_parser_drops():
    """Clear the parser drop log (called once before running the parsers)."""
    _DROPPED.clear()


def record_parser_drop(parser, source_file, reason, what):
    """Report one route a parser could not map, and remember it for --strict."""
    _DROPPED.append((parser, source_file, reason, what))
    warn(f'parser {parser} ({source_file}): dropped [{reason}]: {what}')


def parser_drops():
    """How many routes the parsers dropped since the last reset."""
    return len(_DROPPED)


# Where a colliding entry point takes its label and its kind from: a hand-written
# declaration beats a generated route, and a first-hop fallback never beats either.
SOURCE_RANK = {'declared': 0, 'parsers': 1, 'fallback': 2}

# Registry position of a contribution whose entry carries no 'ucpos' (a caller that did
# not record one). Such names sort after every positioned one, in arrival order.
UNPOSITIONED = float('inf')


def _parser_routes(parsed):
    """Map (file index, symbol) -> the route the first parser produced for it."""
    routes = {}
    for entry in parsed:
        if entry.get('label'):
            routes.setdefault((entry['i'], entry.get('symbol') or ''), entry['label'])
    return routes


def _route_of(routes, index, symbol):
    """The parser route of one entry point: its own, else the one of its class.

    An entry declared on `Class.method` inherits the route a parser registered for
    `Class`, so the router mount and the methods use-cases declare under it stay
    together in the panel instead of being scattered by their labels.
    """
    own = routes.get((index, symbol or ''))
    if own is not None:
        return own
    if symbol and '.' in symbol:
        return routes.get((index, symbol.split('.', 1)[0]))
    return None


def merge_entry_points(parsed, declared, fallback):
    """Merge the three sources into the final entry-point list.

    Entries are grouped by (file index, symbol); each group becomes one entry point
    that keeps what every source knows about that place: the label of the most
    precedent source (declared > parsers > fallback), the first kind that is not
    'other' in that same order, the route a parser produced for it or for its class,
    and the names of the use-cases it belongs to, in registry order. The result is
    sorted by (kind, route or label, label, symbol, index).

    `declared` and `fallback` entries carry the name of their use-case in the internal
    key 'uc' and its position in the loaded registry in the internal key 'ucpos'; both
    are read here and neither is emitted.

    Reference: docs/data-contract.md, section 6.2.
    """
    routes = _parser_routes(parsed)
    merged, at, label_rank, kind_rank, ucs = [], {}, {}, {}, {}
    arrival = 0
    for source, entries in (('parsers', parsed), ('declared', declared),
                            ('fallback', fallback)):
        rank = SOURCE_RANK[source]
        for entry in entries:
            symbol = entry.get('symbol') or None
            key = (entry['i'], symbol or '')
            kind = entry['kind']
            if key not in at:
                at[key] = len(merged)
                label_rank[key] = rank
                kind_rank[key] = rank if kind != 'other' else len(SOURCE_RANK)
                ucs[key] = {}
                merged.append({'label': entry['label'], 'kind': kind, 'i': entry['i'],
                               'symbol': symbol,
                               'route': _route_of(routes, entry['i'], symbol),
                               'ucs': []})
            else:
                target = merged[at[key]]
                if rank < label_rank[key]:
                    target['label'] = entry['label']
                    label_rank[key] = rank
                if kind != 'other' and rank < kind_rank[key]:
                    target['kind'] = kind
                    kind_rank[key] = rank
            uc = entry.get('uc')
            if uc:
                # The sources are walked declared-list-then-fallback-list, which is not
                # registry order: a use-case can contribute here through the fallback
                # while a later one declared its entry point. Sort the names on the
                # position the use-case has in the registry, not on arrival.
                position = entry.get('ucpos')
                ucs[key].setdefault(
                    uc, (UNPOSITIONED if position is None else position, arrival))
                arrival += 1

    for key, index in at.items():
        merged[index]['ucs'] = sorted(ucs[key], key=ucs[key].get)

    def sort_key(entry):
        kind = entry['kind']
        return (KINDS.index(kind) if kind in KINDS else len(KINDS),
                entry['route'] or entry['label'], entry['label'],
                entry['symbol'] or '', entry['i'])

    merged.sort(key=sort_key)
    return merged
