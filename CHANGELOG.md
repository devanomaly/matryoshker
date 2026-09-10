# Changelog

All notable changes to this project are documented in this file.

## [Unreleased]

### Added

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
