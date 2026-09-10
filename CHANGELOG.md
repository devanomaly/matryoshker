# Changelog

All notable changes to this project are documented in this file.

## [Unreleased]

### Added

- **Visual review harness** (`tools/visual_review.py`): one command builds the bundled
  fixture with both bundled configs and drives the result in a real browser, writing a
  PNG per named state (14 states across light/dark, `config/example.json` /
  `config/example-ddd.json` and `en` / `pt-BR`) plus a machine-readable `metrics.json`
  and a Markdown `report.md`. `visual_review.py diff` renders the before/after table of
  what a change moved, which is what a pull request should quote. Playwright is a
  development-only dependency, now declared in `requirements-dev.txt`; `pipeline/`, the
  viewer and the pytest suite are unaffected.

- **CI** (`.github/workflows/ci.yml`): a `visual review (ubuntu)` job builds both demo
  maps from the committed golden extraction (no Node), writes the metrics table into the
  run's job summary and uploads the HTML, screenshots and metrics as a workflow
  artifact. It needs no permissions beyond the existing `contents: read`, writes only
  under the runner's temp directory, and carries a 20-minute timeout.

- **Hop fan-out in the Flow scene** (#9). A hop whose role opens with `branch:` / `ramo:`
  is a *sibling* — one of N alternatives chosen at the preceding hop — not a step after
  it. A consecutive run of them now occupies one level, drawn side by side between its
  selector and its reconvergence, with edges as the cartesian product between consecutive
  levels. **Numbering is by level**: the siblings are labeled `Na`, `Nb`, `Nc`. The map
  overlay applies the same grouping.

- **`ucs[].hops[].k`** in `data.json`: `"branch"` or `"seam"`, derived from the role
  prefix (`branch:`/`ramo:`, `seam:`/`costura:`, matched case-insensitively and only at
  the start of the role) and **omitted** when there is none, so the prefix vocabulary
  lives in `pipeline/usecases.py` alone and the viewer never re-parses role text.
  Documented in data-contract §5.1 and §7.4.

- A `seam:` / `costura:` hop's *incoming* edges are drawn dashed; fan edges stay solid,
  and the two compose.

### Fixed

- **The Flow scene now follows the selection you made last.** With a use-case
  active, choosing an entry point (or *call tree from here* in the Symbols scene) updated
  the crumb, the detail panel and the sidebar highlight while Flow kept drawing the
  use-case chain. The use-case overlay and the entry-point lens still coexist everywhere
  else — Context keeps its documented lens precedence — and clearing one makes Flow fall
  back to the other. Clicking an entry point while the Flow scene is open now redraws Flow
  in place instead of jumping to Packages, and a new Flow source refits the view. See
  `docs/data-contract.md` section 13.4.

- **A route parser no longer erases a hand-written entry-point label.** Entry points that
  land on the same file and symbol are now merged instead of collapsed onto the first
  source: the label declared by a use-case wins over the one a parser generated, the
  parser's route is kept in the new `route` field, and the new `ucs` field lists the
  use-cases that enter there. The entry-points panel shows both, and the entry-point
  detail links to each use-case. `meta.contract` stays `2` (see
  `docs/data-contract.md` section 15.1).

- **Stars panel**: a file now needs at least one use-case, one inbound import or one inbound
  call to be listed; the list is no longer padded to 20 with all-zero files, and the badge
  counts what is shown. Rows whose base name repeats show their parent folder. When nothing
  qualifies the panel says so instead of showing an empty box, and a long label wraps
  inside its row instead of overflowing the panel.

- **Entry points panel** starts expanded when the map has entry points (it stays completely
  hidden when it has none).

- **Docs**: README, QUICKSTART, CONTRIBUTING and their Portuguese mirrors under
  `docs/pt-BR/` now state that the generated page makes exactly one external request — the
  Google Fonts `<link>` — and works fully without it.

- **The generated HTML declares its character encoding.** `viewer/template.html` carried
  no `<meta charset>`, while a generated map carries hundreds of non-ASCII bytes — the
  middle-dot separator, em dashes, ellipses, arrows and every accented character of the
  pt-BR `UI_STRINGS` table. A browser therefore had to guess the encoding. Served over
  HTTP without a `charset` in the `Content-Type` — which `QUICKSTART.md` documents as a
  supported way to publish a map — Chromium falls back to windows-1252 and the whole UI
  renders as mojibake (`pan Â· drag`); opened from `file://` the guess is usually right
  but not reliably so. The declaration is now the first line of the template, inside the
  1024-byte window a browser prescans.

- **Packages scene used a sliver of the canvas and its cluster labels overlapped.** The
  clusters were shelf-packed against a hardcoded 1500-unit width, so a typical repo
  produced a single horizontal row (the bundled demo measured 832 × 79 world units,
  a 10.5:1 strip), and the cluster label was drawn with no width constraint, running
  over the neighbouring cluster's label (up to 47px on the bundled demo). Clusters are
  now packed into a compact grid whose shelf width is derived from the packed content
  (total area × a target aspect ratio), each box is as wide as the wider of its node
  grid and its label, and a label that still does not fit is clipped with an ellipsis
  and carries the full name as a tooltip. The bundled demo now measures 464 × 340
  (1.37:1) with no overlap; a synthetic 457-file, 41-cluster repository measures 1.24:1
  instead of 3.41:1, with its worst label overrun down from 122px to zero.

- **Context scene** was packed against its own hardcoded 900-unit width (a 4.8:1 strip
  for the demo, a 0.5:1 column for a large repo); it now uses the same content-derived
  packing (1.66:1 and 1.38:1 respectively) and sizes its boxes with the same
  deterministic text estimate, which also keeps localized file counts and long or East
  Asian folder names clear of the hide-folder `×`.

### Notes

- **Backward compatible.** The registry format is unchanged and the prefix stays verbatim
  inside `r`. A registry that uses no role prefixes emits no `k`, keeps its `1..N`
  numbering, and produces a byte-identical `data.json`.

- The use-case detail panel is deliberately unchanged: it lists the registry's own lines
  in JSON order, prefix visible, which is what an author needs when correcting the file.

- Known limitations of this version are listed in data-contract §5.1: no nesting; two
  independent adjacent lateral alternatives merge into one fan of two; a sibling that
  terminates mid-chain is still drawn reconverging; the file-level map overlay cannot
  show a fan whose siblings live in the selector's own file.

- **Existing maps: cluster base positions changed.** Cluster base positions changed, so a saved arrangement (`mtk:<repo>@<commit>:pos`, kept
  per commit) will appear moved on an existing map. Node dragging, the per-use-case
  Packages arrangement, the hidden-folder list and the status drafts are unaffected and
  their `localStorage` keys are unchanged.

## [1.4.0] - 2026-09-05

First public release.

This release brings the internal v1.3 pipeline to the v2 data contract
(`docs/data-contract.md`) for open-source use:

- **Entry points**: a repo-agnostic entry-point model (`http`, `command`, `event`,
  `cli`, `cron`, `other`) replaces the v1 Django-only `endpoints` key. Entry points can
  come from a configured route parser, from a use-case's declared `entry_points`, or —
  when a use-case declares none — as a fallback derived from its first resolved hop.
- **`pipeline/entry_points/`**: a small parser registry (`get_parser`,
  `merge_entry_points`) with one bundled parser, `django-drf`, replacing the hardcoded
  `--urls` flag and `/v1/` route prefix.
- **English data-model keys, with v1 Portuguese aliases accepted**: `name`/`actor`/
  `goal`/`rules` (aliases `nome`/`ator`/`objetivo`/`regras_envolvidas`); canonical status
  values `human-verified`/`agent-verified`/`inferred`/`hypothesis`/`outdated` (aliases
  `verificado-humano`/`verificado-agente`/`inferido`/`hipotese`/`desatualizado`).
  Existing v1 registries keep working unchanged.
- **`pipeline/build.py`**: a single-command orchestrator for the whole pipeline
  (extract → prep_data → prep_extra → inject), with `--strict` support and per-step
  stderr announcements.
- **`config.lang`**: the viewer's UI language is now a config field (`en` default,
  `pt-BR` also supported) instead of being hardcoded.
