---
name: New entry-point parser
about: Propose a parser for a framework other than Django/DRF (see docs/ROADMAP.md item 4)
title: "entry-point parser: <framework>"
labels: enhancement, entry-points
---

## Framework / routing style

<!-- e.g. FastAPI decorators, Flask blueprints, Express routers, Rails config/routes.rb -->

## Route declarations to match

<!-- The one or two source patterns the parser should recognize, with a short code
     sample of each. Compare with pipeline/entry_points/django_drf.py's two regexes
     (router.register(...) and path(..., X.as_view())) for the level of scope a first
     version should aim for — narrow and correct beats broad and approximate. -->

```
<code sample>
```

## Config shape

<!-- The config/<repo>.json entry_points.parsers[n] entry you're proposing, following
     docs/data-contract.md section 6.3: {"name": "...", "files": [...], plus whatever
     options this framework's routing needs (a route_prefix equivalent? something like
     ignore_views?). -->

```json
{ "name": "...", "files": [], "...": "..." }
```

## Output shape

<!-- Confirm each match becomes {"label", "kind", "path", "symbol"} per section 6.3 —
     `path` must be a value taken from `class_file` (or however this framework's
     handlers map to a declaring file), never invented, so prep_extra.py can turn it
     into a file index. -->

## Fixture

<!-- A parser needs a test fixture. Point to an existing file under examples/sample-drf
     you could extend, or describe the small new file(s) you'd add there. -->
