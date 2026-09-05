# Changelog

All notable changes to this project are documented in this file.

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
