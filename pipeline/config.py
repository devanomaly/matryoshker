"""config.py — loading and validation of config/<repo>.json.

This module has no CLI. `load_config` returns a dict where every documented key is
present with its default applied, the v1 aliases are resolved and the deprecated keys
have been warned about, so callers never have to call `.get` with a default again.
Fatal problems are raised as SystemExit('<flag>: <message>') with the CLI argument the
caller passed (usually '--config').

Reference: docs/data-contract.md, section 3.
"""
try:
    from _common import read_json, warn
    from entry_points import get_parser
except ImportError:  # imported as part of the package: from pipeline.config import ...
    from pipeline._common import read_json, warn
    from pipeline.entry_points import get_parser

# UI languages the viewer ships strings for.
LANGUAGES = ('en', 'pt-BR')

# Every documented key, with the default applied when it is missing.
DEFAULTS = {
    'repo': '',
    'commit': '?',
    'date': '',
    'lang': 'en',
    'categories': (),
    'rules': (),
    'fallback_category': 'other',
    'test_path_marker': '/tests',
    'test_category': 'tests',
    'hop_path_prefixes': (),
}

# Keys accepted but not part of the v2 contract.
ALIASES = {'data': 'date'}          # v1 name of "date"; "date" wins when both exist
DEPRECATED = ('urls_files',)        # v1 route list; folded into entry_points

# Keys of a category object.
CATEGORY_KEYS = ('id', 'label', 'gray', 'muted')


def _default(key):
    value = DEFAULTS[key]
    return list(value) if isinstance(value, tuple) else value


def load_config(path, label='--config'):
    """Read a repo config and return it with defaults, aliases and deprecations resolved."""
    raw = read_json(path, label)
    if not isinstance(raw, dict):
        raise SystemExit(f'{label}: expected a JSON object, got {type(raw).__name__}')

    config = dict(raw)
    config.pop('$schema', None)     # editor hint; the pipeline ignores it

    for alias, canonical in ALIASES.items():
        if alias in config:
            value = config.pop(alias)
            config.setdefault(canonical, value)

    known = set(DEFAULTS) | {'entry_points'} | set(DEPRECATED)
    for key in list(config):
        if key not in known:
            warn(f'warning: config: unknown key "{key}" ignored')
            config.pop(key)

    for key in DEFAULTS:
        # test_path_marker is handled below: an explicit null disables the check,
        # so it must not be filled in with the default here.
        if key != 'test_path_marker' and config.get(key) is None:
            config[key] = _default(key)

    repo = config['repo']
    if not isinstance(repo, str) or not repo.strip():
        raise SystemExit(f'{label}: "repo" is required and must be a non-empty string')
    config['repo'] = repo.strip()

    for key in ('commit', 'date'):
        if not isinstance(config[key], str):
            warn(f'warning: config: "{key}" must be a string; using {_default(key)!r}')
            config[key] = _default(key)

    for key in ('fallback_category', 'test_category'):
        if not isinstance(config[key], str) or not config[key]:
            warn(f'warning: config: "{key}" must be a non-empty string; '
                 f'using {_default(key)!r}')
            config[key] = _default(key)

    marker = config.get('test_path_marker', _default('test_path_marker'))
    if marker is None:
        marker = ''         # explicit null: no path marks a test file
    elif not isinstance(marker, str):
        warn('warning: config: "test_path_marker" must be a string or null; check disabled')
        marker = ''
    config['test_path_marker'] = marker

    if config['lang'] not in LANGUAGES:
        warn(f'warning: config: unknown lang "{config["lang"]}", using "en"')
        config['lang'] = 'en'

    config['categories'] = _load_categories(config['categories'], label)
    config['rules'] = _load_rules(config['rules'], label)
    config['hop_path_prefixes'] = _load_prefixes(config['hop_path_prefixes'], label)
    config['entry_points'] = _load_entry_points(config, label)
    _warn_undeclared_categories(config)
    return config


