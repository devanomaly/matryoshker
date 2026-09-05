# ADR 0001 — Entry points and the v2 data contract

Date: 2026-09-05 · Status: accepted · Supersedes: the v1.3 contract (Portuguese README)

## Context

Matryoshker was validated on one private codebase before going public, and the v1.3
contract still carried that origin:

- The only entry-point concept was the HTTP *endpoint*, produced by a Django/DRF parser
  with a hardcoded `/v1/` route prefix and a hardcoded `Spectacular` skip list. A
  project without `urls.py` — a DDD-first codebase that prototypes use-cases as command
  handlers, application services, event consumers or jobs before any route exists —
  got an empty panel and no call tree at all, although the viewer only ever needed a
  label and a file index.
- Hop citations resolved against hardcoded path prefixes (`v1/`, `src/`).
- Config and registry keys, status values, stderr messages and UI strings were in
  Portuguese; defaults (`outros`, `testes`) too.
- Four scripts had to be run by hand, and the config's `urls_files` key was an
  annotation nobody read.

The public release needs a contract other people can implement fixtures, parsers and
viewers against, in English, without any trace of the original codebase.

## Decision

1. **Entry points replace endpoints.** The embedded object gets
   `entry_points: [{label, kind, i, symbol}]` with `kind` in
   `http | command | event | cli | cron | other`; the `endpoints` key is gone. Three
   optional sources feed it, merged in a fixed order — route parsers from the config,
   entry points declared per use-case with the same citation grammar as hops, and a
   fallback that promotes the first resolved hop of every use-case that declared
   nothing resolvable — deduplicated by `(i, symbol)` (first source wins) and sorted by
   `(kind, label)`. The merge lives in `prep_extra.py`, the only emitter of
   `entry_points`; `prep_data.py` keeps producing `meta/files/imports/ucs`.
2. **Route parsers are a plugin package** (`pipeline/entry_points/`, registry by name,
   `parse(files, class_file, options)`), configured in `config.entry_points.parsers`
   with per-parser `files`, `route_prefix` and `ignore_views`. `django-drf` is the first
   parser; `urls_files` is deprecated and mapped to it with a warning.
3. **Config and registry go English with aliases.** `date` (alias `data`), `lang`
   (`en` | `pt-BR`, drives a `UI_STRINGS` table in the viewer), `hop_path_prefixes`
   (replaces the hardcoded prefixes), defaults `other`/`tests`. Use-case keys
   `name/actor/goal/rules` with the v1 keys accepted transparently; status values
   `human-verified | agent-verified | inferred | hypothesis | outdated` with the v1
   values mapped. The pipeline is lenient (aliases silent, unknown keys warn); the
   JSON Schemas (`schemas/`) are strict for editors and CI.
4. **One command**: `pipeline/build.py` runs extract → prep_data → prep_extra → inject as
   subprocesses, passes the counters through and fails on the first failing step.
   The four scripts stay usable standalone.
5. **Citation parsing is made robust without changing the grammar**: the citation may
   appear anywhere in the line, the first candidate that resolves wins, the role is
   kept even without a separator, and a hop whose symbol is not declared in the file
   gets a warning (still no drop). `--strict` turns drops into exit code 3 for CI.

The complete reference is `docs/data-contract.md`.

## Consequences

- The viewer gains a generic "Entry points" panel grouped by kind (hidden when empty),
  a call tree and a Context lens launchable from any entry point, and a "call tree from
  here" launcher for any file/symbol — with no framework knowledge inside it.
- Projects without HTTP routes get a useful map from day one: every documented
  use-case yields an entry point through the fallback source.
- Existing v1 configs and registries keep working (aliases), but generated
  `data.json`/`extra.json` are **not** backward compatible: the viewer and the pipeline
  must be updated together, which `inject.py` already forces by design.
- `prep_extra.py` re-resolves hops (silently) to compute the fallback source; the cost
  is negligible and keeps every script standalone instead of chaining outputs.
- Two use-cases starting at the same file and symbol share one fallback entry point,
  labelled with the first use-case's name — a documented, deliberate simplification.
- Adding a framework means adding one module under `pipeline/entry_points/` and one
  registry line; nothing else changes.
- Fixtures, tests and docs can be written against the schemas and this contract
  without any reference to the private codebase the tool was first validated on.
