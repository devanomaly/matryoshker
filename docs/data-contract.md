# Matryoshker data contract — v2

This document is the complete reference for every file format, CLI and module that
makes up the Matryoshker pipeline, and for the JSON object the viewer reads. Other
parts of the project (pipeline code, viewer code, fixtures, tests, README) are written
from this document; when they disagree with it, this document wins and the other side
is the bug.

Contract version: **2** (2026-09). It supersedes the v1.3 contract described in the
Portuguese README of earlier releases. Section 15 lists every difference.

Conventions used below:

- `snake_case` names are JSON keys or CLI flags exactly as they must appear.
- "stderr" means diagnostics; "stdout" means the one-line counters that scripts print
  on success. Nothing else goes to stdout.
- "MUST" / "MUST NOT" are hard requirements for the implementation; "SHOULD" is a
  recommendation for data authors.
- Paths inside all JSON files use `/` as separator, are relative to the root of the
  repository being mapped (the *target repo*) and never start with `./`. The
  pipeline normalizes `\` to `/` and strips a leading `./` wherever it reads a path.

---

## 1. Pipeline overview

```
target repo (read-only)
  │
  ├─ 1. extractor/extract.mjs  (Node 22, tree-sitter, deterministic, offline)
  │       └─ <extract-out>/scan-output.json, im-output.json, es-output.json
  │
  ├─ 2. pipeline/prep_data.py  (config + use-case registry)
  │       └─ data.json   {meta, files, imports, ucs}
  │
  ├─ 3. pipeline/prep_extra.py (entry points + call edges)
  │       └─ extra.json  {nfiles, entry_points, calls}
  │
  └─ 4. pipeline/inject.py     (string-replaces __MATRYOSHKER_DATA__ in viewer/template.html)
          └─ matryoshker.html  (self-contained; the embedded object is data.json + extra.json)

pipeline/build.py runs 1→4 in one command. Each step also works standalone.
```

Inputs owned by the user of the tool:

| File | Purpose | Reference |
|---|---|---|
| `config/<repo>.json` | categories, classification rules, UI language, hop path prefixes, entry-point parsers | section 3, `schemas/config.schema.json` |
| `data/<repo>/usecases.json` | versioned use-case registry (canonical file name `usecases.json`) | section 4, `schemas/usecases.schema.json` |

Principles that every implementation MUST keep:

1. `pipeline/` is pure Python standard library (3.10+). No third-party runtime
   dependency, ever.
2. The viewer is one HTML file with zero external dependencies except the Google Fonts
   `<link>`. Its CSS colors live in three theme blocks (`:root`, the guarded
   `prefers-color-scheme: dark` block, `:root[data-theme="dark"]`); a color defined in
   only one block is a bug.
3. No script writes into the target repository. Everything is written under
   `--out` / `--extract-out`.
4. The injection placeholder is `__MATRYOSHKER_DATA__` and never changes.
5. Anything specific to one repository (categories, prefixes, routes, framework
   conventions) lives in `config/`, `data/` or a parser module — never in the viewer.

### 1.1 The file index invariant

Every cross-reference in the embedded object (`imports`, `ucs[].hops[].i`,
`entry_points[].i`, the keys of `calls` and `calls[].x[][1]`) is an **integer index into
`files`**. `files[k]` is the k-th entry of `es-output.json` → `results`, in file order,
after path normalization. `prep_data.py` and `prep_extra.py` MUST build this index the
same way (iterate `results` in order, `norm_path` each `path`, skip nothing). To make a
mismatch impossible to miss, `extra.json` carries `nfiles` and `inject.py` refuses to
merge when it differs from `data.json` → `meta.nfiles` (section 8).

---

## 2. Extractor outputs consumed by the pipeline

`extractor/extract.mjs <repoRoot> --out <dir> [--exclude "p1,p2"] [--lang <language>]`
writes three files into `<dir>`. The pipeline reads only these fields:

`es-output.json` (extract-structure):

```
{ "scriptCompleted": true, "filesAnalyzed": N, "filesSkipped": [path...],
  "results": [ { "path": "src/x.py", "totalLines": 120,
                 "classes":   [ { "name": "Foo", "startLine": 3, "endLine": 40, "methods": ["run", "stop"] } ],
                 "functions": [ { "name": "main", "startLine": 42, "endLine": 60 } ],
                 "exports":   [ { "name": "Foo" } ],
                 "callGraph": [ { "caller": "Foo.run", "callee": "helper", "lineNumber": 12 } ] } ] }