- **`config.hop_path_prefixes`**: citation-resolution prefixes are now configurable per
  repo instead of hardcoded (`v1/`, `src/`) in `prep_data.py`.
- **JSON Schemas** (`schemas/config.schema.json`, `schemas/usecases.schema.json`,
  draft-07) for editor support and CI validation, kept in sync with the data contract.
- **Test suite** (`tests/`): unit tests for the config/use-case loaders, citation
  parsing, entry-point merging and the `django-drf` parser, plus an end-to-end test that
  runs the whole pipeline against a bundled fixture and checks the embedded object.
- **CI** (`.github/workflows/ci.yml`): the test suite runs on Python 3.10 and 3.12, on
  Ubuntu and Windows, on every push and pull request.
- **Public fixture** (`examples/sample-drf/`): a small Django/DRF library-lending app
  with a matching `usecases.json` at every epistemic status, replacing the internal
  target repo used during development. `.github/workflows/pages.yml` builds this
  fixture and publishes it to GitHub Pages.
- Documentation rewritten in English (`README.md`, `QUICKSTART.md`, `CONTRIBUTING.md`);
  the v1.3 Portuguese originals are kept as a snapshot under `docs/pt-BR/`.

See `docs/data-contract.md` section 15 for the complete v1.3 → v2 migration checklist.
