# Contributing

Matryoshker takes two kinds of contribution — and the second is as important as the
first: **code** (viewer/pipeline) and **data** (use-cases, status blessings, repo
configs). Keeping the team's shared mental model current depends on anyone being able to
feed in new use-cases and bless the existing ones.

## Contributing DATA

### Adding a use-case

Edit `data/<repo>/usecases.json` (`examples/sample-drf/usecases.json` for the bundled
fixture) and add an entry:

```json
{
  "name": "Member borrows a copy of a title",
  "actor": "Library member",
  "goal": "one sentence",
  "entry_points": [
    "http: catalog/views.py:BookViewSet — POST /api/books/{id}/borrow"
  ],
  "hops": [
    "catalog/views.py:BookViewSet.borrow — reads the member id and asks for a free copy (role, <=14 words)",
    "lending/services/loan_service.py:LoanService.checkout — the central rule of the flow"
  ],
  "async_legs": [], "failure_paths": [], "rules": [], "tests": [],
  "seam_crossing": false,
  "status": "inferred"
}
```

#### Hop grammar

```
"<path/file.ext>[:<Symbol>] — <role>"
```

In **execution order**, separator is the em dash (` — `; ` - ` and ` – ` are also
accepted, but standardize on the em dash), symbol should exist in the file (prefer
`Class.method` over a bare line number).

#### Entry-point grammar

```
"[<kind>: ][<label> ]<path/file.ext>[:<Symbol>][ — <text>]"
```

`<kind>` is one of `http`, `command`, `event`, `cli`, `cron`, `other` (case-insensitive);
omit it and the kind defaults to `other`. Examples:

```
"http: POST /v1/books (src/api/views.py:BookViewSet)"
"command: src/domain/commands.py:RegisterBook — register"
"src/jobs/nightly.py:rebuild_index"
```

Use `entry_points` when a use-case genuinely starts somewhere specific (a route, a
command, a scheduled job); leave it empty and the **first resolved hop** becomes a
fallback entry point automatically (`docs/data-contract.md`, section 6.2) — this is the
normal path for a DDD-first registry with no routes yet.

#### What `prep_data.py` checks — and what it does not

- It resolves the hop's **file** against the graph. A hop whose file does not resolve is
  dropped, and the tool prints the hop and the reason on stderr (file not found, or the
  file name is ambiguous), plus a per-use-case summary `N/M hops resolved`. Read the
  stderr: **the exit code is 0 even when every hop of a use-case was dropped**, so "it
  ran without error" proves nothing — what matters is that `hops=` in the final line
  matches what you wrote.
- It checks the symbol after the colon only as a **warning** (`unverified symbol [...]`
  on stderr) — it does not drop the hop. `file.py:MethodThatDoesNotExist` still resolves,
  still counts toward the total, and still shows up on the map as if it were real. Double
  check the symbol yourself, in the file.
- With none of the accepted separators, the whole line becomes the citation and **the
  role disappears without a warning**. With a separator, the role is truncated at 140
  characters.

Of the fields above, the pipeline reads `name`, `actor`, `goal`, `entry_points`, `hops`,
`rules`, `seam_crossing` and `status` (section 4.1 of `docs/data-contract.md`). The rest
(`async_legs`, `failure_paths`, `tests`, and any extra key such as `notes` or
`preconditions`) are versioned documentation for humans and agents — worth the effort,
but the map does not render them.

### Epistemic status (the rule that is not negotiable)

- A new use-case written by a human without a full re-read: `inferred`.
- A use-case structured or checked by an agent pipeline: **at most** `agent-verified`.
- **`human-verified` only enters when a human has re-read the hops and blesses them —
  never by an agent, never as a default.**
- Found a use-case the code now contradicts? Mark it `outdated` in the PR (do not delete
  it — the divergence itself is information).

The v1 Portuguese status values (`verificado-humano`, `verificado-agente`, `inferido`,
`hipotese`, `desatualizado`) are still accepted as aliases and mapped silently to the
canonical English values above; new entries should use the English values directly.

In the viewer, the status dropdown in the use-case panel is a local draft
(`localStorage`, shown with `· local`); *export local statuses* opens the JSON
`{"<use-case name>": "<status>"}` snippet of your local changes to apply to the registry
via a PR. The versioned registry file is the only collective source of truth.

### Adding a new repo

`config/<repo>.json` (copy `config/example.json` or `config/example-ddd.json`) +
`data/<repo>/usecases.json` (may start empty: `[]`). See `docs/data-contract.md` sections
3 and 4 for every key, and `schemas/config.schema.json` /
`schemas/usecases.schema.json` for editor validation.

