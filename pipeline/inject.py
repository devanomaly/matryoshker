"""inject.py — embeds the data in the template and writes the self-contained HTML.

Usage:
  python pipeline/inject.py --template viewer/template.html --data data.json \
      [--extra extra.json] --out matryoshker.html

The embedded object always has the six keys the viewer reads
({meta, files, imports, ucs, entry_points, calls}); without --extra the last two are
written empty. When extra.json carries an nfiles that disagrees with data.json the
merge is refused: the two files would come from different extractions and every file
index in them would point somewhere else.

Reference: docs/data-contract.md, sections 8 and 10.5.
"""
import argparse
import json

try:
    from _common import kb, read_json, read_text, warn_python_version, write_text
except ImportError:  # run as a module: python -m pipeline.inject
    from pipeline._common import kb, read_json, read_text, warn_python_version, write_text

# Stable internal name of the injection point in the template (not a leftover brand).
PLACEHOLDER = '__MATRYOSHKER_DATA__'


def parse_args():
    ap = argparse.ArgumentParser(
        description='Embeds the data in the template and writes the self-contained HTML.')
    ap.add_argument('--template', required=True, metavar='FILE',
                    help=f'HTML template containing the {PLACEHOLDER} placeholder')
    ap.add_argument('--data', required=True, metavar='FILE',
                    help='data.json produced by prep_data.py')
    ap.add_argument('--extra', default=None, metavar='FILE',
                    help='extra.json produced by prep_extra.py (optional)')
    ap.add_argument('--out', required=True, metavar='FILE',
                    help='path of the HTML to write')
    return ap.parse_args()


def main():
    warn_python_version()
    args = parse_args()

    base = read_json(args.data, '--data')
    entry_points, calls = [], {}
    if args.extra:
        extra = read_json(args.extra, '--extra')
        nfiles = extra.get('nfiles')
        expected = (base.get('meta') or {}).get('nfiles')
        if nfiles is not None and expected is not None and nfiles != expected:
            raise SystemExit(f'--extra: nfiles={nfiles} does not match --data '
                             f'meta.nfiles={expected} (different extractions?)')
        entry_points = extra.get('entry_points', [])
        calls = extra.get('calls', {})
    base['entry_points'] = entry_points
    base['calls'] = calls

    # '</' is escaped so the payload can never close the <script> that hosts it.
    payload = json.dumps(base, ensure_ascii=False, separators=(',', ':')) \
        .replace('</', '<' + chr(92) + '/')

    template = read_text(args.template, '--template')
    if PLACEHOLDER not in template:
        raise SystemExit(f'--template: {args.template} does not contain the placeholder {PLACEHOLDER}')

    nbytes = write_text(args.out, template.replace(PLACEHOLDER, payload))
    print(f'{args.out}: {kb(nbytes)}KB')


if __name__ == '__main__':
    main()
