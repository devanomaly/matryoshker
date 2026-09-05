# Quickstart

Prerequisites: Python 3.10+, Node 22+, git. Tested in CI on Linux and Windows (Git
Bash); macOS is expected to behave like Linux. The scripts warn on stderr when the
interpreter is older than 3.10.

Running the test suite additionally needs pytest (`pip install pytest`); the pipeline
itself has no third-party dependency.

On Windows, `python` may resolve to an old install (the Microsoft Store shim, or an
earlier entry in `PATH`) even with 3.12 also installed — check with `python --version`,
or call `py -3` instead.

## 0. Install the extractor's dependencies (once)

```bash
cd extractor
npm ci --ignore-scripts
cd ..
```

This installs the vendored, lockfile-pinned tree-sitter grammars. It is the only step
that touches the network; extraction itself runs 100% locally afterwards.

## One-command build

```bash
python pipeline/build.py --repo <path to the target repo> --config config/<repo>.json \
    [--ucs data/<repo>/usecases.json] --out matryoshker.html [--lang <language>]
```

Runs the four steps below in order, stopping (with the same exit code) at whichever step
fails; nothing is written to `--out` unless all four succeed. `--lang` filters the
extractor to one source language (e.g. `python`) — it is unrelated to the config's
`lang` field, which selects the viewer's UI language. Try it against the bundled
fixture:

```bash
python pipeline/build.py --repo examples/sample-drf --config config/example.json \
    --ucs examples/sample-drf/usecases.json --out matryoshker.html --lang python
```

## The four steps, standalone

Each step also works on its own — useful when iterating on one stage without re-running
extraction.

### 1. Extraction (vendored extractor)

```bash
node extractor/extract.mjs <path to the target repo> --out out/ \
    --exclude "dist/*" --lang python
```

Writes `scan-output.json`, `im-output.json`, `es-output.json` (plus intermediates, for
debugging) into `out/`. `--lang` filters by language (omit it for all languages the
vendored grammars cover); `--exclude` takes comma-separated gitignore-style patterns.
Nothing is written into the target repo.

### 2. Repo config

Copy `config/example.json` (route parser included) or `config/example-ddd.json` (no
route parser — entry points come from the use-case registry) and adjust `repo`,
`commit`, `date`, `categories` and `rules` (path prefix → category; the first six
non-`gray` categories get the palette colors; `muted` categories start hidden, with a
toggle in the header). `fallback_category`, `test_path_marker` and `test_category` cover
whatever the rules miss.

#### Discovering `categories` and `rules`

Primary path — let the scan draft it for you:

```bash
python pipeline/suggest_config.py --scan out/scan-output.json --repo my-repo \
    --out config/my-repo.json
```

It groups the top-level directories by file count (descending into the second level when
the top is a single monolith folder like `app/`, `src/` or `v1/`), emits categories in
that order — the first six colored, `test`/`tests`/`spec` folders already `gray`+`muted`
— and prints a `dir | files | language` table on stderr. This is a **draft**: review the
table for categories to merge or rename (a folder name is not an architectural role),
confirm that directories with no rule really belong in `other`, and fill in `commit`
(emitted as `ADJUST`) and `date`.

Manual fallback, if you would rather write it by hand:

1. list the repo's top-level folders (and second-level ones, if everything lives under a
   single folder);
2. group by role, not by name — six colored categories is the useful ceiling, everything
   else goes to `other`;
3. mark test folders `gray` + `muted`.

### 3. Compose the data

```bash
python pipeline/prep_data.py --es out/es-output.json --imports out/im-output.json \
    --config config/my-repo.json --ucs data/my-repo/usecases.json --out out/data.json
python pipeline/prep_extra.py --es out/es-output.json --imports out/im-output.json \
    --config config/my-repo.json --ucs data/my-repo/usecases.json \
    --repo <path to the target repo> --out out/extra.json
```

`--ucs` is optional in both; without it `prep_data.py` writes `ucs=[]` and
`prep_extra.py` only runs the configured route parsers (if any). `--repo` is only
required when a parser in `entry_points.parsers` declares `files`.

### 4. Inject into the viewer

```bash
python pipeline/inject.py --template viewer/template.html --data out/data.json \
    --extra out/extra.json --out matryoshker.html
```

`--extra` is optional too — without it the embedded object still gets empty
`entry_points`/`calls`.

## Reading the counters and stderr

Each script prints one summary line on stdout when it succeeds:

- `prep_data.py`: `files=N imports=N ucs=N hops=N -> <out> (NKB)` — `hops` counts
  **resolved** hops only.
- `prep_extra.py`: `entry_points=N calls: internal=N cross=N -> <out> (NKB)`, plus (when
  entry points exist) a breakdown line `entry points: <a> from parsers, <b> declared,
  <c> fallback, <d> duplicates merged`.
- `inject.py`: `<out>: NKB`.

A `hops=` count lower than what the registry declares means some hop's **file** did not
resolve against the graph. `prep_data.py` reports each dropped hop and each unverified
symbol on stderr, per use-case, and still exits 0 — the exit code alone never proves the
registry is fully wired to the graph; read the stderr, or pass `--strict` to
`prep_data.py`/`prep_extra.py`/`build.py` to turn any drop into exit code 3. See
[CONTRIBUTING.md](CONTRIBUTING.md) for the citation grammar these scripts parse.

`prep_extra.py` reports parser drops the same way
(`parser <name> (<file>): dropped [<reason>]: <what>`) and `entry_points=0` is the
expected result whenever no parser is configured (the DDD-first path) or the target repo
is not Django/DRF — not an error on its own.

## Open the result

`matryoshker.html` is self-contained — open it in a browser, serve it statically, or
publish it as a Claude Artifact. No server, no network, no keys required at runtime.

It opens in **Packages**; *Context* goes up one level, double-clicking a file goes down
to **Symbols**, and **Flow** appears in the breadcrumb once a use-case or entry point is
active. Esc goes up one level. The theme follows the host environment (system
preference, or the host's `data-theme`). Node layouts and status drafts live in
`localStorage`, per commit and per browser.

No use-case registry yet? Omit `--ucs` — the map, the symbols and any configured route
parsers still work; the use-cases panel stays empty until the first
`data/<repo>/usecases.json` exists (see [CONTRIBUTING.md](CONTRIBUTING.md) to seed one).
