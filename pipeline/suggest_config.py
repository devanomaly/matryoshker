"""suggest_config.py — suggests a DRAFT config/<repo>.json from the scan.

Usage:
  python pipeline/suggest_config.py --scan scan-output.json --repo NAME [--out config.json]

Input: the scan-output.json produced by extract.mjs (a list of files with path and
language).
Output: a v2 draft (docs/data-contract.md, section 3) — `categories` ordered by file
count, `rules` mapping prefix -> category (each prefix ends with '/', so that
'src/app/' cannot also capture 'src/apple/'), `commit` = "ADJUST", an empty `date`
and `lang` = "en" for a human to fill in. Without --out, the JSON is printed to stdout.

Grouping is by top-level directory; when the top level is a single monolith ('app/',
'src/', 'v1/'... or a directory that alone holds most of the files) the script goes
one level deeper and those directories also become `hop_path_prefixes`. Test
directories (test/tests/spec) become a single gray+muted category; files at the root
and directories that are too small fall back to the 'other' category with no rule.

Nothing here guesses the role of a directory — the script just counts files and
names folders. That is why the dir|files|language table is printed to stderr: it is
what the human uses to decide which categories to merge, rename, or drop before
using the config. Entry points are not guessed either; the stderr notes show the
block to add when the repo has routes worth parsing.
"""
import argparse
import json
from collections import Counter

try:
    from _common import kb, norm_path, read_json, warn, warn_python_version, write_text
except ImportError:  # run as a module: python -m pipeline.suggest_config
    from pipeline._common import (kb, norm_path, read_json, warn, warn_python_version,
                                  write_text)

# Directories that are usually the root of a monolith: when they show up at the
# top level, the useful grouping is one level below (src/models, v1/views...).
MONOLITH_DIRS = {'app', 'apps', 'src', 'source', 'lib', 'pkg', 'internal', 'v1'}

# A top-level directory that alone holds this fraction of the files is also
# treated as a monolith, even with a name outside the list above.
MONOLITH_SHARE = 0.5

# Folder names that mark tests; they become a single gray+muted category.
TEST_DIR_NAMES = {'test', 'tests', 'spec', 'specs', '__tests__'}

# The viewer gives palette colors to the first 6 non-gray categories.
COLORED_SLOTS = 6

# Cap on suggested categories: anything above this falls into the fallback (a config
# with 30 categories does not help anyone read the map).
MAX_CATEGORIES = 12

FALLBACK_ID = 'other'
TEST_ID = 'tests'
DEFAULT_TEST_MARKER = '/tests'
DEFAULT_LANG = 'en'

# Order the keys are written in; it matches docs/data-contract.md, section 3.1.
KEY_ORDER = ('repo', 'commit', 'date', 'lang', 'categories', 'rules', 'fallback_category',
             'test_path_marker', 'test_category', 'hop_path_prefixes')

# Keys whose value is a JSON array, printed one item per line.
LIST_KEYS = ('categories', 'rules', 'hop_path_prefixes')

# Shown on stderr: the block to add by hand when the repo has routes to parse.
ENTRY_POINTS_EXAMPLE = '''  "entry_points": {
    "parsers": [
      { "name": "django-drf", "files": ["api/urls.py"], "route_prefix": "", "ignore_views": [] }
    ]
  }'''


def parse_args():
    ap = argparse.ArgumentParser(
        description='Suggests a draft config/<repo>.json from scan-output.json.')
    ap.add_argument('--scan', required=True, metavar='FILE',
                    help='scan-output.json produced by extract.mjs')
    ap.add_argument('--repo', required=True, metavar='NAME',
                    help='repo name (goes into the config\'s "repo" field)')
    ap.add_argument('--out', default=None, metavar='FILE',
                    help='path of the config to generate (without it, JSON goes to stdout)')
    return ap.parse_args()


def collect_files(scan):
    """Extracts [(path, language)] from scan-output.json."""
    if not isinstance(scan, dict) or 'files' not in scan:
        raise SystemExit("--scan: JSON has no 'files' key (expected the extract.mjs scan output)")
    files = []
    for n, entry in enumerate(scan['files']):
        if not isinstance(entry, dict) or 'path' not in entry:
            raise SystemExit(f"--scan: files[{n}] must be an object with a 'path' key")
        files.append((norm_path(entry['path']), entry.get('language') or 'unknown'))
    if not files:
        raise SystemExit('--scan: no files in the scan (nothing to suggest)')
    return files


def find_monoliths(files):
    """Top-level directories that should be opened at the second level."""
    total = len(files)
    top = Counter(p.split('/')[0] for p, _lang in files if '/' in p)
    monoliths = set()
    for name, count in top.items():
        if name not in MONOLITH_DIRS and count < total * MONOLITH_SHARE:
            continue
        subdirs = {p.split('/')[1] for p, _lang in files
                   if p.startswith(name + '/') and p.count('/') > 1}
        if len(subdirs) >= 2:
            monoliths.add(name)
    return monoliths


def group_dirs(files, monoliths):
    """Groups files by directory prefix, ordered by descending count.

    Each group: {prefix, files, language, test}. The '' prefix collects loose
    files at the repo root — they do not become a rule (an empty prefix would
    match everything).
    """
    groups = {}
    for path, lang in files:
        parts = path.split('/')
        if len(parts) == 1:
            prefix = ''
        elif parts[0] in monoliths and len(parts) > 2:
            prefix = parts[0] + '/' + parts[1]
        else:
            prefix = parts[0]
        group = groups.setdefault(prefix, {'prefix': prefix, 'files': 0, 'langs': Counter()})
        group['files'] += 1
        if lang != 'unknown':
            group['langs'][lang] += 1

    ordered = []
    for group in groups.values():
        langs = group.pop('langs')
        top_lang = sorted(langs.items(), key=lambda kv: (-kv[1], kv[0]))
        group['language'] = top_lang[0][0] if top_lang else 'unknown'
        group['test'] = group['prefix'].split('/')[-1].lower() in TEST_DIR_NAMES
        ordered.append(group)
    ordered.sort(key=lambda g: (-g['files'], g['prefix']))
    return ordered


