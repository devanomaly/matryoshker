# sample-drf — a library lending fixture

A deliberately small Django + Django REST Framework project modelling a
public library: authors, books, physical copies, members, loans,
reservations and overdue notices.

## What this is for

This directory is a **fixture**, not an application. It exists so that
Matryoshker has a stable, public, and self-contained repository to map:

- the golden extraction in `tests/golden/` is generated from this tree;
- the example configuration and the hosted demo are built from it;
- the pipeline tests assert against its structure.

**It is not runnable.** Django and DRF are not installed anywhere in this
repository and must never become a dependency of it. Every file is valid
Python 3 and is checked with `python -m py_compile`, which is all the
extractor needs — it parses source, it never imports it.

## Layout

```
manage.py                       Django entrypoint (never executed)
library/                        project package
  settings.py                   minimal settings
  urls.py                       root routes: api/, health/, docs/
catalog/                        HTTP-facing app
  models.py                     Author, Book, Copy
  serializers.py                DRF serializers
  views.py                      BookViewSet, AuthorViewSet, HealthView
  urls.py                       DRF router + one direct route
  services/catalog_service.py   catalog queries and copy bookkeeping
lending/                        domain-first app, no HTTP surface
  models.py                     Member, Loan, Reservation
  domain/policies.py            loan limits, due dates, fines (pure)
  services/loan_service.py      checkout, renewal, return
  services/overdue_service.py   overdue detection and follow-up
  handlers/place_reservation.py PlaceReservationHandler
  handlers/return_book.py       ReturnBookHandler
  tasks/notify_overdue.py       overdue notice delivery
tests/                          unittest modules
```

## Why it is shaped this way

The fixture is built to produce an interesting map rather than a minimal
one, so the layering is explicit:

- **views call services and handlers**, never the ORM directly;
- **handlers call services and the domain policies**;
- **services call models and the notice task**;
- **`lending/domain/policies.py` calls nothing** — it is the leaf every
  other layer eventually reaches, and the only module the test suite can
  exercise without Django.

Cross-file edges are written as absolute imports
(`from catalog.services.catalog_service import CatalogService`) because
the extractor resolves imports statically, from the source text alone.

Two routes in `library/urls.py` are there for the endpoint parser: one
`include()` of the app router, and a `docs/` schema route that a real
configuration is expected to filter out by name, since generated API
documentation is tooling rather than product surface.

## Regenerating the golden extraction

```
node extractor/extract.mjs examples/sample-drf --out tests/golden --lang python
```

Keep only `scan-output.json`, `im-output.json` and `es-output.json`.
