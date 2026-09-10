"""config.py — what the visual-review harness runs, and in what order.

Split out of visual_review.py so the run matrix and the state list can be read (and
edited) without scrolling past three hundred lines of embedded JavaScript. Pure data:
no imports, no logic, nothing here touches a browser.

Reference: docs/data-contract.md (the viewer's DOM and data contract).
"""
# ---------------------------------------------------------------- run matrix
# A one-factor-at-a-time star around a common baseline, not the theme x config x lang
# cube: the theme provably changes no metric, so the missing cells would add screenshots
# and runtime without adding information. Every dimension is still varied exactly once.
RUNS = [
    {'id': 'example.light.en', 'config': 'example', 'theme': 'light', 'lang': 'en'},
    {'id': 'example.dark.en', 'config': 'example', 'theme': 'dark', 'lang': 'en'},
    {'id': 'example-ddd.light.en', 'config': 'example-ddd', 'theme': 'light', 'lang': 'en'},
    {'id': 'example.light.pt-BR', 'config': 'example', 'theme': 'light', 'lang': 'pt-BR'},
]

# ---------------------------------------------------------------- state list
# Canonical order. Names are stable so two runs compare entry by entry.
STATES = [
    'context',
    'packages',                  # also the empty state: no use-case, no entry point
    'symbols',
    'symbols_symbol_selected',
    'flow_usecase',
    'flow_entry_point',
    'flow_call_tree',
    'flow_empty',
    'packages_usecase_overlay',
    'context_entry_point_lens',
    'file_selected_detail',
    'entry_points_panel_open',
    'stars_panel_open',
    'search_results',
]

# Deliberately not states, and why:
#   - the muted-categories toggle (#tgtests): a superset of `packages` with no code path
#     beyond visible(); it would near-duplicate six states.
#   - hidden folders (the Context "x" and #bhid): writes localStorage, a per-viewer
#     preference rather than a review surface.
#   - the symbol-scoped call tree ([data-tree="sym"]): the same callTreeSvg path as
#     flow_call_tree with a narrower root.
#   - the export-statuses panel and the status <select>: they mutate localStorage drafts,
#     which would make the run order-dependent.
#   - drag / pan / zoom (offs.*, k/tx/ty): non-deterministic by nature, and excluded from
#     every metric on purpose.
#   - "entry points absent entirely" (data-contract 13.3): not reachable from either
#     bundled config — a fixture gap, not a harness gap.
