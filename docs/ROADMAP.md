# Roadmap

These are candidate issues, not commitments with a date. Each is independent; pick
whichever is interesting and open an issue to discuss the approach before a large PR.

## 1. Use-case composer in the viewer

Today, adding a use-case means hand-editing `data/<repo>/usecases.json` and hoping the
hop citations resolve (see `CONTRIBUTING.md` and `docs/data-contract.md` section 5). A
guided form inside the viewer — name/actor/goal/status, hops built by autocomplete over
the graph itself (so a `file:Symbol` pair is validated the moment it is chosen, not after
a `prep_data.py` run) — would remove the unverified-symbol problem at the source and turn
registry authoring into a UI flow. The output would still be a JSON snippet meant for a
PR against the versioned registry; the viewer never writes it directly (section 4 of the
data contract: "the viewer never writes it").

## 2. CI freshness gate for the registries

A CI job that re-resolves every hop and entry-point citation in `data/<repo>/usecases.json`
against a fresh extraction of the target repo, and fails the PR when a citation that used
to resolve no longer does (a renamed file, a removed symbol previously verified only by
convention). This is deliberately separate from the base pipeline: `prep_data.py` and
`prep_extra.py` never fail on a dropped citation by default (exit code 0, `--strict`
opts in — section 11 of the data contract) because a partially-stale registry should
still render; a freshness gate is a stricter, opt-in check for repos that want it enforced
on every PR.

## 3. Per-branch generation in CI

`.github/workflows/pages.yml` builds one map (the `main` branch of the bundled fixture)
on every push. Building and hosting one map per branch or per PR — a real
branch-preview workflow — would let reviewers see the map reflect the change being
reviewed, not just what already landed on `main`.

## 4. More entry-point parsers

The only bundled parser is `django-drf` (`pipeline/entry_points/django_drf.py`), covering
`router.register(...)` and `path(..., X.as_view())`. Function-based Django views,
`include()`, and other frameworks entirely (FastAPI, Flask, Express, Rails routes, ...)
are all open. See `docs/data-contract.md` section 6.3 for the parser interface
(`parse(files, class_file, options) -> list[dict]`) and
`.github/ISSUE_TEMPLATE/new-entry-point-parser.md` for what a proposal should include.