```

- `classes`, `functions`, `exports`, `callGraph` may be absent or `null` (treated as empty).
- A `functions` entry may be a bare string in older extractions (treated as `[name, 0, 0]`).
- `scan-output.json` (`{ "files": [ { "path", "language", "sizeLines", "fileCategory" } ], "totalFiles": N }`)
  is read only by `suggest_config.py`.

`im-output.json` (extract-import-map): `{ "importMap": { "src/a.py": ["src/b.py", ...] } }`.
Edges whose source or destination is not in `results` are ignored; self-imports are ignored.

---

## 3. Config file: `config/<repo>.json`

JSON object. Schema: `schemas/config.schema.json` (draft-07). A config MAY carry a
`"$schema"` key for editor support; the pipeline ignores it.

### 3.1 Keys

| Key | Type | Default | Meaning |
|---|---|---|---|
| `repo` | string, non-empty | **required** | Display name. Also part of the viewer's `localStorage` key `mtk:<repo>@<commit>`. |
| `commit` | string | `"?"` | Commit the map was built from (short SHA recommended). Shown in the header; part of the `localStorage` key. |
| `date` | string | `""` | Build/snapshot date shown in the header. ISO `YYYY-MM-DD` recommended; displayed verbatim. |
| `lang` | `"en"` \| `"pt-BR"` | `"en"` | Viewer UI language (section 13). Any other value → stderr warning, `"en"` used. |
| `categories` | array of category objects | `[]` | Ordered list; drives colors and the legend (3.2). |
| `rules` | array of `[prefix, category_id]` pairs | `[]` | Path classification, first match wins (3.3). |
| `fallback_category` | string | `"other"` | Category of files no rule matches and that are not tests. |
| `test_path_marker` | string \| null | `"/tests"` | Substring that marks test files. `""` or `null` disables the check. |
| `test_category` | string | `"tests"` | Category assigned when `test_path_marker` matches. |
| `hop_path_prefixes` | array of strings | `[]` | Prefixes tried when a cited path does not resolve as written (section 5.3). |
| `entry_points` | object `{ "parsers": [...] }` | absent | Route parsers to run (section 6.3). Absent or `parsers: []` → no parser runs. |

Aliases and deprecated keys:

| Key | Status | Rule |
|---|---|---|
| `data` | v1 alias of `date` | Accepted silently. If both `date` and `data` are present, `date` wins. |
| `urls_files` | **deprecated** (v1) | Accepted with the stderr warning `warning: config key "urls_files" is deprecated; use entry_points.parsers` and mapped to one parser entry `{"name": "django-drf", "files": <urls_files>, "route_prefix": "", "ignore_views": []}`. If `entry_points` is also present, `urls_files` is ignored (warning says so). |
| any other key | unknown | stderr `warning: config: unknown key "<key>" ignored`. The JSON Schema is stricter (`additionalProperties: false`) so that editors flag typos. |

Validation performed by `pipeline/config.py` (`load_config`), all fatal (exit 1) unless
marked warning:

- file missing / not UTF-8 / invalid JSON / top level not an object;
- `repo` missing or empty;
- `categories[n]` not an object with a non-empty string `id`, or duplicate `id`;
- `rules[n]` not a 2-element array of strings, or empty prefix;
- `hop_path_prefixes[n]` not a non-empty string;
- `entry_points` not an object, `entry_points.parsers` not an array, a parser entry
  without a string `name`, or a `name` that is not registered (section 6.3);
- warning: a category id used in `rules`, `fallback_category` or `test_category` that
  is not declared in `categories` (the viewer paints undeclared categories gray).

### 3.2 Category object

```
{ "id": "domain", "label": "Domain", "gray": false, "muted": false }
```

| Key | Type | Default | Meaning |
|---|---|---|---|
| `id` | string, non-empty, unique | required | Value stored in `files[].g`. |
| `label` | string | `id` | Legend text. |
| `gray` | boolean | `false` | Neutral color (gray slot) instead of a palette slot. |
| `muted` | boolean | `false` | Hidden by default; the header toggle reveals it (tests, typically). |

Color assignment (viewer, deterministic): walking `categories` in order, the first six
non-gray categories get palette slots 1..6, every later non-gray category shares slot 6;
gray categories get gray slots 1, 2, then 2 again. A file whose `g` is not in
`categories` is painted with gray slot 1 and labelled with its raw id.

### 3.3 Rules

`rules` is an ordered list of `[prefix, category_id]`. `prep_data.py` classifies each
file path as:

1. the category of the first rule whose `prefix` satisfies `path.startswith(prefix)`;
2. else `test_category` if `test_path_marker` is non-empty and `test_path_marker in path`;
3. else `fallback_category`.

Authors SHOULD end prefixes with `/` (`"src/app/"`) so that `src/app` does not also
capture `src/apple`. Put the more specific prefix first (`suggest_config.py` orders
its draft that way).

### 3.4 Example

```json
{
  "$schema": "../schemas/config.schema.json",
  "repo": "library-catalog",
  "commit": "a1b2c3d",
  "date": "2026-09-05",
  "lang": "en",
  "categories": [
    { "id": "api",     "label": "API" },
    { "id": "domain",  "label": "Domain" },
    { "id": "infra",   "label": "Infrastructure" },
    { "id": "other",   "label": "Other", "gray": true },
    { "id": "tests",   "label": "Tests", "gray": true, "muted": true }
  ],
  "rules": [
    ["src/api/", "api"],
    ["src/domain/", "domain"],
    ["src/infra/", "infra"]
  ],
  "fallback_category": "other",
  "test_path_marker": "/tests",
  "test_category": "tests",
  "hop_path_prefixes": ["src/"],
  "entry_points": {
    "parsers": [
      { "name": "django-drf", "files": ["src/api/urls.py"], "route_prefix": "/v1",
        "ignore_views": ["Spectacular"] }
    ]
  }
}
```

---

## 4. Use-case registry: `data/<repo>/usecases.json`

JSON **array** of use-case objects. Schema: `schemas/usecases.schema.json`. An empty
registry is `[]`. The registry is the collective source of truth: the viewer never
writes it; local status drafts made in the viewer are exported as a JSON snippet to be
applied via pull request.

### 4.1 Keys

| Key | Type | Default | Read by the pipeline? |
|---|---|---|---|
| `name` | string, non-empty, **unique in the file** | **required** | yes → `ucs[].name`; the viewer keys local status drafts by it |
| `actor` | string | `""` | yes → `ucs[].actor` |
| `goal` | string | `""` | yes → `ucs[].goal` |
| `entry_points` | array of entry-point citations (strings, section 5.2) | `[]` | yes → merged into `entry_points` (section 6) |
| `hops` | array of hop citations (strings, section 5.1), in execution order | `[]` | yes → `ucs[].hops` |
| `rules` | array of strings (business rules touched) | `[]` | yes → `ucs[].rules` |
| `seam_crossing` | boolean | `false` | yes → `ucs[].seam` |
| `status` | status value (4.2) | `"inferred"` | yes → `ucs[].status` |
| `async_legs` | array | `[]` | no (documentation) |
| `failure_paths` | array | `[]` | no (documentation) |
| `tests` | array | `[]` | no (documentation) |
| any other key (`notes`, `preconditions`, `documented`, ...) | any | — | no; ignored without warning |

v1 aliases, accepted transparently (no warning). When both the canonical key and the
alias are present, the canonical key wins:

| v1 key | v2 key |
|---|---|
| `nome` | `name` |
| `ator` | `actor` |
| `objetivo` | `goal` |
| `regras_envolvidas` | `rules` |

Fatal (exit 1) registry errors, raised by `pipeline/usecases.py` (`load_usecases`):
file missing / not UTF-8 / invalid JSON; top level not an array; an element that is
not an object; an element with neither `name` nor `nome` (or an empty one); two
use-cases with the same resolved `name`. Non-string items inside `hops`, `entry_points`
or `rules` are a fatal error too (`--ucs: use-case "<name>": hops[2] must be a string`).

### 4.2 Status values

Canonical values and their v1 aliases:

| Canonical (v2) | v1 alias(es) | Meaning |
|---|---|---|
| `human-verified` | `verificado-humano` | a human re-read the hops and blessed them — **never set by an agent, never a default** |
| `agent-verified` | `verificado-agente` | structured/checked by an agent pipeline (its ceiling) |
| `inferred` | `inferido` | written without a complete re-read |
| `hypothesis` | `hipotese`, `hipótese` | not yet confirmed against the code |
| `outdated` | `desatualizado` | the code contradicts it (keep it; the divergence is information) |

The pipeline maps aliases to the canonical value silently. Any other value →
`warning: UC <name>: unknown status "<value>", using "inferred"`. `data.json` and the
viewer only ever contain canonical values.

### 4.3 Example

```json
[
  {
    "name": "Librarian registers a new book",
    "actor": "Librarian",
    "goal": "Add a title to the catalog so members can borrow it",
    "entry_points": [
      "http: POST /v1/books (src/api/views.py:BookViewSet)",
      "command: src/domain/commands.py:RegisterBook — RegisterBookHandler.handle"
    ],
    "hops": [
      "src/api/views.py:BookViewSet.create — validates the payload and dispatches",
      "src/domain/commands.py:RegisterBookHandler.handle — central rule",
      "src/domain/isbn.py:validate_isbn13 — branch: ISBN-13, checksum over 12 digits",
      "src/domain/isbn.py:validate_isbn10 — branch: legacy ISBN-10, X allowed as check digit",
      "src/infra/repositories.py:BookRepository.add — persists the aggregate"
    ],
    "async_legs": [],
    "failure_paths": ["duplicate ISBN → 409"],
    "rules": ["ISBN must be unique"],
    "tests": ["tests/api/test_books.py::test_create"],
    "seam_crossing": false,
    "status": "inferred",
    "notes": "free text, ignored by the pipeline"
  }
]
```

The two `branch:` hops are siblings, not a sequence: the handler picks one validator by
ISBN length and both reconverge on `BookRepository.add`. The viewer draws them as level
`3a` / `3b` side by side, with `add` at level 4 (§5.1).

---

## 5. Citation grammar and resolution

A *citation* is the fragment `path/file.ext[:Symbol]` that ties a line of the registry
to a file of the extraction. Hops and entry points share the regex, the file finder
and the reporting format; they differ only in what surrounds the citation.

### 5.1 Hop citation

```
"<path/file.ext>[:<Symbol>] — <role>"
```

- `—` is the em dash (U+2014). ` - ` (hyphen) and ` – ` (en dash, U+2013) are accepted;
  authors SHOULD standardize on the em dash.
- `<Symbol>` SHOULD be `Class.method`, `Class` or `function`. `:123` and `:123-145`
  (line references) are accepted and kept verbatim as the symbol text. `()` after a
  symbol is stripped.
- `<role>` is free text describing what the hop does (14 words or fewer recommended);
  it is truncated at **140 characters** (`ROLE_MAX_LEN`).

**Role prefixes.** A role MAY open with one of four words followed by a colon. The word
is matched case-insensitively and only at the very start of the role, so `picks the
branch: left or right` is ordinary prose, not a prefix.

| Prefix (en) | Prefix (pt) | Derived `hops[].k` | Meaning |
|---|---|---|---|
| `branch:` | `ramo:` | `"branch"` | a sibling: one of N alternatives chosen at the preceding hop |
| `seam:` | `costura:` | `"seam"` | the hop crosses a seam — disk, HTTP, subprocess, a human step |

The prefix stays inside `r` verbatim (§7.4); the derived kind is emitted separately so
the viewer never re-parses role text and the vocabulary lives in `pipeline/usecases.py`
alone. A registry with no prefixes emits no `k` at all and its `data.json` is byte for
byte what it was before fan-out existed.

**Fan semantics.** `hops` stays a flat array in execution order; the fan is derived from
adjacency:

- **selector** — the last non-`branch` hop before a run of `branch` hops;
- **siblings** — the *consecutive* run of `branch` hops. The whole run occupies **one
  level**, drawn side by side;
- **reconvergence** — the next non-`branch` hop, which receives one edge from each
  sibling.

**Numbering is by level, not by hop.** The selector is level N-1, every sibling is level
N and is labeled `Na`, `Nb`, `Nc`, the reconvergence is level N+1. A registry with one
hop per level — which is any registry without role prefixes — therefore numbers `1..N`,
exactly as before. Edges are the cartesian product between consecutive levels, which
covers selector→fan (1×N), fan→reconvergence (N×1) and step→step (1×1) with one rule;
two fans are never adjacent by construction, so N×M cannot arise. A run of length 1 is
still a fan: it is drawn off the main line, so a lone `branch:` between two ordinary hops
does not read as a step.

**Limitations, deliberate in this version.**

- **No nesting.** A `branch:` hop cannot itself open a sub-fan.
- **Two independent adjacent lateral alternatives merge into one fan of two.** Adjacency
  is all the grammar has. To express them separately, put a non-branch hop between them.
- **A sibling that actually terminates mid-chain is still drawn reconverging.** An error
  path is not a step toward the next hop, and the registry has no way to say so.
- **The map overlay is file-level** and dedups consecutive hops of the same file, so a
  fan whose siblings live in the selector's own file cannot appear there. The Flow panel
  is hop-level and does show it.

### 5.2 Entry-point citation

```
"[<kind>: ][<label> ]<path/file.ext>[:<Symbol>][ — <text>]"
```

- `<kind>` is one of `http`, `command`, `event`, `cli`, `cron`, `other`,
  case-insensitive, followed by `:`. No prefix → kind `other`. The prefix MUST be at the
  very start; `http://...` is not a kind prefix (see the regex below).
