## What changes for the map's user

<!-- One or two sentences: what does someone reading a generated matryoshker.html see
     differently, or what does someone editing a config/usecases file get differently?
     Not a restatement of the diff — the effect of the diff. -->

## What kind of change

- [ ] Code: viewer (`viewer/template.html`)
- [ ] Code: pipeline (`pipeline/`, `extractor/`)
- [ ] Data: use-case registry (`data/`, `examples/`)
- [ ] Data: repo config (`config/`)
- [ ] Docs (`README.md`, `QUICKSTART.md`, `CONTRIBUTING.md`, `docs/`)
- [ ] Other

## Checklist

- [ ] `python -m pytest -q tests` passes.
- [ ] If `pipeline/` or `viewer/template.html` changed: ran the four-scene manual check
      from `CONTRIBUTING.md` (Context, Packages, Symbols via double-click, Flow via an
      active use-case or entry point) in both themes, and in both languages if
      `UI_STRINGS` changed.
- [ ] If a use-case registry changed: re-ran `prep_data.py` (or `build.py`) and checked
      the `hops=` counter and stderr for `dropped [...]` / `unverified symbol [...]`
      lines against the new entries.
- [ ] If the data contract (`docs/data-contract.md`) is affected: this PR updates it in
      the same change, not as a follow-up.
- [ ] Kept the PR small and single-purpose.
