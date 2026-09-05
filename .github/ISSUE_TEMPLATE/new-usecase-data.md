---
name: New or updated use-case
about: Propose a use-case to add, correct, or re-bless in a usecases.json registry
title: ""
labels: data
---

## Registry file

<!-- e.g. examples/sample-drf/usecases.json, or data/<repo>/usecases.json -->

## Use-case

```json
{
  "name": "",
  "actor": "",
  "goal": "",
  "entry_points": [],
  "hops": [],
  "rules": [],
  "seam_crossing": false,
  "status": "inferred"
}
```

See `CONTRIBUTING.md` for the hop grammar (`path/file.ext[:Symbol] — role`), the
entry-point grammar (`[kind: ][label ]path/file.ext[:Symbol][ — text]`), and the status
rule: **`human-verified` only by a human who re-read the hops** — never by an agent,
never as a default.

## What this is (pick one)

- [ ] A brand-new use-case
- [ ] Correcting hops/entry points on an existing use-case (paste the current `name`)
- [ ] Blessing an existing use-case's status (`inferred`/`agent-verified` → `human-verified`,
      or marking it `outdated`)

## Verification

<!-- Did you run pipeline/prep_data.py (or pipeline/build.py) and check the "hops=N"
     count and stderr for "dropped"/"unverified symbol" lines against this registry?
     Paste the relevant summary line here. -->