- `<label>` is the text between the kind prefix and the citation, e.g. `POST /v1/books`.
- `<text>` after the separator is free text.
- The label of the resulting entry point is, in order of precedence: `<label>` if
  non-empty; else `<text>` if non-empty; else the use-case `name`.

Examples (all valid):

```
"http: POST /v1/books (src/api/views.py:BookViewSet)"       kind http,    label "POST /v1/books",  symbol BookViewSet
"command: src/domain/commands.py:RegisterBook — register"    kind command, label "register",        symbol RegisterBook
"src/jobs/nightly.py:rebuild_index"                          kind other,   label = use-case name,  symbol rebuild_index
"POST /v1/books (src/api/views.py:BookViewSet)"              kind other (v1 form still works)
```

### 5.3 Parsing algorithm (normative)

Constants (module `pipeline/usecases.py`):

```python
CITATION = re.compile(r'([\w/.\-]+\.\w+)\s*(?::\s*([\w.\-]+(?:\(\))?|\d+(?:-\d+)?))?')
KIND_PREFIX = re.compile(r'^\s*(http|command|event|cli|cron|other)\s*:(?!//)\s*', re.I)
LEAD_TRIM = re.compile(r'\s*[(\[{]*\s*$')                 # trailing "(" of "label (file.py:X)"
TAIL_TRIM = re.compile(r'^\s*[)\]}]*\s*(?:[—–-]\s*)?')  # ")", then one separator
ROLE_MAX_LEN = 140
KINDS = ('http', 'command', 'event', 'cli', 'cron', 'other')   # also the sort order
```

For one raw string `s`:

1. Normalize: `s = norm_path(s)` (`\` → `/`). Entry points only: match `KIND_PREFIX`;
   if it matches, `kind = group(1).lower()` and `s` becomes the remainder, else
   `kind = "other"`.
2. Candidates: `list(CITATION.finditer(s))`. If empty → **dropped**, reason
   `no file citation`.
3. For each candidate in order, `path = group(1)` with a leading `./` stripped; call
   `find_file(path)`. The **first candidate whose file resolves** is the citation.
   If none resolves → **dropped** with the reason returned for the *first* candidate.
4. `symbol = (group(2) or '').rstrip('()')`; hops store it as `s` (`""` when absent),
   entry points store it as `symbol` (`null` when absent).
5. `head = LEAD_TRIM.sub('', s[:match.start()]).strip()`;
   `tail = TAIL_TRIM.sub('', s[match.end():], count=1).strip()[:ROLE_MAX_LEN]`.
   Hops: `r = tail` (`head` is ignored). Entry points: label per 5.2 using `head`, `tail`.

This is a superset of the v1 behavior for well-formed hops (`citation — role`), and
additionally keeps the role when the separator is missing and skips path-looking
tokens inside labels (`/v1/books.json (views.py:X)`).

`find_file(path)` (built by `make_file_finder(path_index, hop_path_prefixes)`) tries,
in order, and returns `(index, None)` at the first hit:

1. `path` exactly;
2. `prefix + path` for each prefix of `config.hop_path_prefixes`, in config order
   (a prefix without a trailing `/` gets one appended before joining);
3. basename match: every extracted path `p` such that `p == basename` or
   `p.endswith('/' + basename)`, where `basename = path.split('/')[-1]`. Exactly one hit
   → resolved; more than one → `(None, "ambiguous file name (N files end with /<basename>)")`;
   none → `(None, "file not found in the extraction")`.

Matching is case-sensitive and uses the paths exactly as the extractor wrote them.

### 5.4 Symbol verification (warning only)

After a hop resolves, `prep_data.py` checks the symbol against `files[i]`:
`A.b` → class `A` exists and `b` is in its methods; `X` → a class `X`, a function `X`
or a method `X` of any class exists; numeric line references and empty symbols are not
checked. A miss does **not** drop the hop; it prints
`  unverified symbol [<symbol> not declared in <path>]: <raw hop>`. The hop still appears
on the map, so authors must fix it in the registry.

### 5.5 Reporting (stderr) and totals

Per use-case, printed only when the use-case has at least one dropped citation or one
unverified symbol:

```
UC <name>: <resolved>/<total> hops resolved
  dropped [<reason>]: <raw hop>
  unverified symbol [<symbol> not declared in <path>]: <raw hop>
UC <name>: <resolved>/<total> entry points resolved
  dropped [<reason>]: <raw entry point>
```

Then, only when something was dropped:

```
total: <resolved>/<total> hops resolved (<dropped> dropped in <n> use-cases)
total: <resolved>/<total> entry points resolved (<dropped> dropped in <n> use-cases)
```

Dropped citations never change the exit code (0) unless `--strict` is given
(section 10). A dropped entry-point citation is kept in the registry as documentation
only: it produces no node.

---

## 6. Entry points

An *entry point* is a place where execution enters the codebase: an HTTP route, a
command handler, an event consumer, a CLI command, a scheduled job. HTTP endpoints are
one kind among several; a project that prototypes use-cases before routes has entry
points and no `urls.py`. The v1 `endpoints` key no longer exists.

### 6.1 Shape in the embedded object

```
"entry_points": [ { "label": "POST /v1/books/{id}/borrow", "kind": "http", "i": 12,
                    "symbol": "BookViewSet", "route": "/v1/books",
                    "ucs": ["Member borrows a copy of a title"] } ]
```

| Key | Type | Meaning |
|---|---|---|
| `label` | string, non-empty | What the panel shows. A label a use-case author declared, when there is one; else the route a parser produced; else the use-case name. |
| `kind` | `"http"` \| `"command"` \| `"event"` \| `"cli"` \| `"cron"` \| `"other"` | Group in the panel. |
| `i` | integer, `0 <= i < nfiles` | File where execution enters. Everything the viewer does with an entry point starts from this index. |
| `symbol` | string \| null | Declaring symbol (view class, handler, function) when known. |
| `route` | string \| null | The route a parser produced for this entry point — its own, or the one of the class it is a method of. `null` when no parser contributed. Kept next to `label` so turning a parser on never destroys a written label. |
| `ucs` | array of strings | Names of the use-cases this entry point belongs to (they declared it, or it is their first-hop fallback), in registry order, each at most once. `[]` when only parsers contributed. |

### 6.2 Sources and merge (normative)

Three optional sources, merged **in this order**:

1. **Route parsers** listed in `config.entry_points.parsers`, in config order, each
   producing entries in file order (section 6.3).
2. **Declared entry points** of every use-case (`entry_points[]`, section 5.2), use-cases
   in registry order, citations in declaration order. Unresolved citations are dropped
   with a stderr report and never produce a node. Each declared entry carries the name
   of the use-case that declared it.
3. **Fallback**: for every use-case with **zero resolvable declared entry points**
   (including use-cases with an empty `entry_points`), its **first resolved hop** becomes
   an entry point with `kind: "other"`, `label` = use-case `name`, `symbol` = the hop's
   symbol or `null` when empty. A use-case with no resolved hop contributes nothing.
   The fallback entry carries the use-case name too.

Merge rule: entries are grouped by the key `(i, symbol or "")`; every group becomes
**one** entry point that keeps what each source knows, instead of discarding all but the
first. With the source precedence **declared > parsers > fallback**:

| Field | Rule |
|---|---|
| `i`, `symbol` | the group key; identical in every member by construction |
| `label` | the label of the first member of the most precedent source present. A hand-written declaration wins over a generated route; a fallback label (the use-case name) never overrides either. |
| `kind` | the kind of the first member, in source precedence order, whose kind is not `"other"`; `"other"` when every member is `"other"`. An unprefixed declaration therefore does not demote a parser's `http`, while an explicit `command:` on the same symbol does. |
| `route` | the label a route parser produced for the key, or — when `symbol` is `Class.method` — the one it produced for `(i, "Class")`. `null` when no parser contributed. An entry that comes from a parser alone has `route == label`. |
| `ucs` | the names of the use-cases that declared the entry point or contributed it as a fallback, in registry order, each name at most once. |

The merged entry keeps the list position of its first member (parsers, then declared,
then fallback); the position only decides ties the sort below cannot break.

Finally sort by `(KINDS.index(kind), route or label, label, symbol or "", i)`; the sort
is stable. Sorting on the route first keeps the entry points of one parsed route
together — the viewset the router mounted and each of its methods a use-case declared —
instead of scattering them by their labels.

Between `collect_from_usecases` and the merge, a declared or fallback entry carries its
use-case name in the internal key `uc` and the position of that use-case in the loaded
registry in the internal key `ucpos`. `ucs` is ordered on `ucpos`, not on the order the
merge meets the contributions: the merge walks the whole declared list before the whole
fallback list, so a use-case that comes first in the registry but contributes through
the fallback would otherwise be named after a later one that declared the entry point.
Neither key is ever emitted.

Consequences to document for users:

- Turning a route parser on never replaces a label a use-case author wrote: the parser's
  route is kept in `route` and the declared `label` stands. The same registry shows the
  same labels with and without a parser.
- Two use-cases whose first hop is the same file and symbol still share one fallback
  entry point, labelled with the first use-case's name — but both names appear in `ucs`.
- Two use-cases declaring the same `(i, symbol)` share one entry point labelled with the
  first declaration's label; both names appear in `ucs`.
- A class-level route from a parser and a method-level entry a use-case declared on the
  same class are different keys and stay two entries — deliberately, since they are two
  different places to enter. They share the same `route`, so the panel shows them
  together and says which route each belongs to.

The merge lives in `pipeline/entry_points/__init__.py: merge_entry_points(...)` and is
invoked by **`prep_extra.py`**, which is the only script that emits `entry_points`
(section 10.4). `prep_data.py` does not know about entry points. Both scripts read the
registry through the same `pipeline/usecases.py` loader and file finder, so hops resolve
identically; `prep_extra.py` resolves hops with reporting **silenced** (`prep_data.py`
already reported them) and reports only entry-point citations and parser drops.

### 6.3 Parser interface

Package `pipeline/entry_points/`:

```
pipeline/entry_points/__init__.py   PARSERS = {'django-drf': django_drf}; get_parser(name); merge_entry_points(...)
pipeline/entry_points/django_drf.py parse(files, class_file, options) -> list[dict]
```

- `get_parser(name)` returns the module or raises
  `SystemExit('--config: unknown entry-point parser "<name>"; available: django-drf')`
  (the list is `sorted(PARSERS)`; exit 1).
- `parse(files, class_file, options)`:
  - `files`: list of absolute paths to the source files to scan — the config entry's
    `files`, each joined with the target repo root (`prep_extra --repo`). A missing file
    is fatal (`--config: entry_points.parsers[n].files: file not found: <path>`).
  - `class_file`: `dict[str, str]` mapping each **top-level class name** found in the
    extraction to the (normalized, repo-relative) path that declares it; on duplicates
    the first file in extraction order wins.
  - `options`: the config entry minus `name` and `files`. A parser MUST ignore options
    it does not know and print `warning: parser <name>: unknown option "<key>"`.
  - returns a list of `{"label": str, "kind": str, "path": str, "symbol": str|None}`
    where `path` is a value taken from `class_file` (so it always maps to an index).
    `prep_extra.py` turns `path` into `i`. A parser never sees or invents file indices.
    `kind` MUST be one of `KINDS` (6.1); `prep_extra.py` validates it and, for anything
    else, prints `warning: parser <name>: unknown kind "<k>", using "other"` and coerces
    it to `other` — the viewer renders only the six declared groups, so an unvalidated
    kind would silently drop the entry point from the panel.
  - a parser reports what it could not map as
    `parser <name> (<file>): dropped [<reason>]: <what>` on stderr and continues.

The parser interface is unchanged by the label/route merge: a parser still returns only
label/kind/path/symbol, and `prep_extra.py` derives an entry point's route from the
parser's own label (section 6.2).

Config entry for a parser (`config.entry_points.parsers[n]`):

| Key | Type | Default | Meaning |
|---|---|---|---|
| `name` | string | required | Registry name. Unknown → fatal, listing available parsers. |
| `files` | array of strings (paths relative to the target repo root) | `[]` | Files the parser scans. `django-drf` requires at least one (warning + no output otherwise). |
| `route_prefix` | string; `""` or starting with `/` | `""` | Prepended to every route label. A trailing `/` is stripped. |
| `ignore_views` | array of strings | `[]` | A view whose class name contains any of these substrings is skipped silently. |
| other keys | any | — | Parser-specific; unknown ones warn. |

### 6.4 The `django-drf` parser

Scans each file with two regexes (multiline):

```python
ROUTER_REGISTER = re.compile(r"^\s*router\.register\(r?['\"]([^'\"]+)['\"]\s*,\s*(?:\w+\.)?(\w+)", re.M)
PATH_AS_VIEW    = re.compile(r"path\(['\"]([^'\"]+)['\"]\s*,\s*(?:\w+\.)?(\w+)\.as_view")
```

For each match: `view = group(2)`; skip it if any `ignore_views` substring is in `view`;
`route = route_prefix + '/' + group(1).lstrip('/')` (kept verbatim otherwise, including a
trailing `/`); `path = class_file.get(view)`; if `path` is missing → stderr
`parser django-drf (<file>): dropped [view class not found in the extraction]: <route> <view>`;
else emit `{"label": route, "kind": "http", "path": path, "symbol": view}`.
Output order: files in config order; inside a file, all `router.register` matches, then
all `path(..., X.as_view)` matches, each in source order.

Function-based views and `include()` are out of scope for this parser (a contribution).

---

## 7. `data.json` — output of `prep_data.py`

```
{
  "meta":    { ... },                     section 7.1
  "files":   [ ... ],                     section 7.2
  "imports": [ [src, dst], ... ],         section 7.3
  "ucs":     [ ... ]                      section 7.4
}
```

Serialized with `json.dumps(ensure_ascii=False, separators=(',', ':'))`.

### 7.1 `meta`

| Key | Type | Source | Viewer use |
|---|---|---|---|
| `contract` | integer, always `2` | constant | none (reserved for tooling; the viewer MUST NOT fail on it) |
| `repo` | string | `config.repo` | header line; `localStorage` key |
| `commit` | string | `config.commit` | header line; `localStorage` key |
| `date` | string | `config.date` (or `data`) | header line |
| `lang` | `"en"` \| `"pt-BR"` | `config.lang` | selects `UI_STRINGS[lang]`; `<html lang>` |
| `categories` | array of category objects | `config.categories`, verbatim | legend, colors, muted toggle. Empty array ⇒ the viewer derives one gray category per distinct `files[].g` (same as a missing key) |
| `nfiles` | integer | `len(files)` | cross-check with `extra.json.nfiles` in `inject.py` |
| `nimports` | integer | `len(imports)` | informational |
| `nucs` | integer | `len(ucs)` | informational |

### 7.2 `files`

Array; index = file identity (1.1).

```
{ "p": "src/api/views.py", "n": 120, "g": "api",
  "c": [ ["BookViewSet", 10, 80, ["list", "create"]] ],
  "f": [ ["healthcheck", 84, 90] ] }
```

| Key | Type | Meaning |
|---|---|---|
| `p` | string | normalized path |
| `n` | integer | `totalLines` (0 when absent) |
| `g` | string | category id (3.3) |
| `c` | array of `[name, startLine, endLine, [method, ...]]` | classes |
| `f` | array of `[name, startLine, endLine]` | free functions |

The viewer derives from `files`: the Packages layout (cluster key = first two path
segments, `(root)` for files at the root), the search index, the Symbols scene.

### 7.3 `imports`

Array of `[source_index, target_index]`, deduplicated (each pair at most once), in
`importMap` order, no self-loops. The viewer derives out/in adjacency (detail panel,
Context edges aggregated per cluster with thickness `1 + log2(n)` and hidden below 2
imports, the entry-point lens = BFS of depth 2 over out-edges, the `impIn` centrality).

### 7.4 `ucs`

```
{ "name": "Librarian registers a new book", "actor": "Librarian", "goal": "…",
  "seam": false, "rules": ["ISBN must be unique"], "status": "inferred",
  "hops": [ { "i": 12, "s": "BookViewSet.create", "r": "validates the payload and dispatches" },
            { "i": 18, "s": "validate_isbn13", "r": "branch: ISBN-13, checksum over 12 digits", "k": "branch" } ] }
```

| Key | Type | Source |
|---|---|---|
| `name` | string | registry `name` (alias `nome`) |
| `actor` | string | `actor` (`ator`), `""` default |
| `goal` | string | `goal` (`objetivo`), `""` default |
| `seam` | boolean | `bool(seam_crossing)` |
| `rules` | array of strings | `rules` (`regras_envolvidas`) |
| `status` | canonical status | `status` after alias mapping |
| `hops` | array of `{i, s, r}` plus optional `k` | resolved hops only, in registry order; `s` is `""` when the citation had no symbol |

`hops[].k` is derived from the role prefix of §5.1 and is one of `"branch"` or `"seam"`.
It is **omitted** when the role has no prefix, so a registry that uses none produces the
same bytes it always did. `r` is unaffected: it keeps the prefix verbatim, which is what
the detail panel shows an author fixing the registry file. Consumers that do not care
about fan-out can ignore `k` entirely.

Registry order is preserved. A use-case with zero resolved hops is still emitted (it
shows in the panel with `Hops (0)`). The viewer derives `ucByFile` (reverse index
file → use-cases, the same join as the overlay, so both directions agree by
construction) and the `ucCount` centrality.

---

## 8. `extra.json` — output of `prep_extra.py` — and injection

```
{ "nfiles": 240,
  "entry_points": [ { "label": "POST /v1/books/{id}/borrow", "kind": "http", "i": 12,
                      "symbol": "BookViewSet", "route": "/v1/books",
                      "ucs": ["Member borrows a copy of a title"] } ],
  "calls": { "12": { "n": [ ["BookViewSet.create", "validate", 31] ],
                     "x": [ ["BookViewSet.create", 40, "RegisterBookHandler", 33] ] } } }
```

| Key | Type | Meaning |
|---|---|---|
| `nfiles` | integer | number of extracted files, for the index cross-check |
| `entry_points` | array (section 6.1) | merged, deduplicated, sorted |
| `calls` | object keyed by file index **as a string** | only files with at least one edge appear |
| `calls[i].n` | array of `[caller, callee, line]` | internal edges: callee is a class, method or function of the same file |
| `calls[i].x` | array of `[caller, target_index, symbol, line]` | cross-file edges: `symbol` is an export/class/function of `files[target_index]`, found among the files `i` imports |

Call resolution (unchanged from v1): the callee expression is split into identifiers;
`self.x` uses `x`; the first identifier is looked up in the same file, then up to the
first three identifiers are looked up in the exports of imported files; names in the
builtin skip list (`len`, `dict`, `print`, `Exception`, ...) never become edges; one edge
per `(caller, root identifier)` per file.

**Call resolution is tuned for Python.** Two of its constants are Python-specific and
are not configurable in contract v2: `prep_extra.SKIP` lists Python builtins and common
Python exceptions, and the only receiver stripped from a call expression is `self`. The
extractor parses many more languages, and for those the call edges are noisier (a
language's own builtins are not skipped) or thinner (`this.method()` resolves on
`this`, not on `method`). Files, imports, symbols and use-case hops are language-neutral;
only `calls` carries this bias. Making the skip list and the receiver aliases
(`self`, `this`, ...) config keys is a candidate for a later contract version.

The viewer derives from `calls`: the Symbols scene edges, the call tree of the Flow
scene (breadth-first over `x` targets, depth 3, at most 8 children per node, an
`+N` marker for the rest) and the `callIn` centrality.

`inject.py` merges:

- `data.entry_points = extra.get('entry_points', [])` and `data.calls = extra.get('calls', {})`;
- without `--extra`, both keys are still written as `[]` / `{}` so the embedded object
  always has all six keys;
- if `extra.nfiles` is present and `!= data.meta.nfiles` → fatal:
  `--extra: nfiles=<a> does not match --data meta.nfiles=<b> (different extractions?)`.

The payload is serialized with `ensure_ascii=False`, then every `</` is replaced by
`<\/` so the JSON can never close the `<script>` tag hosting it, and the placeholder
`__MATRYOSHKER_DATA__` is replaced by it. A template without the placeholder is fatal.

### 8.1 The embedded object (what the viewer reads)

```
DATA = { meta, files, imports, ucs, entry_points, calls }
```

The viewer reads it as `JSON.parse(document.getElementById('data').textContent)` and
MUST tolerate `entry_points` and `calls` being absent (default `[]` / `{}`) and
`meta.categories` being absent or empty.

---

## 9. Module layout of `pipeline/` after the change

```
pipeline/
  __init__.py          empty; makes `python -m pipeline.<script>` work
  _common.py           read_json / read_text / write_text / norm_path / warn / warn_python_version / kb
  config.py            load_config(path) -> dict with defaults applied, aliases resolved, deprecations warned
  usecases.py          load_usecases(path) -> list; CITATION & co.; make_file_finder; parse_hop; parse_entry_point;
                       resolve_use_case(uc, find_file, report) -> {"hops": [...], "entry_points": [...], ...}
  entry_points/
    __init__.py        PARSERS, get_parser(name), merge_entry_points(parsed, declared, fallback) -> list
    django_drf.py      parse(files, class_file, options)
  prep_data.py         CLI (section 10.3)
  prep_extra.py        CLI (section 10.4)
  inject.py            CLI (section 10.5)
  build.py             CLI orchestrator (section 10.6)
  suggest_config.py    CLI (section 10.2)
```

Rules for the modules:

- every script keeps the `try: from _common import ... except ImportError: from pipeline._common import ...`
  pattern so that both `python pipeline/x.py` and `python -m pipeline.x` work;
- `config.py` and `usecases.py` have no CLI; they raise `SystemExit('<flag>: <message>')`
  with the flag name they were given (`--config`, `--ucs`) so messages point at the
  right argument;
- all text is English: identifiers, docstrings, comments, messages.

`load_config` returns a dict with **every** key of 3.1 present (defaults applied,
`date` resolved, `urls_files` folded into `entry_points`), so callers never call
`.get` with a default again. `load_usecases` returns use-cases with canonical keys and
canonical status, extra keys preserved.

---

## 10. CLI reference

Common to every Python script: `argparse`; `-h/--help`; a stderr warning (never a
failure) when the interpreter is older than 3.10; fatal errors are printed as
`<flag>: <message>` (exit 1); bad command-line syntax exits 2 (argparse); one summary
line on stdout on success. Scripts never modify their inputs.

### 10.1 `extractor/extract.mjs` (Node 22+, unchanged)

```
node extractor/extract.mjs <repoRoot> --out <dir> [--exclude "p1,p2"] [--lang <language>]
```

`--exclude`: comma-separated gitignore-style patterns. `--lang`: keep only files of one
extractor language id (`python`, `typescript`, ...); omit for all. Exit 1 on any failed
step, with `extract.mjs failed: <reason>`. Requires `npm ci --ignore-scripts` once in
`extractor/`.

### 10.2 `pipeline/suggest_config.py`

```
python pipeline/suggest_config.py --scan <scan-output.json> --repo <name> [--out <config.json>]
```

Emits a **draft** v2 config: keys in this order — `repo`, `commit` (`"ADJUST"`),
`date` (`""`), `lang` (`"en"`), `categories`, `rules`, `fallback_category` (`"other"`),
`test_path_marker`, `test_category` (`"tests"`), `hop_path_prefixes` (the detected
monolith directories with a trailing `/`, sorted; else `[]`). It emits neither
`entry_points` nor `urls_files`. Without `--out` the JSON goes to stdout; with it,
stdout gets `categories=N rules=N dirs=N -> <out> (NKB)`. The `dir | files | language`
table and the "draft generated" notice go to stderr.

### 10.3 `pipeline/prep_data.py`

```
python pipeline/prep_data.py --es <es-output.json> --imports <im-output.json> \
    --config <config.json> [--ucs <usecases.json>] --out <data.json> [--strict]
```

| Flag | Required | Meaning |
|---|---|---|
| `--es` | yes | extract-structure output |
| `--imports` | yes | import-map output |
| `--config` | yes | repo config (section 3) |
| `--ucs` | no | use-case registry; without it `ucs = []` |
| `--out` | yes | `data.json` to write (parent directory must exist) |
| `--strict` | no | exit 3 if any hop was dropped |

stdout: `files=N imports=N ucs=N hops=N -> <out> (NKB)` where `hops` counts resolved
hops only. stderr: section 5.5.

### 10.4 `pipeline/prep_extra.py`

```
python pipeline/prep_extra.py --es <es-output.json> --imports <im-output.json> --out <extra.json> \
    [--config <config.json>] [--ucs <usecases.json>] [--repo <target repo root>] [--strict]
```

| Flag | Required | Meaning |
|---|---|---|
| `--es`, `--imports`, `--out` | yes | as above; `--out` is `extra.json` |
| `--config` | no | provides `entry_points.parsers` and `hop_path_prefixes`; without it no parser runs and no prefixes are tried |
| `--ucs` | no | registry for sources 2 and 3; without it only parsers contribute |
| `--repo` | when any parser declares `files` | target repo root the parser files are joined with; fatal `--repo: required because entry_points.parsers declares files` otherwise |
| `--strict` | no | exit 3 if any entry-point citation or parser route was dropped |

The v1 flag `--urls` is removed (argparse rejects it); use `entry_points.parsers`.

stdout: `entry_points=N calls: internal=N cross=N -> <out> (NKB)`.
stderr: section 5.5 for entry points, parser drops (6.3), and — whenever `N > 0` —
one breakdown line `entry points: <a> from parsers, <b> declared, <c> fallback, <d> duplicates merged`.

### 10.5 `pipeline/inject.py`

```
python pipeline/inject.py --template viewer/template.html --data <data.json> [--extra <extra.json>] --out <matryoshker.html>
```

stdout: `<out>: NKB`. Fatal: missing placeholder; `nfiles` mismatch (section 8).

### 10.6 `pipeline/build.py`

```
python pipeline/build.py --repo <target repo path> --config config/x.json \
    [--ucs data/x/usecases.json] [--out matryoshker.html] [--extract-out out] \
    [--lang <extractor language>] [--exclude "p1,p2"] [--template viewer/template.html] \
    [--node node] [--skip-extract] [--strict]
```

| Flag | Default | Meaning |
|---|---|---|
| `--repo` | required | target repository root (read-only) |
| `--config` | required | repo config |
| `--ucs` | none | use-case registry |
| `--out` | `matryoshker.html` | final HTML |
| `--extract-out` | `out` | directory for `scan/im/es-output.json`, `data.json` and `extra.json` (created if missing) |
| `--lang` | none | passed to `extract.mjs --lang` (source language filter — **not** the UI language, which is `config.lang`) |
| `--exclude` | none | passed to `extract.mjs --exclude` verbatim |
| `--template` | `<matryoshker root>/viewer/template.html` | viewer template |
| `--node` | `node` | Node executable |
| `--skip-extract` | off | reuse `<extract-out>/es-output.json` and `im-output.json` (fatal if missing) |
| `--strict` | off | forwarded to `prep_data` and `prep_extra` |

`<matryoshker root>` is the parent directory of `pipeline/`, resolved from
`build.py`'s own location, so the command works from any current directory.

Steps, as subprocesses (`sys.executable` for the Python ones), each announced on
stderr as `build.py: step k/4 <name>` with the child's stdout and stderr passed
through unchanged (so the same counters appear):

1. `node <root>/extractor/extract.mjs <repo> --out <extract-out> [--exclude ..] [--lang ..]`
2. `prep_data.py --es .. --imports .. --config .. [--ucs ..] --out <extract-out>/data.json`
3. `prep_extra.py --es .. --imports .. --config .. [--ucs ..] --repo <repo> --out <extract-out>/extra.json`
4. `inject.py --template .. --data .. --extra .. --out <out>`

Before step 1: `--repo` must be an existing directory; `<root>/extractor/node_modules`
must exist (else `build.py: extractor dependencies missing; run "npm ci --ignore-scripts" in extractor/`);
the Node executable must be found (else `build.py: node executable not found: <node>`).
A failing step stops the build with `build.py: step k/4 <name> failed (exit <code>)` and
**build.py exits with that same non-zero code**; its own failures exit 1. Nothing is
written to `--out` unless all four steps succeed.

---

## 11. Exit codes and stderr rules

| Code | Meaning | Who |
|---|---|---|
| 0 | success — **even when hops or entry points were dropped** | all |
| 1 | fatal input/usage error (`<flag>: <message>`), missing placeholder, index mismatch, unknown parser, build orchestration failure | all |
| 2 | command-line syntax error (argparse) | all Python scripts |
| 3 | `--strict` and at least one citation/route was dropped (`strict: N citations dropped`) | `prep_data`, `prep_extra`, `build` |
| other | propagated from a failed step | `build.py` |

stderr line kinds, each on its own line, no other prefixes:

- `warning: <message>` — deprecated key, unknown key/option, unknown status or lang,
  undeclared category, missing parser files;
- `UC <name>: k/n hops resolved` / `UC <name>: k/n entry points resolved` followed by
  indented `  dropped [<reason>]: <raw>` and `  unverified symbol [...]: <raw>` lines;
- `parser <name> (<file>): dropped [<reason>]: <what>`;
- `total: ...` summaries and the `entry points: ...` breakdown;
- `build.py: step k/4 <name>` and `build.py: ... failed (exit N)`;
- the Python-version warning from `_common.warn_python_version`.

Diagnostics are written through `_common.warn`, which degrades non-encodable characters
to `?` instead of crashing on narrow consoles.

---

## 12. Example end-to-end

```bash
cd extractor && npm ci --ignore-scripts && cd ..
python pipeline/build.py --repo ../library-catalog --config config/library-catalog.json \
    --ucs data/library-catalog/usecases.json --out matryoshker.html --lang python
```

Equivalent standalone steps:

```bash
node extractor/extract.mjs ../library-catalog --out out --lang python
python pipeline/prep_data.py  --es out/es-output.json --imports out/im-output.json \
    --config config/library-catalog.json --ucs data/library-catalog/usecases.json --out out/data.json
python pipeline/prep_extra.py --es out/es-output.json --imports out/im-output.json \
    --config config/library-catalog.json --ucs data/library-catalog/usecases.json \
    --repo ../library-catalog --out out/extra.json
python pipeline/inject.py --template viewer/template.html --data out/data.json \
    --extra out/extra.json --out matryoshker.html
```

---

## 13. Viewer requirements (`viewer/template.html`)

The viewer is repo-agnostic and reads only the embedded object of 8.1. This section is
the contract the viewer implementation follows.

The page issues exactly **one** external request: the Google Fonts `<link>` in its
`<head>`. The viewer MUST stay fully functional when that request fails (offline, or a
host CSP that blocks it) — every `font-family` declaration ends in a generic fallback and
no script, style or data comes from the network.

### 13.1 `meta` keys the viewer needs

`repo`, `commit`, `date` (header: `<repo> @ <commit> · <date>`), `lang` (13.2),
`categories` (3.2). `contract`, `nfiles`, `nimports`, `nucs` are ignored.

### 13.2 UI strings

All user-visible text comes from a `UI_STRINGS` table with two entries, `en` and
`pt-BR`, selected by `meta.lang`; an unknown or missing `lang` falls back to `en`, and a
key missing in one language falls back to the `en` text. The viewer sets
`document.documentElement.lang` to the selected value. Placeholders in braces are
substituted by the viewer. Keys and texts:

| Key | en | pt-BR |
|---|---|---|
| `search.placeholder` | `search file, class, method…` | `buscar arquivo, classe, método…` |
| `search.none` | `nothing found` | `nada encontrado` |
| `search.kind.file` | `file` | `arquivo` |
| `search.kind.class` | `class` | `classe` |
| `search.kind.method` | `method` | `método` |
| `search.kind.function` | `function` | `função` |
| `toggle.stars` | `stars` | `estrelas` |
| `panel.entry_points` | `Entry points` | `Pontos de entrada` |
| `kind.http` | `HTTP` | `HTTP` |
| `kind.command` | `Commands` | `Comandos` |
| `kind.event` | `Events` | `Eventos` |
| `kind.cli` | `CLI` | `CLI` |
| `kind.cron` | `Scheduled` | `Agendados` |
| `kind.other` | `Other` | `Outros` |
| `ep.route` | `route {route}` | `rota {route}` |
| `ep.ucs` | `use-cases: {names}` | `use-cases: {names}` |
| `panel.stars` | `Stars` | `Estrelas` |
| `star.stats` | `UC {uc}/{total} · imp {imp} · calls {calls}` | `UC {uc}/{total} · imp {imp} · cham {calls}` |
| `stars.none` | `No file qualifies yet — a file appears here once a use-case, an import or a call points at it.` | `Nenhum arquivo se qualifica ainda — um arquivo aparece aqui quando um use-case, um import ou uma chamada aponta para ele.` |
| `panel.usecases` | `Use-cases` | `Use-cases` |
| `badge.seam` | `seam` | `seam` |
| `uc.clear` | `clear selection (Esc)` | `limpar seleção (Esc)` |
| `uc.export` | `export local statuses` | `exportar status locais` |
| `uc.export_n` | `export local statuses ({n})` | `exportar status locais ({n})` |
| `uc.export_title` | `builds the JSON snippet of your local status changes to paste into the repo via PR` | `gera o snippet JSON das alterações locais de status para colar no repo via PR` |
| `crumb.context` | `Context` | `Contexto` |
| `crumb.packages` | `Packages` | `Pacotes` |
| `crumb.flow` | `Flow` | `Fluxo` |
| `crumb.entry_point` | `entry point: {label} ×` | `ponto de entrada: {label} ×` |
| `crumb.entry_point_title` | `clear the entry-point lens` | `limpar a lente do ponto de entrada` |
| `crumb.call_tree` | `call tree: {label} ×` | `árvore de chamadas: {label} ×` |
| `crumb.call_tree_title` | `clear the call tree root` | `limpar a raiz da árvore de chamadas` |
| `crumb.hidden` | `hidden folders: {n} ×` | `pastas ocultas: {n} ×` |
| `crumb.hidden_title` | `restore all hidden folders` | `restaurar todas as pastas ocultas` |
| `map.aria` | `Code map in nested levels: context, packages, file` | `Mapa do código em níveis: contexto, pacotes, arquivo` |
| `zoom.in` | `zoom in` | `aproximar` |
| `zoom.out` | `zoom out` | `afastar` |
| `zoom.fit` | `fit to screen` | `ajustar à tela` |
| `hint` | `drag the background = pan · drag a node = arrange (Context/Symbols; Packages with an active UC) · double-click drills down · Esc goes up` | `arraste o fundo = pan · arraste um nó = organizar (Contexto/Símbolos; Pacotes com UC ativo) · duplo-clique desce · Esc sobe` |
| `tip.file` | `{path} · {n} loc` | `{path} · {n} loc` |
| `ctx.files` | `{n} files` | `{n} arquivos` |
| `ctx.hide` | `hide this folder` | `ocultar esta pasta` |
| `ctx.imports_title` | `{a} → {b}: {n} imports` | `{a} → {b}: {n} imports` |
| `file.functions` | `functions` | `funções` |
| `file.calls_other` | `calls into other files` | `chama em outros arquivos` |
| `flow.call_tree_title` | `{label} — call tree (depth {d})` | `{label} — árvore de chamadas (prof. {d})` |
| `flow.empty` | `Select a use-case or an entry point to see the flow as a tree.` | `Selecione um use-case ou um ponto de entrada para ver o fluxo em árvore.` |
| `detail.title` | `Detail` | `Detalhe` |
| `detail.empty` | `Select a use-case or an entry point on the left, or click a file. Double-click a file to open its symbol map.` | `Selecione um use-case ou um ponto de entrada à esquerda, ou clique num arquivo. Duplo-clique num arquivo abre o mapa de símbolos dele.` |
| `detail.empty_short` | `Select a use-case or an entry point on the left, or click a file.` | `Selecione um use-case ou um ponto de entrada à esquerda, ou clique num arquivo.` |
| `detail.file` | `File` | `Arquivo` |
| `detail.lines` | `{n} lines` | `{n} linhas` |
| `detail.open_symbols` | `open symbol map ⌄` | `abrir mapa de símbolos ⌄` |
| `detail.call_tree_here` | `call tree from here` | `árvore de chamadas a partir daqui` |
| `detail.in_this_uc` | `In this use-case` | `Neste use-case` |
| `detail.classes` | `Classes` | `Classes` |
| `detail.functions` | `Functions` | `Funções` |
| `detail.ucs_here` | `Use-cases passing here ({n})` | `Use-cases que passam aqui ({n})` |
| `detail.ucs_here_note` | `linked by file — sibling routes of the same view share the list` | `vínculo por arquivo — rotas irmãs da mesma view compartilham a lista` |
| `detail.imports` | `Imports ({n})` | `Importa ({n})` |
| `detail.imported_by` | `Imported by ({n})` | `Importado por ({n})` |
| `detail.symbols` | `Symbols` | `Símbolos` |
| `detail.symbols_stats` | `{c} classes · {f} functions · {n} internal calls · {x} external` | `{c} classes · {f} funções · {n} chamadas internas · {x} externas` |
| `detail.symbols_help` | `Click a symbol to highlight its calls. Double-click a dashed box to jump to the called file. Esc goes back to packages.` | `Clique num símbolo para destacar as chamadas dele. Duplo-clique numa caixa tracejada salta para o arquivo chamado. Esc volta aos pacotes.` |
| `detail.symbol` | `Symbol` | `Símbolo` |
| `detail.calls` | `Calls ({n})` | `Chama ({n})` |
| `detail.called_by` | `Called by ({n})` | `Chamado por ({n})` |
| `detail.in` | `in` | `em` |
| `detail.usecase` | `Use-case` | `Use-case` |
| `detail.seam` | `crosses a seam` | `cruza seam` |
| `detail.status_title` | `local draft; make it official in the repo via PR (export local statuses)` | `rascunho local; oficialize no repo via PR (exportar status locais)` |
| `detail.local` | `· local` | `· local` |
| `detail.hops` | `Hops ({n})` | `Hops ({n})` |
| `detail.rules` | `Rules involved` | `Regras envolvidas` |
| `detail.entry_point` | `Entry point` | `Ponto de entrada` |
| `export.title` | `Export statuses` | `Exportar status` |
| `export.body` | `Local status changes ({n}). Apply them to the status field of the use-cases in the repo's data file (via PR) to make them official:` | `Alterações locais de status ({n}). Aplique-as ao campo status dos use-cases no arquivo de dados do repo (via PR) para oficializar:` |

Not localized (identifiers, not prose): the app title `Matryoshker`, the status values
(chips and `<option>` texts show the canonical value), category labels (they come from
the config), and the cluster key `(root)` for files at the repository root — it is also
a `localStorage` key, so it MUST be the same string in every language.

### 13.3 Entry points panel

- Reads `DATA.entry_points` (default `[]`). When the array is empty the whole section
  (header and list) is hidden — not collapsed, absent from the layout. When it is
  non-empty the section is rendered **open** (the header carries no `closed` class and
  the list is visible); clicking the header collapses and re-expands it.
- Grouped by `kind` in the order of `KINDS` (`http`, `command`, `event`, `cli`, `cron`,
  `other`), each group with a small heading `UI_STRINGS['kind.<kind>']` and its count;
  groups with no entries are not rendered. Entries keep the order of the array.
- Each entry shows `label` and, below it, `symbol` (when not null) and the base name of
  `files[i].p`. When `route` is set and differs from `label`, a third line shows
  `ep.route`. When `ucs` holds names other than `label` itself, a fourth line shows
  `ep.ucs` with at most three of them joined by ` · `, followed by `+N` for the rest
  (`+N` is a marker, not prose: it is not localized).
- Clicking an entry sets it active (`activeEp`): in the Context scene the lens dims
  every cluster outside the BFS-depth-2 reach of `entry_points[activeEp].i` and labels
  the entry cluster with the entry's `label`; in the Flow scene it becomes the Flow
  source (13.4) and the scene is redrawn in place; in the other scenes the viewer goes
  to Packages, selects and centers file `i`. Choosing an entry point clears `treeRoot`
  and leaves an active use-case untouched (13.4). The crumb `crumb.entry_point` (with
  the label) clears `activeEp` entirely — the lens, the sidebar highlight and, when the
  entry point was the Flow source, the Flow drawing, which then falls back (13.4).
  While the entry point is the Flow source, the Flow scene shows the call tree rooted at
  `i` titled `flow.call_tree_title` with `label = "<label> · <symbol>"` (or just
  `<label>` when `symbol` is null).
- The detail panel for an active entry point (title `detail.entry_point`) shows label,
  kind, the `ep.route` line when `route` differs from the label, symbol, the file link
  and — when `ucs` is non-empty — every name in `ucs` under a heading reusing
  `panel.usecases`, each name a link that selects that use-case. A name is looked up in
  `ucs[]` by exact match; a name with no match is rendered as plain text. This list is
  the exact "enters here" link, unlike `detail.ucs_here`, which is the file-level join.
- The viewer MUST tolerate `route` and `ucs` being absent (an `extra.json` written before
  this revision): a missing `route` reads as `null`, a missing `ucs` as `[]`.

### 13.4 Flow source and the call tree launcher

Two selections can be active at the same time: the use-case overlay (`activeUC`) and at
most one call-tree root — either an entry point (`activeEp`, 13.3) or a root launched
from the Symbols scene (`treeRoot`). The two call-tree roots replace each other: setting
one clears the other. The use-case overlay is independent of both, because the Context
scene deliberately combines them (13.3: the entry-point lens wins over the use-case
overlay there).

The Flow scene draws exactly one of them: the one chosen LAST. `flowPick`
(`'uc' | 'ep' | 'tree' | null`) records that choice; it is set when a use-case, an entry
point or a tree root is chosen, and it is not persisted. Before every render the viewer
re-points it at a selection that is still active: a `flowPick` naming a selection that has
been cleared falls back to whichever selection survives (entry point, then tree root, then
use-case), and to `null` when none does. The Flow crumb is visible exactly when
`flowPick !== null`, and `flowPick === null` is what draws `flow.empty`. Changing the Flow
source while the Flow scene is open redraws it and refits the view so the new chain or
tree is on screen; re-rendering the same source (a status change, for example) keeps the
current zoom and pan. Changing the status of the active use-case repaints its detail
panel and never changes the Flow source. The refit is recorded as done only once it
could actually be applied, so a Flow drawn while the map has no layout width (a hidden
or zero-sized container) is refitted on the next render instead of staying off-screen.

State `treeRoot = {i, symbol|null} | null`. The Symbols scene detail panel (file header
and, when a symbol is selected, the symbol panel) offers a button
`detail.call_tree_here` that sets `treeRoot` from the open file (and the selected symbol,
if any), clears `activeEp`, makes the tree the Flow source and opens the Flow scene. When
`treeRoot.symbol` is set, the root's children are the targets of `calls[i].x` edges whose
caller equals the symbol (deeper levels are file-level, as for entry points). The crumb
`crumb.call_tree` (label = base name, `:symbol` appended when present) clears `treeRoot`;
Flow then falls back to the active use-case, if there is one.

The Esc order does not depend on the Flow source and stays: search results → selected
symbol → Symbols/Flow scene → entry point or tree root → selected file → active use-case →
Context. `flowPick` is never an Esc rung of its own — Esc clears selections, and the Flow
source follows whatever is left.

### 13.5 Use-cases and status

- Use-case keys are the English ones of 7.4 (`name`, `actor`, `goal`, `seam`, `rules`,
  `status`, `hops`).
- `ST_CYCLE = ['human-verified', 'agent-verified', 'inferred', 'hypothesis', 'outdated']`;
  the CSS status classes are `.st.human-verified` … `.st.outdated`. A `localStorage`
  override whose value is not in `ST_CYCLE` is ignored (v1 drafts written with the
  Portuguese values simply stop applying).
- The export snippet is `{ "<name>": "<canonical status>" }`.
- `localStorage` keys are unchanged: `mtk:<repo>@<commit>:pos`, `:st`, `:hidef`.
- The Flow scene groups `hops` into levels with `groupHops()` per §5.1 and draws each
  level as a row, the siblings of a fan side by side. Fan edges are **solid** — same
  stroke as an ordinary step; a `"seam"` hop's *incoming* edges are **dashed**, and the
  two compose (a sibling that is also a seam is entered dashed while its peers are not).
  The role prefix is dropped from the drawn label — the token up to the first `:` — and
  the pipeline's `k` decides whether there is one to drop, so the vocabulary is not
  duplicated in the viewer.
- The **detail panel** is unaffected: it lists the registry's own lines in JSON order,
  prefix visible, because that is what an author needs when correcting the file.
- The map overlay applies the same level grouping, but it is file-level and dedups
  consecutive hops of the same file, so a fan whose siblings share the selector's file
  does not appear there (§5.1).

### 13.6 Scene layout (determinism)

The layout of every scene is a pure function of the embedded object. It MUST NOT read the
viewport (`clientWidth`/`clientHeight`, media queries), the wall clock or a random source,
and MUST NOT measure rendered text (`getComputedTextLength`, canvas metrics): the same
data must always produce the same map, because the drag offsets saved in
`mtk:<repo>@<commit>:pos` are deltas over these base positions.

- Packages and Context pack their boxes with a shelf-packing helper whose shelf width is
  derived from the packed content: `max(widest box, sqrt(total area × 1.8))`, where the
  total area sums `(w + column gap) × (h + row gap)` over the boxes. No constant caps the
  width of the map.
- A cluster box is as wide as the wider of its node grid and its label, the label
  contribution being capped (210 units in Packages, 240 in Context). Text width is
  estimated from the character count of the monospace label (East Asian wide code points
  count as two cells), never measured.
- A label that does not fit is clipped with `…` using the same estimate, so a label can
  never leave its own box and two labels can never overlap. The untruncated text stays
  available as an SVG `<title>`: on the label in Packages, and on the box group in
  Context, where it is emitted only when the name was actually clipped, so an untruncated
  box carries no native tooltip repeating the label it already shows.
- `fit()` and `centerOn()` are view operations, not layout: they may read the viewport.

### 13.6 Stars panel

The panel ranks the files something else points at ("most central"). It is derived
entirely from the embedded object; the pipeline computes nothing for it.

- Candidates are all files whose category is not `muted` (3.2).
- A candidate **qualifies** only when at least one of the three centralities is non-zero:
  `ucCount` (use-cases whose hops touch the file, derived from `ucs`), `impIn` (inbound
  edges in `imports`), `callIn` (inbound cross-file edges in `calls`). A file nothing
  points at never appears, whatever the list length.
- Qualifying files are sorted by `ucCount` desc, then `impIn` desc, then `callIn` desc;
  the sort is stable, so files equal on all three keep file order. At most **20** rows
  are rendered.
- The badge shows the number of rows actually rendered (never a padded 20).
- A row shows the file's base name; when a base name repeats inside the rendered list the
  row shows `<parent folder>/<base name>` instead, and the full path when that still
  repeats. The row's `title` is always the full path. A label too long for the panel wraps
  inside its row instead of overflowing it.
- When nothing qualifies — a legitimate state for a repository with no use-case registry
  yet and no resolvable imports or calls — the section stays visible with badge `0` and
  the list holds the single message `UI_STRINGS['stars.none']`.
- Clicking a row goes to Packages, selects and centers that file. The `stars` header
  toggle (halos in the Packages scene) is a separate feature driven by `ucCount` for
  every file and is not affected by the panel's filter.

---

## 14. JSON Schemas

- `schemas/config.schema.json` — draft-07, validates `config/<repo>.json` (section 3),
  strict about unknown keys, accepts the `data` alias and the deprecated `urls_files`.
- `schemas/usecases.schema.json` — draft-07, validates `data/<repo>/usecases.json`
  (section 4): a top-level array, each item requiring `name` or `nome`, typed known keys,
  status restricted to canonical values and v1 aliases, extra keys allowed.

The pipeline does not depend on a schema validator (stdlib only); the schemas exist for
editors, CI jobs that choose to install one, and as the reference for fixtures.

---

## 15. Changes from v1.3 (migration checklist)

| Area | v1.3 | v2 |
|---|---|---|
| Config `data` | key | `date` (alias `data` accepted) |
| Config `lang` | — | new, `"en"` default |
| Config `hop_path_prefixes` | hardcoded `v1/`, `src/` in `prep_data.make_file_finder` | config list, default `[]` |
| Config `entry_points.parsers` | — | new; `urls_files` deprecated → mapped with a warning |
| Config defaults | `outros` / `testes` | `other` / `tests` |
| Registry keys | `nome`, `ator`, `objetivo`, `regras_envolvidas` | `name`, `actor`, `goal`, `rules` (aliases accepted) |
| Registry file name | `data/<repo>/ucs.json` | `data/<repo>/usecases.json` (any path works via `--ucs`) |
| Status values | Portuguese | canonical English, aliases mapped |
| Route prefix | `/v1/` hardcoded for `router.register` | `route_prefix` per parser, default `""` |
| Spectacular views | hardcoded skip | `ignore_views` per parser, default `[]` |
| `data.json` `ucs[]` keys | `nome`, `ator`, `obj`, `regras` | `name`, `actor`, `goal`, `rules` |
| `data.json` `meta` | `data` | `date`, plus `lang`, `contract` |
| `extra.json` | `{endpoints, calls}` | `{nfiles, entry_points, calls}` |
| Embedded key `endpoints` | `[{route, view, i}]` | removed; `entry_points` `[{label, kind, i, symbol}]` |
| `prep_extra --urls` | flag | removed; `--config`, `--ucs`, `--repo`, `--strict` added |
| `prep_data` | — | `--strict`; symbol verification warnings |
| `build.py` | — | new single-command pipeline |
| Citation parsing | first separator splits, `.search` | citation anywhere, first resolving candidate, role kept without separator |
| stderr language | Portuguese | English, formats of section 11 |

### 15.1 Revisions within contract 2

`meta.contract` stays `2`: the embedded object only gains keys — none is removed or
retyped — and nothing branches on the number. A consumer written against the first v2
release keeps working, and a viewer of this revision reads an older `extra.json` by
defaulting `route` to `null` and `ucs` to `[]`.

| Date | Change |
|---|---|
| 2026-09 | Entry points: `route` and `ucs` added (6.1); the merge keeps every source's contribution instead of discarding all but the first, so a declared label survives a route parser (6.2); the sort gained `route` as its first text key; the panel shows the route and the declaring use-cases (13.3) with the new UI strings `ep.route` and `ep.ucs` (13.2). |
