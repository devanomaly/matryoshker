# Quickstart

Prerequisites: Python 3.10+, Node 22+, git. Tested in CI on Linux and Windows (Git
Bash); macOS is expected to behave like Linux. The scripts warn on stderr when the
interpreter is older than 3.10.

Running the test suite additionally needs pytest (`pip install pytest`); the pipeline
itself has no third-party dependency.

On Windows, `python` may resolve to an old install (the Microsoft Store shim, or an
earlier entry in `PATH`) even with 3.12 also installed — check with `python --version`,
or call `py -3` instead. The commands below say `python`; substitute freely.

## 0. Install the extractor's dependencies (once)

```bash
cd extractor
npm ci --ignore-scripts
cd ..
```

This installs the vendored, lockfile-pinned tree-sitter grammars. It is the only step
that touches the network; extraction itself runs 100% locally afterwards. `build.py`
refuses to start until `extractor/node_modules` exists, with a message saying so.

## 1. Build the bundled sample

```bash
python pipeline/build.py --repo examples/sample-drf --config config/example.json \
    --ucs examples/sample-drf/usecases.json --out matryoshker.html --lang python
```

Expected, on a fresh checkout (the `build.py: step k/4` lines and the extractor's own
summary omitted):

```
files=25 imports=33 ucs=5 hops=33 -> out/data.json (9KB)
entry points: 4 from parsers, 5 declared, 1 fallback, 2 duplicates merged
entry_points=8 calls: internal=49 cross=71 -> out/extra.json (6KB)
matryoshker.html: 97KB
```

Open `matryoshker.html` in a browser (double-click it, or serve the directory
statically). It opens in the **Packages** scene; the README's five-minute tour says what
to click. `config/example-ddd.json` builds the same fixture with no route parser, which
is the shape of a project that has use-cases but no Django/DRF routes.

## 2. Point it at your own repository

The one-command form is:

```bash
python pipeline/build.py --repo <path to the target repo> --config config/<repo>.json \
    [--ucs data/<repo>/usecases.json] --out matryoshker.html [--lang <language>] \
    [--extract-out out] [--exclude "dist/*,build/*"] [--strict]
```

It runs the four steps of section 3 in order, stopping (with the same exit code) at
whichever step fails; nothing is written to `--out` unless all four succeed.

**Output paths you control.** The scripts write only where you point them:

| Flag | Default | What lands there |
|---|---|---|
| `--out` | `matryoshker.html` | the final self-contained HTML |
| `--extract-out` | `out/` **relative to your current directory** | `scan-output.json`, `im-output.json`, `es-output.json`, `data.json`, `extra.json` |

The target repository (`--repo`) is only read. If you run the command from inside the
target repository, or pass paths inside it, the outputs land there — add them to its
`.gitignore` or choose paths elsewhere. This checkout's `.gitignore` already covers
`out/`, `matryoshker*.html` and the JSON intermediates, so running it here is safe.

**`--lang`** filters the *extractor* to one source language (`python`, `typescript`,
`go`…) and is unrelated to the config's `lang` key, which selects the viewer's UI
language (`en` or `pt-BR`). Omit `--lang` to extract every language the vendored
grammars cover: Python, TypeScript/JavaScript, Go, Rust, Java, Kotlin, Scala, C#, C/C++,
PHP, Ruby, Swift and Dart (`extractor/vendor/core/package.json` pins the grammars; a
file in any other language is listed but yields no symbols).
Everything the map shows — files, imports, symbols, use-case hops — is language-neutral;
**call-edge resolution is tuned for Python** (README, *Known limits*), so the Symbols
scene and the call trees are noisier or thinner for the other languages.

### 2a. Start without a use-case registry

Omit `--ucs`. The map, the Symbols scene, the search and any configured route parser
still work; the *Use-cases* panel shows `0`, the *Entry points* panel is absent unless a
parser found routes, and the *Stars* panel ranks files by inbound imports and calls
alone (it says so when nothing qualifies at all). Verified on the fixture: with
`config/example-ddd.json` and no `--ucs` the build prints `ucs=0 hops=0` and
`entry_points=0`, and the map opens with ten starred files and no entry points. This is
the normal first build for a new repository: look at the extracted map, then pick the
first behavior worth explaining.

### 2b. Write the config

Copy `config/example.json` (route parser included) or `config/example-ddd.json` (no
route parser — entry points come from the use-case registry) and adjust `repo`,
`commit`, `date`, `categories` and `rules` (path prefix → category; the first six
non-`gray` categories get the palette colors; `muted` categories start hidden, with a
toggle in the header). `fallback_category`, `test_path_marker` and `test_category` cover
whatever the rules miss. `commit` and `date` are shown verbatim in the header — nothing
reads git, so update them when you rebuild.

