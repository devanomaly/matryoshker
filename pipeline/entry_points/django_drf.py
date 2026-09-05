"""django_drf.py — entry-point parser for Django/DRF url configurations.

It scans the files listed in `config.entry_points.parsers[n].files` for the two
shapes that mount a class-based view, and maps each route to the file that declares
the view class:

    router.register("books", BookViewSet)      -> <route_prefix>/books
    path("health/", HealthView.as_view())      -> <route_prefix>/health/

Options (from the same config entry): `route_prefix` (default "") and `ignore_views`
(default []). Function-based views and include() are out of scope — a parser for them
is a welcome contribution.

Reference: docs/data-contract.md, section 6.4.
"""
import re

try:
    from _common import read_text, warn
except ImportError:  # imported as part of the package
    from pipeline._common import read_text, warn

NAME = 'django-drf'

ROUTER_REGISTER = re.compile(
    r"^\s*router\.register\(r?['\"]([^'\"]+)['\"]\s*,\s*(?:\w+\.)?(\w+)", re.M)
PATH_AS_VIEW = re.compile(
    r"path\(['\"]([^'\"]+)['\"]\s*,\s*(?:\w+\.)?(\w+)\.as_view")

# Options this parser understands; anything else is reported and ignored.
OPTIONS = ('route_prefix', 'ignore_views')


def parse(files, class_file, options):
    """Return the entry points found in `files`.

    `files` are absolute paths, `class_file` maps a top-level class name to the
    repo-relative file that declares it, and `options` is the config entry minus
    `name` and `files`.
    """
    for key in options:
        if key not in OPTIONS:
            warn(f'warning: parser {NAME}: unknown option "{key}"')

    route_prefix = (options.get('route_prefix') or '').rstrip('/')
    ignore_views = options.get('ignore_views') or []

    if not files:
        warn(f'warning: parser {NAME}: no files to scan; it produced no entry points')
        return []

    try:
        from . import record_parser_drop
    except ImportError:  # pragma: no cover - parser used outside the package
        def record_parser_drop(_parser, _file, reason, what):
            warn(f'parser {NAME} ({_file}): dropped [{reason}]: {what}')

    entry_points = []
    for source_file in files:
        source = read_text(source_file, '--config')
        for regex in (ROUTER_REGISTER, PATH_AS_VIEW):
            for match in regex.finditer(source):
                view = match.group(2)
                if any(ignored in view for ignored in ignore_views):
                    continue
                route = route_prefix + '/' + match.group(1).lstrip('/')
                path = class_file.get(view)
                if path is None:
                    record_parser_drop(NAME, source_file,
                                       'view class not found in the extraction',
                                       f'{route} {view}')
                    continue
                entry_points.append({'label': route, 'kind': 'http', 'path': path,
                                     'symbol': view})
    return entry_points
