"""conftest.py — shared fixtures for the Matryoshker test suite.

Puts the repository root on `sys.path` so tests can do `from pipeline import ...`
regardless of the directory pytest was invoked from (this matters most on the
Windows CI runner), and centralizes the paths and skip logic that more than one
test file needs.

Reference: docs/data-contract.md.
"""
import os
import shutil
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

GOLDEN_DIR = os.path.join(REPO_ROOT, 'tests', 'golden')
CONFIG_DIR = os.path.join(REPO_ROOT, 'config')
EXAMPLE_REPO = os.path.join(REPO_ROOT, 'examples', 'sample-drf')
EXAMPLE_USECASES = os.path.join(EXAMPLE_REPO, 'usecases.json')
VIEWER_TEMPLATE = os.path.join(REPO_ROOT, 'viewer', 'template.html')


@pytest.fixture(scope='session')
def repo_root():
    return REPO_ROOT


@pytest.fixture(scope='session')
def golden_dir():
    return GOLDEN_DIR


@pytest.fixture(scope='session')
def config_dir():
    return CONFIG_DIR


@pytest.fixture(scope='session')
def example_repo():
    return EXAMPLE_REPO


@pytest.fixture(scope='session')
def example_usecases():
    return EXAMPLE_USECASES


@pytest.fixture(scope='session')
def viewer_template():
    return VIEWER_TEMPLATE


def node_available():
    """Whether a real extraction can be run: node on PATH and the extractor's
    node_modules already installed (npm ci --ignore-scripts in extractor/)."""
    if shutil.which('node') is None:
        return False
    return os.path.isdir(os.path.join(REPO_ROOT, 'extractor', 'node_modules'))


def skip_without_node_binary():
    """Skip the current test cleanly when there is no node on PATH.

    For tests that only need the JavaScript engine — e.g. running a block extracted
    from viewer/template.html — and never touch the extractor, so they must not be
    skipped just because extractor/node_modules has not been installed.
    """
    if shutil.which('node') is None:
        pytest.skip('node executable not found on PATH')


def skip_without_node():
    """Skip the current test cleanly when a real extraction cannot be run."""
    skip_without_node_binary()
    if not os.path.isdir(os.path.join(REPO_ROOT, 'extractor', 'node_modules')):
        pytest.skip('extractor/node_modules missing; run "npm ci --ignore-scripts" in extractor/')



@pytest.fixture(scope='session')
def require_node():
    """Fixture form of skip_without_node(), for tests that prefer a fixture."""
    skip_without_node()
    return True