Let the scan draft the categories for you:

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
(emitted as `ADJUST`) and `date`. `out/scan-output.json` exists after any build, so run
the build without `--ucs` and without a real config first — or with a minimal
`{"repo": "my-repo"}` — and draft the config from the result.

Manual fallback, if you would rather write it by hand:

1. list the repo's top-level folders (and second-level ones, if everything lives under a
   single folder);
2. group by role, not by name — six colored categories is the useful ceiling, everything
   else goes to `other`;
3. mark test folders `gray` + `muted`.

**Routes.** The only bundled entry-point parser is `django-drf` (`router.register` and
`path(..., X.as_view())`). For any other framework leave `entry_points.parsers` out, as
`config/example-ddd.json` does: entry points then come from the use-case registry
(declared `entry_points`, or the first hop as a fallback). `entry_points=0` on a build
with no parser and no registry is expected, not an error.

### 2c. Add the first use-case later

Create `data/<repo>/usecases.json` containing `[]`, pass it with `--ucs`, and add the
first entry when you have read the code for one behavior.
[docs/first-use-case.md](docs/first-use-case.md) does exactly that on the bundled
fixture, including the build counters to check and what a wrong citation prints;
[CONTRIBUTING.md](CONTRIBUTING.md) has the hop grammar and the status rule. Build with
`--strict` once the registry exists: a hop whose file does not resolve then stops the
build (exit 3) instead of silently drawing a shorter flow.

## 3. The four steps, standalone

Each step also works on its own — useful when iterating on one stage without re-running
extraction (`build.py --skip-extract` reuses the last extraction too).

### 3.1 Extraction (vendored extractor)

```bash
node extractor/extract.mjs <path to the target repo> --out out/ \
    --exclude "dist/*" --lang python
```

Writes `scan-output.json`, `im-output.json`, `es-output.json` (plus intermediates, for
debugging) into `out/`. `--lang` filters by language (omit it for all languages the
vendored grammars cover); `--exclude` takes comma-separated gitignore-style patterns.
The target repository is only read.

### 3.2 Compose the data

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

### 3.3 Inject into the viewer

```bash
python pipeline/inject.py --template viewer/template.html --data out/data.json \
    --extra out/extra.json --out matryoshker.html
```

`--extra` is optional too — without it the embedded object still gets empty
`entry_points`/`calls`.

## 4. Reading the counters and stderr

Each script prints one summary line on stdout when it succeeds:

- `prep_data.py`: `files=N imports=N ucs=N hops=N -> <out> (NKB)` — `hops` counts
  **resolved** hops only.
- `prep_extra.py`: `entry_points=N calls: internal=N cross=N -> <out> (NKB)`, plus (when
  entry points exist) a breakdown line `entry points: <a> from parsers, <b> declared,
  <c> fallback, <d> duplicates merged`. Entry points found by a parser and entry points
  declared by a use-case on the same file and symbol are merged into one: the written
  label wins, the parsed route is kept beside it.
- `inject.py`: `<out>: NKB`.

A `hops=` count lower than what the registry declares means some hop's **file** did not
resolve against the graph. `prep_data.py` reports each dropped hop and each unverified
symbol on stderr, per use-case, and still exits 0 — the exit code alone never proves the
registry is fully wired to the graph; read the stderr, or pass `--strict` to
`prep_data.py`/`prep_extra.py`/`build.py` to turn any **dropped** citation into exit
code 3. An **unverified symbol** (the file resolved, the symbol after the colon is not
declared in it) is a warning only: the hop still counts, still draws, and `--strict`
does not fail on it. See [CONTRIBUTING.md](CONTRIBUTING.md) for the citation grammar
these scripts parse and [docs/first-use-case.md](docs/first-use-case.md) for both
messages as they actually print.

`prep_extra.py` reports parser drops the same way
(`parser <name> (<file>): dropped [<reason>]: <what>`) and `entry_points=0` is the
expected result whenever no parser is configured (the DDD-first path) or the target repo
is not Django/DRF — not an error on its own.

## 5. Open the result

`matryoshker.html` is self-contained — open it in a browser, serve it statically, or
publish it as a Claude Artifact. No server, no build step, no keys required at runtime. The
page makes exactly one external request, the Google Fonts `<link>` in its `<head>`; offline
or behind a CSP that blocks it, the map is fully functional and falls back to the system
fonts.

It opens in **Packages**; *Context* goes up one level, double-clicking a file goes down
to **Symbols**, and **Flow** appears in the breadcrumb once a use-case or entry point is
active. Esc goes up one level. The theme follows the host environment (system
preference, or the host's `data-theme`). Node layouts and status drafts live in
`localStorage`, per commit and per browser; a status draft is not a change to the
registry until its exported snippet is applied to the file and merged.
