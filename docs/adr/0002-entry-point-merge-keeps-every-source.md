# ADR 0002 — The entry-point merge keeps every source's contribution

Date: 2026-09-07 · Status: accepted · Amends: ADR 0001 (decision 1)

## Context

ADR 0001 gave entry points three sources — route parsers, use-case declarations and a
first-hop fallback — merged by deduplicating on `(i, symbol)` where the first source
wins, then sorted by `(kind, label)`. "First source wins" was implemented as *discard
the whole later entry*: only the `label`, `kind`, `i` and `symbol` of the first
occurrence survived, and nothing the other sources knew was kept.

That loses information a human wrote. Built from the same registry
(`examples/sample-drf/usecases.json`) with two configs:

- with `config/example-ddd.json` (no parser) the use-case *Member borrows a copy of a
  title* declares `http: catalog/views.py:BookViewSet — POST /api/books/{id}/borrow`,
  and the panel shows `POST /api/books/{id}/borrow`;
- with `config/example.json` (the `django-drf` parser on `catalog/urls.py` and
  `library/urls.py`) the parser emits `(i=6, BookViewSet)` labelled `/api/books` first,
  the identical key from the declaration is discarded whole, and the panel shows
  `/api/books` instead. The label the author wrote is gone from the panel, from the
  `crumb.entry_point` crumb, from the Context lens cluster label and from the Flow
  call-tree title — all four read `label`. The borrow use-case is left with no entry
  point of its own, because `collect_from_usecases` decides the fallback from the
  *resolved* declared entries, before the merge throws that entry away.

Turning a parser on destroyed information. The panel also listed `/api/books`
(symbol `BookViewSet`, from the parser) next to `GET /api/books` (symbol
`BookViewSet.list`, declared by another use-case): two naming conventions for one route,
with nothing recording that they belong together, and nothing anywhere recording which
use-case enters at a given entry point.

## Decision

Replace "first occurrence wins, the rest are discarded" with a **field-level merge**.
The dedup key stays `(i, symbol or "")`; each group of entries becomes **one** entry
point that keeps what every source knows:

1. **Source precedence for the label and the kind is `declared > parsers > fallback`.**
   A hand-written declaration wins the `label` over a generated route; a fallback label
   (the use-case name) never overrides either. The `kind` is the first one that is not
   `"other"` in that same precedence order, so an unprefixed declaration does not demote
   a parser's `http`, while an explicit `command:` on the same symbol does.
2. **Two new keys carry what used to be discarded.** `route` holds the label a route
   parser produced for the key — or, for a `Class.method` symbol, the one it produced
   for `Class` — and is `null` when no parser contributed. `ucs` holds the names of the
   use-cases that declared the entry point or contributed it as a fallback, in registry
   order, each name at most once. Registry order is not the order the merge meets the
   contributions — it walks the whole declared list before the whole fallback one — so
   each contribution carries its use-case's position in the loaded registry in the
   internal key `ucpos`, and `ucs` is sorted on that. It matters because the panel keeps
   only the first three names.
3. **The sort becomes `(KINDS.index(kind), route or label, label, symbol or "", i)`**,
   superseding ADR 0001's `(kind, label)`. Sorting on the route first keeps the entry
   points of one parsed route together: the viewset the router mounted and each of its
   methods a use-case declared, instead of scattering them by their labels.
4. **The viewer shows both facts.** A panel entry gains a `route …` line when the route
   says more than the label already does, and a `use-cases: …` line (at most three names,
   then `+N`); the entry-point detail panel shows the route and every declaring
   use-case as a link that selects it. Two new UI strings, `ep.route` and `ep.ucs`.

The parser interface (ADR 0001 decision 2) is unchanged — a parser still returns only
`label`/`kind`/`path`/`symbol`, and `prep_extra.py` derives the route from its label —
so third-party parsers keep working. `meta.contract` stays `2`: the embedded object only
gains keys, none is removed or retyped, and nothing branches on the number. The revision
is recorded in `docs/data-contract.md` section 15.1.

Rejected alternatives:

- **Keep first-wins and reorder the sources (declared before parsers).** Cheapest, and
  it fixes the label — but it destroys the parser's route instead of the human's label:
  the same bug with the victim swapped. The two-conventions symptom gets worse, since
  the route knowledge then disappears entirely.
- **Change the dedup key to `(i, symbol, label)`, or drop the dedup.** Both `/api/books`
  and `POST /api/books/{id}/borrow` would survive as two entries for one viewset —
  exactly the noise complained about — and the two identical `/api/health/` parser hits
  (both `urls.py` files match under `route_prefix: "/api"`) would stop collapsing.
  Keying on `i` alone over-merges; keying on `(i, class-of-symbol)` swallows the
  method-level entries a use-case declared.
- **A nested panel level**, with the parsed route as a group header and its methods
  indented. A second grouping dimension that is only sometimes present (no parser ⇒ no
  routes), complicating the `data-ep` bookkeeping and the Esc/active-entry logic for a
  reading benefit that `route` plus the sort already gives with a flat panel.
- **Forcing the parser and the declaration onto one label convention.** A parser cannot
  know the HTTP method of a router-registered viewset, and imposing a convention on
  hand-written labels contradicts the contract's own label precedence (section 5.2).
- **Bumping `meta.contract` to 3.** The change is additive and nothing branches on the
  number; a revision note inside contract 2 is the honest record.
- **Carrying use-case *indices* in `ucs` instead of names.** Indices would couple
  `extra.json` to `data.json`'s ordering across two independent script invocations that
  may be given different `--ucs` files; a wrong index points silently at the wrong
  use-case, a wrong name simply fails to resolve into a link.

## Consequences

- A registry shows the same entry-point labels with and without a route parser. Turning
  a parser on now adds route knowledge instead of replacing what a human wrote.
- ADR 0001's consequence *"two use-cases starting at the same file and symbol share one
  fallback entry point, labelled with the first use-case's name"* still holds, but is no
  longer lossy: both names appear in `ucs` and the panel says so.
- The panel gains an explicit link from an entry point to the use-cases that enter
  there. Until now the viewer's only file↔use-case join was `detail.ucs_here`, which is
  by file and therefore shares its list between sibling routes of one view.
- A class-level parser route and a method-level declaration on the same class stay two
  entry points — two different places to enter — but share a `route`, so the panel lists
  them together and labels each with the route it belongs to.
- Panel entries grow from two lines to at most four, and `extra.json` grows by the route
  and the use-case names it now carries.
- Downstream consumers reading `entry_points[].label` and expecting a parser's route
  must read `route` instead; the panel order changes for any repo running a parser.
  Nothing persisted in `localStorage` indexes entry points, so no saved layout breaks.
- A future parser that wants to contribute more than a route label needs no interface
  change for the route itself, but any further field would be a new contract revision.
