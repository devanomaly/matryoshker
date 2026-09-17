"""test_visual_review_import.py — guards the harness's sibling-module loader.

`tools/visual_review.py` loads `config.py` and `probes.py` from its own directory via
`importlib.util` specifically so that a same-named `pipeline/config.py` earlier on
`sys.path` cannot shadow them (see the comment above `_load_sibling` in that file). The
standard invocation (`python tools/visual_review.py ...`, CI included) always puts
`tools/` first, so a regression here would not show up under normal use — only under a
`sys.path` order the documented invocation never produces. This test manufactures that
order directly: preload `pipeline/config.py` as `config` in `sys.modules`, put
`pipeline/` ahead of `tools/`, then run `visual_review.py list` as a subprocess.

Reference: docs/data-contract.md.
"""
import os
import subprocess
import sys

BOOTSTRAP = (
    "import sys, importlib.util, runpy\n"
    "spec = importlib.util.spec_from_file_location('config', 'pipeline/config.py')\n"
    "mod = importlib.util.module_from_spec(spec)\n"
    "sys.modules['config'] = mod\n"
    "spec.loader.exec_module(mod)\n"
    "sys.path.insert(0, 'pipeline')\n"
    "sys.argv = ['visual_review.py', 'list']\n"
    "runpy.run_path('tools/visual_review.py', run_name='__main__')\n"
)


def test_list_survives_pipeline_config_shadowing_sys_modules(repo_root):
    """pipeline/config.py pre-bound to 'config' in sys.modules must not break `list`.

    Guards the fix in tools/visual_review.py: a plain `from config import RUNS, STATES`
    would resolve to pipeline/config.py here (no RUNS/STATES, ImportError) and the
    try/except fallback beside it could not recover, because `config` is already bound
    in sys.modules to the wrong module before the retry.
    """
    proc = subprocess.run([sys.executable, '-c', BOOTSTRAP], cwd=repo_root,
                          capture_output=True, text=True, encoding='utf-8')
    assert proc.returncode == 0, proc.stderr
    assert 'runs (id, config, theme, lang):' in proc.stdout
    assert 'states (' in proc.stdout