def make_id(prefix, used):
    """Category id derived from the folder name, unique within the config."""
    tail = prefix.split('/')[-1]
    slug = ''.join(ch if ch.isalnum() else '_' for ch in tail.lower()).strip('_')
    candidate = slug or 'group'
    if candidate in used:
        candidate = ''.join(ch if ch.isalnum() else '_' for ch in prefix.lower()).strip('_')
    n = 2
    base = candidate
    while candidate in used:
        candidate = f'{base}_{n}'
        n += 1
    used.add(candidate)
    return candidate


def make_label(prefix):
    """Readable label derived from the folder name ('user_profile' -> 'User Profile')."""
    tail = prefix.split('/')[-1].lstrip('.')
    return tail.replace('_', ' ').replace('-', ' ').strip().title() or prefix


def order_rules(rules):
    """Puts the more specific rule first: 'v1/models/' must come before 'v1/'.

    prep_data.py matches by startswith in file order, so a rule that is a
    prefix of another one has to come after it.
    """
    prefixes = [prefix for prefix, _cat in rules]

    def specificity(rule):
        prefix = rule[0]
        return -sum(1 for other in prefixes if other != prefix and prefix.startswith(other))

    return sorted(rules, key=specificity)


def build_config(groups, monoliths, repo):
    """Builds the config draft and returns (config, kept, dropped)."""
    normal = [g for g in groups if g['prefix'] and not g['test']]
    tests = [g for g in groups if g['prefix'] and g['test']]
    kept, dropped = normal[:MAX_CATEGORIES], normal[MAX_CATEGORIES:]

    used_ids = {FALLBACK_ID, TEST_ID}
    categories, rules = [], []
    for n, group in enumerate(kept):
        category = {'id': make_id(group['prefix'], used_ids), 'label': make_label(group['prefix'])}
        if n >= COLORED_SLOTS:
            category['gray'] = True
        categories.append(category)
        rules.append([group['prefix'] + '/', category['id']])

    categories.append({'id': FALLBACK_ID, 'label': 'Other', 'gray': True})
    categories.append({'id': TEST_ID, 'label': 'Tests', 'gray': True, 'muted': True})
    for group in tests:
        rules.append([group['prefix'] + '/', TEST_ID])

    marker = DEFAULT_TEST_MARKER
    if tests:
        marker = '/' + tests[0]['prefix'].split('/')[-1]

    config = {'repo': repo, 'commit': 'ADJUST', 'date': '', 'lang': DEFAULT_LANG,
              'categories': categories, 'rules': order_rules(rules),
              'fallback_category': FALLBACK_ID, 'test_path_marker': marker,
              'test_category': TEST_ID,
              'hop_path_prefixes': sorted(name + '/' for name in monoliths)}
    return config, kept, dropped


def dump_config(config):
    """Serializes the draft with one array item per line, in the documented key order."""
    def j(value):
        return json.dumps(value, ensure_ascii=False)

    lines = ['{']
    for key in KEY_ORDER:
        value = config[key]
        if key not in LIST_KEYS:
            lines.append(f'  {j(key)}: {j(value)},')
        elif not value:
            lines.append(f'  {j(key)}: [],')
        else:
            body = ',\n'.join(f'    {j(item)}' for item in value)
            lines += [f'  {j(key)}: [', body, '  ],']
    lines[-1] = lines[-1].rstrip(',')
    lines.append('}')
    return '\n'.join(lines) + '\n'


def print_table(groups):
    """dir|files|language table printed to stderr — the basis for the human decision."""
    rows = [(g['prefix'] or '(root)', str(g['files']), g['language']) for g in groups]
    width = max(len(row[0]) for row in rows)
    warn(f"{'dir'.ljust(width)} | files    | language")
    warn(f"{'-' * width}-+----------+----------")
    for name, count, lang in rows:
        warn(f'{name.ljust(width)} | {count.rjust(8)} | {lang}')


def main():
    warn_python_version()
    args = parse_args()

    scan = read_json(args.scan, '--scan')
    files = collect_files(scan)
    monoliths = find_monoliths(files)
    groups = group_dirs(files, monoliths)
    config, kept, dropped = build_config(groups, monoliths, args.repo)

    print_table(groups)
    warn('')
    if dropped:
        names = ', '.join(g['prefix'] for g in dropped)
        warn(f"{len(dropped)} smaller directories got no rule and fall into "
             f"'{FALLBACK_ID}': {names}")
    root = next((g for g in groups if not g['prefix']), None)
    if root:
        warn(f"{root['files']} files at the repo root also fall into '{FALLBACK_ID}' "
             '(an empty prefix would match everything)')

    text = dump_config(config)
    if args.out:
        nbytes = write_text(args.out, text)
        print(f'categories={len(config["categories"])} rules={len(config["rules"])} '
              f'dirs={len(kept)} -> {args.out} ({kb(nbytes)}KB)')
    else:
        print(text, end='')

    warn('')
    warn('no entry_points block is suggested — routes are not guessed. Add one by hand '
         'when the repo has routes to parse:')
    warn(ENTRY_POINTS_EXAMPLE)
    warn('draft generated — review categories/rules before using it')


if __name__ == '__main__':
    main()
