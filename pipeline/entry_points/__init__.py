"""entry_points — registry of route parsers and the entry-point merge.

An entry point is a place where execution enters the codebase: an HTTP route, a
command handler, an event consumer, a CLI command, a scheduled job. They come from
three sources (route parsers, use-case declarations, first-hop fallback) which
`merge_entry_points` deduplicates and orders.

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


def merge_entry_points(parsed, declared, fallback):
    """Merge the three sources into the final entry-point list.

    Order of the sources is parsers, then use-case declarations, then the first-hop
    fallback. Duplicates are keyed by (file index, symbol) and the first occurrence
    wins; the result is sorted by (kind, label, symbol, index).
    """
    merged, seen = [], set()
    for source in (parsed, declared, fallback):
        for entry in source:
            key = (entry['i'], entry.get('symbol') or '')
            if key in seen:
                continue
            seen.add(key)
            merged.append({'label': entry['label'], 'kind': entry['kind'], 'i': entry['i'],
                           'symbol': entry.get('symbol') or None})

    def sort_key(entry):
        kind = entry['kind']
        return (KINDS.index(kind) if kind in KINDS else len(KINDS),
                entry['label'], entry['symbol'] or '', entry['i'])

    merged.sort(key=sort_key)
    return merged
