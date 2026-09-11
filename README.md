# Matryoshker

**When this behavior changes, which parts of the system should I inspect?**

Matryoshker is a navigable code map that answers that question for a repository. It
combines two things that usually live apart:

- **What the code says**, extracted automatically: files, packages, imports, classes,
  functions and the calls between them. Deterministic, offline, no LLM.
- **What people know**, written down and versioned next to the code: *use-cases* — "a
  member borrows a copy of a title" — each one a short list of the symbols the behavior
  passes through, in order, with a one-line role for each, and an *epistemic status*
  saying how much that explanation has been checked.

The viewer draws the second on top of the first, at three nested zoom levels — packages,
files, symbols, like matryoshka dolls — plus a *Flow* scene that shows one behavior as a
numbered chain. Select a use-case and the map dims everything it does not touch.
Click a file and it lists every use-case that passes through it. That is the whole idea:
the automatic graph tells you what *can* call what; the curated use-cases tell you what
*matters* and why, and say how sure anyone is.

Everything repo-specific — categories, path rules, route parsers, the use-cases
themselves — lives in `config/` and `data/`, never in the viewer.

## Try the live demo

**[devanomaly.github.io/matryoshker](https://devanomaly.github.io/matryoshker/)** — the
bundled `examples/sample-drf` fixture (a small Django/DRF library-lending app) with its
five use-cases, rebuilt by `.github/workflows/pages.yml` on every push to `main`.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/demo-use-case-dark.png">
  <img src="docs/images/demo-use-case-light.png" width="1440"
       alt="The Matryoshker viewer with the use-case 'Member borrows a copy of a title' selected. The Packages scene shows package boxes with file squares; the six files the use-case passes through carry numbered badges joined by arrows, everything else is dimmed. The left sidebar lists entry points grouped by kind and the use-cases with status chips; the right panel shows the use-case's actor, its status dropdown set to human-verified, the seven hops with their roles, and the business rules involved.">
</picture>

*The Packages scene of the demo with "Member borrows a copy of a title" selected. The
badges number the files in hop order; the right panel lists the hops themselves. Captured
from a local build of the fixture at 1440×900 (light and dark variants follow your
color-scheme preference).*

The header of the demo reads `sample-drf @ 0000000 · 2026-09-05`: those two values come
from `config/example.json`, typed by hand, not read from git (see
[What the labels do and do not tell you](#what-the-labels-do-and-do-not-tell-you)).

### A five-minute tour

Every control below exists in the demo under exactly this name.

1. **Pick a use-case.** In the left sidebar, open *Use-cases* and click *Member borrows a
   copy of a title*. The map (scene *Packages*) dims every file the use-case does not
   touch and numbers the ones it does, in hop order. The right panel shows the actor, the
   goal, the status dropdown, the *Hops* list and the *Rules involved*. Both come from the
   registry file `examples/sample-drf/usecases.json`; nothing here was extracted.
2. **Read its Flow.** Click *Flow* in the breadcrumb. The same use-case is now a vertical
   chain, one box per hop: file, symbol, role. This is the curated explanation, drawn
   hop by hop. Two hops in the same file get one badge on the map but two boxes here.
3. **Zoom out, zoom in.** *Context* shows packages as boxes with aggregated import
   edges. Back in *Packages*, click a file square (say `loan_service.py` under
   `lending/services`) — the right panel shows its classes, imports and, under
   *Use-cases passing here*, every use-case whose hops touch it. That reverse index is the
   answer to the opening question. Then *open symbol map ⌄* (or double-click the square):
   the *Symbols* scene draws its classes and functions as pills with the **extracted**
   call edges, and the dashed boxes on the right are the other files it calls into.
   Click a pill — `renew`, for example — and the panel lists *Calls* and *Called by*
   from the extraction. This is the second source of information: what the code says,
   with no curation. Comparing it with the hop list is how a reviewer checks a use-case.
4. **Follow an entry point.** In *Entry points*, click *POST /api/books/{id}/borrow*.
   The breadcrumb gains `entry point: … ×`, the *Flow* scene switches to a **call tree**
   rooted at the view (depth 3, breadth-first over extracted calls), and the right panel
   lists the use-cases that enter there. A call tree and a use-case Flow look alike but
   are different things: the tree is mechanical and exhaustive up to its depth, the
   use-case is a person's selection. Click the `×` on the crumb and Flow falls back to the
   use-case. *call tree from here* in the Symbols panel does the same from any file or
   symbol.
5. **Read the status.** Each use-case carries a chip: `human-verified`,
   `agent-verified`, `inferred`, `hypothesis` or `outdated`. The dropdown in the panel
   changes it **locally** (marked `· local`, kept in your browser's `localStorage`);
   *export local statuses* turns those drafts into a JSON snippet to apply to the
   registry in a pull request. The registry file is the only shared truth — see the
   section on labels below before trusting a chip.

Esc goes up one level at a time; the hint line at the bottom of the map lists the
mouse gestures.

## Build it yourself

Prerequisites: Python 3.10+, Node 22+, git.

```bash
git clone https://github.com/devanomaly/matryoshker.git && cd matryoshker
cd extractor && npm ci --ignore-scripts && cd ..        # the only step that touches the network
python pipeline/build.py \
    --repo examples/sample-drf --config config/example.json \
    --ucs examples/sample-drf/usecases.json --out matryoshker.html --lang python
```

Open `matryoshker.html` in a browser. The build prints one counter line per step; the
one to read is `files=25 imports=33 ucs=5 hops=33` — `hops` counts the hops that resolved
against the extraction, and any hop that did not is reported on stderr right above it.
On Windows `python` may resolve to an older interpreter; `py -3` is the safe spelling.

[QUICKSTART.md](QUICKSTART.md) covers pointing the same command at your own repository,
building without a use-case registry, which output paths you control, and the
four pipeline steps standalone.

## Map your first use-case

[docs/first-use-case.md](docs/first-use-case.md) walks through adding one use-case to the
bundled fixture end to end: picking a behavior, reading the files, writing the registry
entry, choosing the granularity of the hops, choosing a status honestly, building the
map, checking the result in the viewer, and what a reviewer does with it. The entry it
writes is real and builds clean. Read it before writing your first entry for your own
repository; [CONTRIBUTING.md](CONTRIBUTING.md) has the grammar reference and
[docs/data-contract.md](docs/data-contract.md) every field.

## What the labels do and do not tell you

Verified against the current pipeline and viewer; the details, with commands, are in
[CONTRIBUTING.md](CONTRIBUTING.md#what-the-status-labels-establish).

- **A status is a claim by whoever wrote the registry, kept by review, not by code.**
  `human-verified` is meant to enter only when a person re-read the hops. Nothing in
  the pipeline enforces that: the registry file can say `human-verified` directly, the
  viewer's dropdown offers it to anyone as a local draft, and the export snippet is
  plain JSON. The safeguard is the pull request that applies it.
- **No reviewer identity, date or evidence is recorded.** The contract has no field for
  them; the viewer shows only the status value. A team that wants them can add its own
  keys to a registry entry (extra keys are kept and ignored by the pipeline) or rely on
  git history of the registry file.
- **Changing the code does not change a status.** The pipeline copies `status` verbatim
  on every build. What it does detect, on stderr, is a hop whose **file** no longer
  exists (the hop is dropped, and `--strict` turns that into exit code 3) and a hop
  whose **symbol** is no longer declared in that file (a warning; the hop still counts
  and still draws, and `--strict` does not fail on it). A method that was renamed
  therefore shows up as a warning you must read, under a status that still says
  `human-verified`.
- **The commit and date in the header are config values**, typed into
  `config/<repo>.json`. Nothing reads git. Updating them when you rebuild is part of
  the maintenance routine, not automatic.
- **Viewer status changes are drafts in one browser.** They live in `localStorage`
  under the repo and commit from the config, never reach the file, and become real only
  when someone pastes the exported snippet into the registry and merges it.

None of this makes the labels useless: it makes them **reviewable**. A registry entry
is a small, versioned, diffable claim, and the map gives a reviewer the extracted call
edges to check it against. The tool does not verify authorship, prove that a use-case
is complete, or keep it fresh on its own.

## What is extracted, what you supply

| Comes from the extraction (automatic) | Comes from you or an agent (curated) |
|---|---|
| files, line counts, packages (first two path segments) | category names and the path rules that assign them (`config/`) |
| import edges between files | use-case name, actor, goal, status |
| classes, methods, functions with line ranges | the hops: which symbols, in what order, one role each |
| call edges, resolved by name heuristics (same file, then imports) | business rules, tests, failure paths (documentation-only fields) |
| HTTP routes, when a route parser is configured (Django/DRF today) | declared entry points (a command, an event, a scheduled job, a route the parser missed) |
| the *Stars* ranking, the reverse index file → use-cases, the call trees | the header's `commit` and `date` |

## What the viewer offers

| Scene | C4 level | What it shows |
|---|---|---|
| **Context** | C1 | packages as boxes + aggregated import edges (thickness = import count); the entry-point lens dims what a depth-2 BFS does not reach |
| **Packages** | C2 | every file in package clusters, colored by category; clusters are packed into a compact grid whose size comes from the data, not from the window |
| **Symbols** | C3–C4 | double-click a file: classes/functions as pills + internal and cross-file calls as edges |
| **Flow** | — | only appears with a use-case or entry point active, and draws whichever of them you selected last: UC → numbered vertical chain of hops, fanned out where the registry marks siblings with `branch:`; entry point (or a call tree launched from Symbols) → top-down call tree |

More:

- use-case overlay on the map (dim + numbered badges + arrows in hop order);
- an entry points panel in the sidebar (HTTP routes, commands, events, CLI, scheduled
  jobs) and a `entry point: … ×` crumb to clear the lens; each entry showing the parsed
  route it belongs to (when there is one) and the use-cases that enter there;
- a reverse index **file → use-cases**: clicking a file lists the UCs that pass through
  it (linked by file, not by route) and jumps back to each one;
- a status dropdown in the UC panel (local draft, see above);
- search by file/class/method and a toggle to reveal `muted` categories (tests, hidden
  by default);
- Obsidian-style node dragging: Context and Symbols always, Packages only with an active
  UC. Layout is saved to `localStorage` per commit — **per UC** in Packages, per scene
  elsewhere;
- light/dark following the host environment (system or the host's `data-theme`; the
  viewer has no theme switch of its own);

all in a single self-contained HTML file (CSP-safe, no external dependencies besides the
Google Fonts `<link>`). That `<link>` is the page's only network request: block it, or
open the file offline, and the map still works in full — only the typefaces fall back to
the system stack.

### The DDD-first path

`config/example-ddd.json` builds the same fixture without any route parser
(`entry_points.parsers` is absent). Entry points then come entirely from the use-case
registry: each use-case's declared `entry_points` (an HTTP route, a command, an event…)
or, absent that, its first resolved hop as a fallback (section 6 of the data contract).
This is the path for projects that write use-cases before routes exist, or that never
expose HTTP at all:

```bash
python pipeline/build.py \
    --repo examples/sample-drf --config config/example-ddd.json \
    --ucs examples/sample-drf/usecases.json --out matryoshker-ddd.html --lang python
```

## Pipeline

```
target repo (read-only)
  └─ extractor/extract.mjs   (vendored derivative of Understand-Anything: tree-sitter,
       offline, no LLM, one command — see extractor/NOTICE)
  └─ pipeline/prep_data.py   (repo config + versioned use-case registry)
  └─ pipeline/prep_extra.py  (entry points + resolved call edges)
  └─ pipeline/inject.py      (data embedded into viewer/template.html)
  → matryoshker.html (self-contained; open in a browser or publish as an artifact)
```

`pipeline/build.py` runs all four steps with one command. `pipeline/suggest_config.py` is
the optional shortcut for a repo's first `config/<repo>.json`: it groups
`scan-output.json`'s directories by file count and emits a **draft** `categories`/`rules`
block to review.

## Epistemic status tags

Every use-case carries a **versioned** `status` in the data file:

`human-verified` · `agent-verified` · `inferred` · `hypothesis` · `outdated`

House rule: **`human-verified` only enters by human gesture** — agent pipelines stop at
`agent-verified`. The rule is enforced by review, not by the tool (see above). In the
viewer, the status dropdown in the UC panel changes a local draft (`localStorage`,
marked `· local`); the *export local statuses* button opens the JSON
`{use-case name: status}` snippet to make it official in the versioned registry via a
PR. The repository is always the source of truth.

## Data contract

Every file format, CLI flag and module boundary in the pipeline is specified in
[docs/data-contract.md](docs/data-contract.md) — read it before writing a config, a
use-case registry, or an entry-point parser. The JSON Schemas in
[schemas/](schemas/) (`config.schema.json`, `usecases.schema.json`) exist for editor
support and for CI jobs that choose to install a validator; the pipeline itself has no
schema-validator dependency.

**Role prefixes on hops.** A hop's role may open with `branch:` / `ramo:` (a sibling: one
of N alternatives chosen at the preceding hop) or `seam:` / `costura:` (the hop crosses a
seam — disk, HTTP, subprocess, a human step). A *consecutive* run of `branch:` hops is
one level of the flow, drawn side by side between its selector and its reconvergence, and
**numbering is by level**: the siblings are `Na`, `Nb`, `Nc`. A registry that uses no
prefixes has one hop per level and keeps its `1..N` chain unchanged. `seam:` draws that
hop's incoming edges dashed. The registry format does not change — the prefix is ordinary
role text, and the pipeline derives an optional `ucs[].hops[].k` from it (section 5.1 of
the data contract).

## Known limits

- The only bundled entry-point parser is Django/DRF-specific
  (`router.register` + `path(...as_view)`); other frameworks need a new parser
  (section 6.3 of the data contract). Without one, entry points come only from the
  registry.
- Extraction requires Node 22+; the extractor is vendored under `extractor/` (a minimal
  derivative of Understand-Anything's phase-1, MIT, commit pinned in `extractor/NOTICE`
  — no external clone, no TypeScript build step at use time). QUICKSTART lists the
  languages it parses.
- Call edges are resolved by name heuristics (same file → imports); dynamic or
  reflective calls do not appear.
- Call-edge resolution is tuned for Python: the skipped-names list is Python builtins and
  exceptions, and `self` is the only receiver stripped from a call expression. For the
  other languages the extractor parses, edges are noisier (their builtins are not
  skipped) or thinner (`this.method()` resolves on `this`). Files, imports, symbols and
  use-case hops are language-neutral; only the call edges carry this bias (section 8 of
  the data contract).
- Hop fan-out, in this version: **no nesting** (a `branch:` hop cannot open a sub-fan);
  **two independent adjacent lateral alternatives merge into one fan of two** — adjacency
  is all the grammar has, so put a non-branch hop between them to keep them apart; **a
  sibling that actually terminates mid-chain is still drawn reconverging** (the registry
  has no way to say otherwise); and **the map overlay is file-level**, dedupping
  consecutive hops of the same file, so a fan whose siblings live in the selector's own
  file does not appear there — the Flow panel, which is hop-level, does show it.
- A map is a snapshot of one build. Keeping it fresh per branch requires generating the
  HTML in CI and hosting it; the bundled Pages workflow does that for `main` of this
  repository only.
- Freshness of the registry is a human routine (see the labels section and
  [CONTRIBUTING.md](CONTRIBUTING.md#keeping-a-registry-current)); the CI gate that would
  re-check citations on every PR is on the roadmap, not implemented.

## Where it sits among other tools

Pieces of this exist elsewhere: static structure maps (Sourcetrail, Understand-Anything,
which the extractor derives from), hotspot and behavior analysis (CodeScene, AppMap),
and the diagramming product that came closest to overlaying curated flows on an
extracted map (CodeSee, discontinued in 2024). In the prior-art scan we did in mid-2026 we
did not find a maintained tool combining an automatically extracted graph, adjustable
granularity and a versioned, statused use-case overlay in one file; we may have missed
one, and the point is not novelty. The pattern in this category is that standalone
products die and open formats outlive them, so Matryoshker is a thin curation and
visualization layer over plain JSON files you keep in your own repository.

## Roadmap

1. A use-case composer inside the viewer: a guided form (name/actor/goal/status) with
   hops built by **autocomplete over the graph itself** (file:symbol validated at
   selection time — this removes the unverified-symbol problem at the source), producing
   a JSON snippet ready for a PR against the registry.
2. A CI freshness gate for the registries (hops/citations re-resolved against the graph
   on every PR).
3. Per-branch generation in CI (real branch-preview builds).
4. Entry-point parsers for more frameworks.

See [docs/ROADMAP.md](docs/ROADMAP.md) for these as candidate issues. Documentation in
Portuguese: [docs/pt-BR/README.md](docs/pt-BR/README.md).

## Attribution

The extractor (`extractor/`) is a minimal derivative of the phase-1 (deterministic
structural extraction) portion of
[Understand-Anything](https://github.com/Egonex-AI/Understand-Anything) by Egonex-AI,
licensed under MIT. Full provenance, the files that are byte-identical to upstream, and
the re-vendoring procedure are in [extractor/NOTICE](extractor/NOTICE).

## License

MIT — see [LICENSE](LICENSE).
