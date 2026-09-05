"""build.py — runs the whole pipeline with one command.

Usage:
  python pipeline/build.py --repo <target repo> --config config/<repo>.json \
      [--ucs data/<repo>/usecases.json] [--out matryoshker.html] [--extract-out out] \
      [--lang <extractor language>] [--exclude "p1,p2"] [--template viewer/template.html] \
      [--node node] [--skip-extract] [--strict]

Four steps, each a subprocess whose stdout and stderr are passed through unchanged:

  1. node extractor/extract.mjs  -> <extract-out>/{scan,im,es}-output.json
  2. prep_data.py                -> <extract-out>/data.json
  3. prep_extra.py               -> <extract-out>/extra.json
  4. inject.py                   -> <out>

A failing step stops the build and build.py exits with that same code; its own
failures exit 1. The target repository is only ever read.

Reference: docs/data-contract.md, section 10.6.
"""
import argparse
import os
import shutil
import subprocess
import sys

try:
    from _common import warn, warn_python_version
except ImportError:  # run as a module: python -m pipeline.build
    from pipeline._common import warn, warn_python_version

# Root of the Matryoshker checkout: the parent of pipeline/, resolved from this file,
# so the command works from any current directory.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

STEPS = 4

# Exit code the Python steps use for --strict.
STRICT_EXIT = 3


def parse_args():
    ap = argparse.ArgumentParser(
        description='Runs the whole Matryoshker pipeline with one command.')
    ap.add_argument('--repo', required=True, metavar='DIR',
                    help='root of the repository to map (read-only)')
    ap.add_argument('--config', required=True, metavar='FILE', help='repo config')
    ap.add_argument('--ucs', default=None, metavar='FILE', help='use-case registry (optional)')
    ap.add_argument('--out', default='matryoshker.html', metavar='FILE',
                    help='final HTML (default: matryoshker.html)')
    ap.add_argument('--extract-out', default='out', metavar='DIR',
                    help='directory for the extraction, data.json and extra.json (default: out)')
    ap.add_argument('--lang', default=None, metavar='LANGUAGE',
                    help='source language filter passed to extract.mjs (not the UI language)')
    ap.add_argument('--exclude', default=None, metavar='PATTERNS',
                    help='comma-separated exclude patterns passed to extract.mjs')
    ap.add_argument('--template', default=None, metavar='FILE',
                    help='viewer template (default: <matryoshker root>/viewer/template.html)')
    ap.add_argument('--node', default='node', metavar='EXECUTABLE',
                    help='Node executable (default: node)')
    ap.add_argument('--skip-extract', action='store_true',
                    help='reuse the es/im outputs already in --extract-out')
    ap.add_argument('--strict', action='store_true',
                    help='forwarded to prep_data.py and prep_extra.py')
    return ap.parse_args()


def run_step(number, name, command):
    """Run one step as a subprocess, stopping the build with its exit code on failure."""
    warn(f'build.py: step {number}/{STEPS} {name}')
    code = subprocess.call(command)
    if code != 0:
        warn(f'build.py: step {number}/{STEPS} {name} failed (exit {code})')
        raise SystemExit(code)


def main():
    warn_python_version()
    args = parse_args()

    if not os.path.isdir(args.repo):
        raise SystemExit(f'--repo: not a directory: {args.repo}')
    template = args.template or os.path.join(ROOT, 'viewer', 'template.html')

    extract_out = args.extract_out
    os.makedirs(extract_out, exist_ok=True)
    es = os.path.join(extract_out, 'es-output.json')
    imports = os.path.join(extract_out, 'im-output.json')
    data = os.path.join(extract_out, 'data.json')
    extra = os.path.join(extract_out, 'extra.json')

    if args.skip_extract:
        for path in (es, imports):
            if not os.path.isfile(path):
                raise SystemExit(f'--skip-extract: {path} not found; run the extraction first')
        warn(f'build.py: step 1/{STEPS} extract skipped (--skip-extract)')
    else:
        if not os.path.isdir(os.path.join(ROOT, 'extractor', 'node_modules')):
            raise SystemExit('build.py: extractor dependencies missing; '
                             'run "npm ci --ignore-scripts" in extractor/')
        if not (shutil.which(args.node) or os.path.isfile(args.node)):
            raise SystemExit(f'build.py: node executable not found: {args.node}')
        command = [args.node, os.path.join(ROOT, 'extractor', 'extract.mjs'), args.repo,
                   '--out', extract_out]
        if args.exclude:
            command += ['--exclude', args.exclude]
        if args.lang:
            command += ['--lang', args.lang]
        run_step(1, 'extract', command)

    prep_data = [sys.executable, os.path.join(ROOT, 'pipeline', 'prep_data.py'),
                 '--es', es, '--imports', imports, '--config', args.config, '--out', data]
    prep_extra = [sys.executable, os.path.join(ROOT, 'pipeline', 'prep_extra.py'),
                  '--es', es, '--imports', imports, '--config', args.config,
                  '--repo', args.repo, '--out', extra]
    if args.ucs:
        prep_data += ['--ucs', args.ucs]
        prep_extra += ['--ucs', args.ucs]
    if args.strict:
        prep_data.append('--strict')
        prep_extra.append('--strict')

    run_step(2, 'prep_data', prep_data)
    run_step(3, 'prep_extra', prep_extra)
    run_step(4, 'inject', [sys.executable, os.path.join(ROOT, 'pipeline', 'inject.py'),
                           '--template', template, '--data', data, '--extra', extra,
                           '--out', args.out])


if __name__ == '__main__':
    main()
