"""_common.py — helpers shared by the pipeline scripts.

No external dependencies: standard library only. It concentrates file reading and
writing plus path normalization so that every CLI fails with the same useful
sentence instead of a raw traceback.

See docs/data-contract.md, section 9.
"""
import json
import os
import sys

# The Windows path separator. Written as chr(92) so that this file never carries a
# literal backslash, which tools that read or rewrite it could mangle.
BS = chr(92)

# Lowest version the pipeline is exercised on. Nothing is blocked below it — only
# warned about, because the real failure usually shows up far from here (recent
# syntax or stdlib features).
MIN_PYTHON = (3, 10)


def norm_path(path):
    """Normalize path separators to '/' and drop a leading './'.

    Every path inside the JSON files is relative to the target repository root,
    uses '/' and never starts with './' (docs/data-contract.md, section 1).
    """
    path = path.replace(BS, '/')
    while path.startswith('./'):
        path = path[2:]
    return path


def read_json(path, label):
    """Read a UTF-8 JSON file, naming the argument that failed in the error.

    `label` is the CLI argument name (for example '--es'), so the user knows
    exactly which path to fix.
    """
    try:
        with open(path, encoding='utf-8') as fh:
            return json.load(fh)
    except FileNotFoundError:
        raise SystemExit(f'{label}: file not found: {path}')
    except IsADirectoryError:
        raise SystemExit(f'{label}: expected a file, got a directory: {path}')
    except PermissionError:
        raise SystemExit(f'{label}: no read permission: {path}')
    except UnicodeDecodeError as exc:
        raise SystemExit(f'{label}: file is not UTF-8 ({path}): {exc}')
    except json.JSONDecodeError as exc:
        raise SystemExit(f'{label}: invalid JSON in {path} (line {exc.lineno}, column {exc.colno}): {exc.msg}')


def read_text(path, label):
    """Read a UTF-8 text file with the same error messages as read_json."""
    try:
        with open(path, encoding='utf-8') as fh:
            return fh.read()
    except FileNotFoundError:
        raise SystemExit(f'{label}: file not found: {path}')
    except IsADirectoryError:
        raise SystemExit(f'{label}: expected a file, got a directory: {path}')
    except PermissionError:
        raise SystemExit(f'{label}: no read permission: {path}')
    except UnicodeDecodeError as exc:
        raise SystemExit(f'{label}: file is not UTF-8 ({path}): {exc}')


def write_text(path, text, label='--out'):
    """Write UTF-8 text and return the size in bytes.

    The destination directory is checked before writing so that an --out pointing
    at a missing folder fails with one sentence instead of a traceback.
    """
    parent = os.path.dirname(os.path.abspath(path))
    if not os.path.isdir(parent):
        raise SystemExit(f'{label}: output directory does not exist: {parent}')
    try:
        with open(path, 'w', encoding='utf-8') as fh:
            fh.write(text)
    except IsADirectoryError:
        raise SystemExit(f'{label}: expected a file, got a directory: {path}')
    except PermissionError:
        raise SystemExit(f'{label}: no write permission: {path}')
    return len(text.encode('utf-8'))


def warn(message):
    """Write a diagnostic to stderr without breaking on a narrow console.

    A Windows console is often cp1252 with errors='strict': em dashes and accented
    characters coming from the data would raise UnicodeEncodeError and kill the
    script. Here the impossible character becomes '?' and the run continues.
    """
    try:
        print(message, file=sys.stderr)
    except UnicodeEncodeError:
        encoding = sys.stderr.encoding or 'ascii'
        print(message.encode(encoding, 'replace').decode(encoding, 'replace'), file=sys.stderr)


def warn_python_version():
    """Warn on stderr, without stopping, when the interpreter predates the tested one.

    Called at the start of every main. On Windows the 'python' on PATH is often a
    Store shim or an old install even when a recent version is present — the warning
    points at that cause before the real error shows up somewhere else.
    """
    if sys.version_info < MIN_PYTHON:
        warn(f'warning: Python {sys.version_info.major}.{sys.version_info.minor} detected; '
             f'the pipeline is tested with {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+; on Windows check '
             "'python --version' or use 'py -3'")


def kb(nbytes):
    """Size in whole KB, for the one-line summaries the CLIs print."""
    return nbytes // 1024