def _load_categories(raw, label):
    """Validate the category list: objects with a unique, non-empty string id."""
    if not isinstance(raw, list):
        raise SystemExit(f'{label}: "categories" must be an array')
    categories, seen = [], set()
    for n, category in enumerate(raw):
        if not isinstance(category, dict):
            raise SystemExit(f'{label}: categories[{n}] must be an object with an "id"')
        cid = category.get('id')
        if not isinstance(cid, str) or not cid.strip():
            raise SystemExit(f'{label}: categories[{n}] needs a non-empty string "id"')
        cid = cid.strip()
        if cid in seen:
            raise SystemExit(f'{label}: categories[{n}]: duplicate category id "{cid}"')
        seen.add(cid)
        for key in category:
            if key not in CATEGORY_KEYS:
                warn(f'warning: config: categories[{n}]: unknown key "{key}" ignored')
        clean = {'id': cid, 'label': category.get('label') or cid}
        if category.get('gray'):
            clean['gray'] = True
        if category.get('muted'):
            clean['muted'] = True
        categories.append(clean)
    return categories


def _load_rules(raw, label):
    """Validate the classification rules: [prefix, category id] pairs."""
    if not isinstance(raw, list):
        raise SystemExit(f'{label}: "rules" must be an array of [prefix, category] pairs')
    rules = []
    for n, rule in enumerate(raw):
        if not isinstance(rule, (list, tuple)) or len(rule) != 2:
            raise SystemExit(
                f'{label}: rules[{n}] must be a [prefix, category] pair, got: {rule!r}')
        prefix, category = rule
        if not isinstance(prefix, str) or not isinstance(category, str):
            raise SystemExit(f'{label}: rules[{n}]: both the prefix and the category must be strings')
        if not prefix:
            raise SystemExit(f'{label}: rules[{n}]: the prefix cannot be empty (it would match every file)')
        rules.append([prefix, category])
    return rules


def _load_prefixes(raw, label):
    """Validate hop_path_prefixes: non-empty strings, kept in config order."""
    if not isinstance(raw, list):
        raise SystemExit(f'{label}: "hop_path_prefixes" must be an array of strings')
    for n, prefix in enumerate(raw):
        if not isinstance(prefix, str) or not prefix:
            raise SystemExit(f'{label}: hop_path_prefixes[{n}] must be a non-empty string')
    return list(raw)


def _load_entry_points(config, label):
    """Validate entry_points.parsers, folding the deprecated urls_files into it."""
    raw = config.get('entry_points')
    urls_files = config.pop('urls_files', None)

    if urls_files is not None:
        if raw is not None:
            warn('warning: config key "urls_files" is deprecated; use entry_points.parsers '
                 '(ignored here because entry_points is present)')
        else:
            warn('warning: config key "urls_files" is deprecated; use entry_points.parsers')
            if not isinstance(urls_files, list):
                raise SystemExit(f'{label}: "urls_files" must be an array of file paths')
            raw = {'parsers': [{'name': 'django-drf', 'files': list(urls_files),
                                'route_prefix': '', 'ignore_views': []}]}

    if raw is None:
        return {'parsers': []}
    if not isinstance(raw, dict):
        raise SystemExit(f'{label}: "entry_points" must be an object with a "parsers" array')
    for key in raw:
        if key != 'parsers':
            warn(f'warning: config: entry_points: unknown key "{key}" ignored')

    parsers = raw.get('parsers') or []
    if not isinstance(parsers, list):
        raise SystemExit(f'{label}: "entry_points.parsers" must be an array')
    clean = []
    for n, parser in enumerate(parsers):
        if not isinstance(parser, dict):
            raise SystemExit(f'{label}: entry_points.parsers[{n}] must be an object with a "name"')
        name = parser.get('name')
        if not isinstance(name, str) or not name.strip():
            raise SystemExit(f'{label}: entry_points.parsers[{n}] needs a non-empty string "name"')
        name = name.strip()
        get_parser(name, label)     # fatal, listing the available names
        files = parser.get('files') or []
        if not isinstance(files, list) or any(not isinstance(f, str) or not f for f in files):
            raise SystemExit(f'{label}: entry_points.parsers[{n}].files must be an array of file paths')
        entry = dict(parser)
        entry['name'] = name
        entry['files'] = list(files)
        clean.append(entry)
    return {'parsers': clean}


def _warn_undeclared_categories(config):
    """Warn about category ids that no category object declares (the viewer paints them gray)."""
    declared = {c['id'] for c in config['categories']}
    if not declared:
        return
    used = [category for _prefix, category in config['rules']]
    used += [config['fallback_category']]
    if config['test_path_marker']:
        used.append(config['test_category'])
    for category in dict.fromkeys(used):
        if category not in declared:
            warn(f'warning: config: category "{category}" is used but not declared in "categories"')
