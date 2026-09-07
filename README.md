# Matryoshker

A navigable code map in nested levels — like matryoshka dolls — with semantic overlays
that no off-the-shelf tool offers: **use-cases** and **entry points** projected onto a
graph extracted deterministically from the repository.

Repo-agnostic by construction: every piece of repo-specific knowledge (categories,
classification rules, routes) lives in `config/` and `data/`, never in the viewer code.

## Why

A round of prior-art scans showed that the combination *automatically extracted graph ×
adjustable granularity × persistent use-case and flow overlays* does not exist in a live
tool — the pieces exist separately (Sourcetrail, CodeScene, AppMap, Understand-Anything),
and the product that came closest (CodeSee) shut down in 2024. The pattern in this
category: standalone products die; **formats and open primitives outlive them**.
Matryoshker is a thin curation and visualization layer over such primitives.

## What the viewer offers

| Scene | C4 level | What it shows |
|---|---|---|
| **Context** | C1 | packages as boxes + aggregated import edges (thickness = import count); the entry-point lens dims what a depth-2 BFS does not reach |
| **Packages** | C2 | every file in package clusters, colored by category |
| **Symbols** | C3–C4 | double-click a file: classes/functions as pills + internal and cross-file calls as edges |
| **Flow** | — | only appears with a use-case or entry point active: UC → numbered vertical chain of hops; entry point → top-down call tree |

More:

- use-case overlay on the map (dim + numbered badges + arrows in hop order);
- an entry points panel in the sidebar (HTTP routes, commands, events, CLI, scheduled
  jobs) and a `entry point: … ×` crumb to clear the lens;
- a reverse index **file → use-cases**: clicking a file lists the UCs that pass through
  it (linked by file, not by route) and jumps back to each one;
- a status dropdown in the UC panel (local draft, see below);
- search by file/class/method and a toggle to reveal `muted` categories (tests, hidden
  by default);
- Obsidian-style node dragging: Context and Symbols always, Packages only with an active
  UC. Layout is saved to `localStorage` per commit — **per UC** in Packages, per scene
  elsewhere;
- light/dark following the host environment (system or the host's `data-theme`; the
  viewer has no theme switch of its own);

all in a single self-contained HTML file (CSP-safe, no external dependencies besides the
Google Fonts `<link>`). That `<link>` is the page's only network request: block it, or
open the file offline, and the map still works in full — only the typefaces fall back to
the system stack.

## 60-second demo

```bash
cd extractor && npm ci --ignore-scripts && cd ..
python pipeline/build.py \
    --repo examples/sample-drf --config config/example.json \
    --ucs examples/sample-drf/usecases.json --out matryoshker.html --lang python
```

Open `matryoshker.html` in a browser. It maps the bundled `examples/sample-drf` fixture
(a small Django/DRF library app) with its `data/`-free companion registry
`examples/sample-drf/usecases.json` — a handful of use-cases at every epistemic status.

`.github/workflows/pages.yml` builds the same fixture on every push to `main` and can
publish it to GitHub Pages; enable Pages for the repository (Settings → Pages → source
"GitHub Actions") to get a hosted demo.

### The DDD-first path

`config/example-ddd.json` builds the same fixture without any route parser
(`entry_points.parsers` is absent). Entry points then come entirely from the use-case
registry: each use-case's declared `entry_points` (an HTTP route, a command, an event…)
or, absent that, its first resolved hop as a fallback (section 6 of the data contract).
This is the path for projects that write use-cases before routes exist, or that never
expose HTTP at all:

```bash
python pipeline/build.py \
    --repo examples/sample-drf --config config/example-ddd.json \
    --ucs examples/sample-drf/usecases.json --out matryoshker-ddd.html --lang python
```

See [QUICKSTART.md](QUICKSTART.md) for the full walkthrough and
[CONTRIBUTING.md](CONTRIBUTING.md) for contributing code **or data** (new use-cases,
status blessings).

## Pipeline

```
target repo (read-only)
  └─ extractor/extract.mjs   (vendored derivative of Understand-Anything: tree-sitter,
       offline, no LLM, one command — see extractor/NOTICE)
  └─ pipeline/prep_data.py   (repo config + versioned use-case registry)
  └─ pipeline/prep_extra.py  (entry points + resolved call edges)
  └─ pipeline/inject.py      (data embedded into viewer/template.html)
  → matryoshker.html (self-contained; open in a browser or publish as an artifact)
```

`pipeline/build.py` runs all four steps with one command. `pipeline/suggest_config.py` is
the optional shortcut for a repo's first `config/<repo>.json`: it groups
`scan-output.json`'s directories by file count and emits a **draft** `categories`/`rules`
block to review.

## Epistemic status tags

Every use-case carries a **versioned** `status` in the data file:

`human-verified` · `agent-verified` · `inferred` · `hypothesis` · `outdated`

Hard rule: **`human-verified` only enters by human gesture** — agent pipelines stop at
`agent-verified`. In the viewer, the status dropdown in the UC panel changes a local
draft (`localStorage`, marked `· local`); the *export local statuses* button opens the
JSON `{use-case name: status}` snippet to make it official in the versioned registry via
a PR. The repository is always the source of truth.

## Data contract

Every file format, CLI flag and module boundary in the pipeline is specified in
[docs/data-contract.md](docs/data-contract.md) — read it before writing a config, a
use-case registry, or an entry-point parser. The JSON Schemas in
[schemas/](schemas/) (`config.schema.json`, `usecases.schema.json`) exist for editor
support and for CI jobs that choose to install a validator; the pipeline itself has no
schema-validator dependency.

## Known limits

- The only bundled entry-point parser is Django/DRF-specific
  (`router.register` + `path(...as_view)`); other frameworks need a new parser
  (section 6.3 of the data contract).
- Extraction requires Node 22+; the extractor is vendored under `extractor/` (a minimal
  derivative of Understand-Anything's phase-1, MIT, commit pinned in `extractor/NOTICE`
  — no external clone, no TypeScript build step at use time).
- Call edges are resolved by name heuristics (same file → imports); dynamic or
  reflective calls do not appear.
- Call-edge resolution is tuned for Python: the skipped-names list is Python builtins and
  exceptions, and `self` is the only receiver stripped from a call expression. For the
  other languages the extractor parses, edges are noisier (their builtins are not
  skipped) or thinner (`this.method()` resolves on `this`). Files, imports, symbols and
  use-case hops are language-neutral; only the call edges carry this bias (section 8 of
  the data contract).
- A map published as a static artifact (e.g. a Claude Artifact) is a snapshot: keeping it
  fresh per branch requires generating the HTML in CI and hosting it, which is on the
  roadmap.

## Roadmap

1. A use-case composer inside the viewer: a guided form (name/actor/goal/status) with
   hops built by **autocomplete over the graph itself** (file:symbol validated at
   selection time — this removes the unverified-symbol problem at the source), producing
   a JSON snippet ready for a PR against the registry.
2. A CI freshness gate for the registries (hops/citations re-resolved against the graph
   on every PR).
3. Per-branch generation in CI (real branch-preview builds).
4. Entry-point parsers for more frameworks.

See [docs/ROADMAP.md](docs/ROADMAP.md) for these as candidate issues.

## Attribution

The extractor (`extractor/`) is a minimal derivative of the phase-1 (deterministic
structural extraction) portion of
[Understand-Anything](https://github.com/Egonex-AI/Understand-Anything) by Egonex-AI,
licensed under MIT. Full provenance, the files that are byte-identical to upstream, and
the re-vendoring procedure are in [extractor/NOTICE](extractor/NOTICE).

## License

MIT — see [LICENSE](LICENSE).