## Contributing CODE

### Viewer (`viewer/template.html`)

- One single file, **zero external dependencies** (the only tolerated exception is the
  Google Fonts `<link>`; nothing else, no CDN — the artifact CSP forbids it). No
  framework: vanilla SVG + DOM.
- Themes: every color goes through CSS tokens defined in the three theme blocks
  (`:root` light, the guarded `prefers-color-scheme: dark` media query, and
  `:root[data-theme="dark"]`). A color defined in only one block is a bug.
- Category palette: the slot colors were validated (color-vision-deficiency and contrast)
  in both themes — do not change a hex value without revalidating.
- Data arrives through the `__MATRYOSHKER_DATA__` placeholder (the injection point's
  stable internal name — never rename it: `inject.py` aborts if it is missing); the
  viewer knows nothing about any specific repo.
- Repo-specific logic inside the viewer is a defect. It belongs in `config/` or `data/`.
- Layout is deterministic: it may read only the embedded data and the layout constants —
  never the viewport, the clock, randomness, or measured text (`getComputedTextLength`).
  Estimate text width from the character count instead; the saved drag offsets are deltas
  over the base positions and are keyed per commit. The block between the
  `// --- pure layout geometry` markers must stay free of DOM and globals: a test extracts
  it and runs it under node (`tests/test_e2e.py`).

### Pipeline (`pipeline/*.py`)

- Pure Python standard library, 3.10+, no third-party runtime dependency ever. CLIs use
  `argparse`. Scripts never write into the target repo — everything goes under `--out`
  or `--extract-out`.
- Every script keeps the
  `try: from _common import ... except ImportError: from pipeline._common import ...`
  pattern so both `python pipeline/x.py` and `python -m pipeline.x` work.
- All text — identifiers, docstrings, comments, CLI messages — is English.

### Adding an entry-point parser

1. Add a module `pipeline/entry_points/<name>.py` exporting
   `parse(files, class_file, options) -> list[dict]` (see `docs/data-contract.md`,
   section 6.3, for the exact contract: what `files`, `class_file` and `options` are, and
   the shape of each returned `{"label", "kind", "path", "symbol"}`).
2. Register it in `pipeline/entry_points/__init__.py`'s `PARSERS` dict.
3. Have the parser ignore options it does not recognize, with a
   `warning: parser <name>: unknown option "<key>"` on stderr, and report what it could
   not map as `parser <name> (<file>): dropped [<reason>]: <what>`.
   Return one of the six declared kinds (`http`, `command`, `event`, `cli`, `cron`,
   `other`); `prep_extra.py` warns and coerces anything else to `other`, because the
   viewer renders only those six groups.
4. Add fixtures and tests under `tests/` exercising the parser against a small sample
   file (see the existing `django-drf` tests for the shape).
5. Document the new parser's config keys in `docs/data-contract.md` if you're proposing a
   contract change, or in the module docstring otherwise.

### Pre-PR checklist

0. Install the test dependency once: `pip install pytest` (the pipeline itself stays
   pure standard library; pytest is only needed to run the suite).
1. Run the test suite: `python -m pytest -q` (the root `pytest.ini` points it at
   `tests/` and keeps it out of `examples/`, which is a fixture, not a test target).
2. Build the fixture and check the generated `<script>` parses as JavaScript:

   ```bash
   python pipeline/build.py --repo examples/sample-drf --config config/example.json \
       --ucs examples/sample-drf/usecases.json --out matryoshker.html --lang python
   python -c "import re;h=open('matryoshker.html',encoding='utf-8').read();open('check.js','w',encoding='utf-8').write(re.findall(r'<script>(.*?)</script>',h,re.S)[-1])"
   node --check check.js
   ```

3. Open the HTML and walk through the four scenes — Context, Packages, double-click a
   file for Symbols, and Flow (only visible with a use-case or entry point active) — in
   both themes (light/dark follows the host environment; toggle your system/browser
   preference, or force `data-theme="dark"` / `data-theme="light"` on `<html>` via
   devtools) and, if you touched anything in `UI_STRINGS`, in both languages
   (`config.lang`: `en` and `pt-BR`).
4. Use-case overlay: select a use-case, check the badges/arrows, and that Esc goes up one
   level at a time until the selection clears.
5. Click a file from the overlay and check the *Use-cases passing here* block (the
   reverse index) — it is what breaks first when a hop → file link changes.

Small, single-purpose PRs. Describe what changes for the map's user, not only what
changes in the code.
