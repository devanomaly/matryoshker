# Map your first use-case

This walkthrough adds one use-case to the bundled fixture, `examples/sample-drf`, from
the first question to the reviewed pull request. Everything in it was run against the
current pipeline; the counters and stderr lines quoted are the ones you should see.
Budget about thirty minutes, with the demo build from the README already working.

Two kinds of guidance are mixed below and it matters which is which:

- **Contract** — what the pipeline requires or does. Stated as such, with a pointer to
  [`docs/data-contract.md`](data-contract.md).
- **Practice** — how this project writes registries so that they stay checkable. Good
  defaults, not rules the tool enforces.

## 0. What a use-case entry is

A use-case is one behavior an actor gets from the system, explained as the ordered list
of symbols it passes through — the *hops* — each with a one-line role. It is a claim
written by a person or an agent, stored as JSON in the repository, and drawn by the
viewer on top of the graph the extractor produced. The pipeline checks that every hop's
**file** exists in the extraction and warns when the **symbol** does not; it does not
check the order, the roles, or whether the list is complete. That is what review is for.

## 1. Pick the behavior

**Behavior:** a member renews a loan before it is due.
**Actor:** library member. **Goal:** keep a copy for one more loan period when nobody is
waiting for the title.

Why this one: it is a real behavior with a business rule of its own (renewals are capped
and blocked by a queue), it is small, and the fixture's registry does not have it yet.
The five entries already in `examples/sample-drf/usecases.json` are the ones you see in
the demo.

Practice: start from a behavior a stakeholder would name, not from a module. "Renew a
loan" is a use-case; "`LoanService`" is not.

## 2. Read the code, with the map open

Build the fixture as in the README and open the map. Type `renew` in the search box:
the result list shows the function `can_renew` in `policies.py`, the method
`LoanService.renew` in `loan_service.py`, and three test symbols. Click the method; the
*Symbols* scene opens on `lending/services/loan_service.py` with `renew` selected, and
the right panel says:

```
Symbol
lending/services/loan_service.py
renew
Calls (2)
  can_renew in policies.py :70
  loan_period_days in policies.py :72
Called by (0)
```

That panel is the extraction talking: `renew` calls two policy functions, and **nothing
in the fixture calls `renew`** — no view, no handler. Keep that fact; it decides the
status later.

Now read the files. These were inspected for this entry:

| File | What was read | What it contributes |
|---|---|---|
| `lending/services/loan_service.py` | `LoanService.renew` | the decision (`can_renew`), the due-date move, the save on the loan |
| `lending/domain/policies.py` | `can_renew`, `loan_period_days`, `MAX_RENEWALS` | the rule: no open reservation, fewer than two renewals; the period per tier |
| `lending/models.py` | `Loan` fields `due_date`, `renewal_count` | where the state lands |
| `catalog/views.py`, `lending/handlers/*.py` | searched for a caller of `renew` | none — there is no entry point |
| `tests/test_policies.py` | `RenewalTests` | covers `can_renew` only, not the service method |

## 3. Write the entry

Append this object to the array in `examples/sample-drf/usecases.json` (after the last
entry, inside the closing `]`):

```json
{
  "name": "Member renews a loan before it is due",
  "actor": "Library member",
  "goal": "Keep a copy for one more loan period when nobody is waiting for the title",
  "hops": [
    "lending/services/loan_service.py:LoanService.renew — refuses when the title has a queue or the renewals are used up",
    "lending/domain/policies.py:can_renew — the rule: no open reservation and fewer than MAX_RENEWALS",
    "lending/domain/policies.py:loan_period_days — how far the due date moves, by member tier",
    "lending/models.py:Loan — stores the new due date and the renewal count"
  ],
  "async_legs": [],
  "failure_paths": [
    "a reservation is open for the title -> renew returns None, nothing is saved",
    "renewal_count is already MAX_RENEWALS -> renew returns None, nothing is saved"
  ],
  "rules": [
    "no renewal while another member is waiting for the title",
    "at most two renewals per loan (MAX_RENEWALS)"
  ],
  "tests": ["tests/test_policies.py::RenewalTests"],
  "seam_crossing": false,
  "status": "inferred",
  "notes": "Nothing in the fixture calls LoanService.renew: no view, no handler. The hops are read from the code; the actor is the intended one, not an observed caller."
}
```

Contract, so you know what is load-bearing (data contract §4.1):

- only `name` is required, and it must be unique in the file;
- the pipeline reads `name`, `actor`, `goal`, `entry_points`, `hops`, `rules`,
  `seam_crossing`, `status`. `async_legs`, `failure_paths`, `tests`, `notes` and any
  other key are kept in the file and ignored — documentation for the next reader;
- a hop is `"<path/file.ext>[:<Symbol>] — <role>"` with an em dash (§5.1). Paths are
  relative to the mapped repository root;
- `status` missing means `inferred`.

Practice: write the role in the present tense, under about fourteen words, saying what
that hop *decides or does for this behavior* — not what the function does in general.
Fill `failure_paths` and `tests` while the code is open; they cost little now and a lot
later.

## 4. Why each hop belongs, and what was left out

| Hop | Why it is a hop |
|---|---|
| `LoanService.renew` | the behavior enters here; it owns the decision and the write |
| `policies.can_renew` | the rule that can refuse the behavior; a reader changing the cap must find this |
| `policies.loan_period_days` | the second rule, deciding *how much* the due date moves; a different concern from the first |
| `models.Loan` | where the state lands; a reader asking "what changed in the database" stops here |

Left out on purpose:

- `loan.save(update_fields=[...])` — an implementation detail of the last hop, visible
  in the code the moment you open it;
- `timedelta` — a library call, not a decision;
- the queue check `loan.copy.book.reservations.filter(state="open").exists()` — an ORM
  expression with no symbol of its own; it is folded into the role of hop 1 ("has a
  queue") rather than cited as a hop;
- `loan_period_days` reading `LOAN_PERIOD_BY_TIER` — one level below what a reader
  needs; the Symbols scene shows it anyway.

Practice, the granularity rule this project uses: **one hop per boundary crossed or
decision made**. Cite a symbol when a reader who wants to change the behavior would have
to open it; skip it when the Symbols scene already shows it for free as an internal call.
Four to eight hops is the usual size. If you find yourself listing every function on the
path, you are transcribing the call tree — the viewer already draws that from the
extraction (*call tree from here*); the use-case is worth writing because it is a
selection.

Two hops in the same file (`policies.py`) are fine: the Flow scene draws both, and the
map overlay merges them into one badge on that file. That merge is a viewer rule, not a
reason to drop a hop.

## 5. Choose the status honestly

The entry says `inferred`. Reasoning, against the definitions in data contract §4.2:

- not `hypothesis`: every hop was read in the code and the extraction agrees with the
  call structure (`renew` → `can_renew`, `loan_period_days`);
- not `human-verified`: that label is reserved, by this project's practice, for a
  **second** reader who re-reads the hops and blesses them in review. The author does
  not self-bless. There is also an open question the author cannot close alone: nothing
  calls `renew`, so "a member renews" is the *intended* actor, not an observed one. That
  is written in `notes`, where the reviewer will see it;
- not `agent-verified`: no agent pipeline produced or checked this entry. If one did, it
  stops at this value — an agent never writes `human-verified` (CONTRIBUTING.md).

Nothing in the tool checks any of this: the file could say `human-verified` and the
pipeline would copy it as written. The status is a claim you make to your reviewers.

**Entry point.** The entry has no `entry_points` key. Contract (§6.2): a use-case with no
resolvable declared entry point gets its **first resolved hop** as a fallback entry point
of kind `other`, labelled with the use-case name. Since nobody calls `renew`, inventing
an HTTP route here would be a lie; the fallback is the honest rendering, and the panel
will show it under *Other*.

## 6. Build the map

From the repository root, with the extractor installed (`npm ci --ignore-scripts` in
`extractor/`, once):

```bash
python pipeline/build.py --repo examples/sample-drf --config config/example.json \
    --ucs examples/sample-drf/usecases.json --out matryoshker.html --lang python --strict
```

Expected output (stderr and stdout interleaved; the `build.py: step k/4` lines omitted;
on Windows the paths print with backslashes):

```
files=25 imports=33 ucs=6 hops=37 -> out/data.json (10KB)
entry points: 4 from parsers, 5 declared, 2 fallback, 2 duplicates merged
entry_points=9 calls: internal=49 cross=71 -> out/extra.json (6KB)
matryoshker.html: 98KB
```

Read the counters against what you wrote: `ucs=6` (five plus yours), `hops=37` (33
plus your four), `2 fallback` (the fixture already had one use-case with no entry point;
yours is the second). No line starting with `UC ` appeared on stderr: every hop's file
resolved and every symbol was found in its file.

### What a mistake looks like

Both variants below were run. **A wrong symbol** — hop 1 cited as
`LoanService.extend` instead of `LoanService.renew`:

```
UC Member renews a loan before it is due: 4/4 hops resolved
  unverified symbol [LoanService.extend not declared in lending/services/loan_service.py]: lending/services/loan_service.py:LoanService.extend — refuses when the title has a queue or the renewals are used up
files=25 imports=33 ucs=6 hops=37 -> out/data.json (10KB)
```

The hop still counts (`4/4`, `hops=37`), still draws on the map with the wrong name,
and the exit code is **0 even with `--strict`**. The only trace is that stderr line.
Read the stderr.

**A wrong file** — hop 2 cited as `lending/domain/renewal_policy.py:can_renew`:

```
UC Member renews a loan before it is due: 3/4 hops resolved
  dropped [file not found in the extraction]: lending/domain/renewal_policy.py:can_renew — the rule: no open reservation and fewer than MAX_RENEWALS
total: 36/37 hops resolved (1 dropped in 1 use-cases)
strict: 1 citations dropped
```

The hop is dropped (`hops=36`), and with `--strict` the build stops at step 2 with exit
code 3 and writes no HTML. Without `--strict` it exits 0 and builds a map with three
hops. Contract: §5.4, §5.5 and §11 of the data contract.

## 7. What you should see

Open `matryoshker.html`.

- Sidebar, *Use-cases*: six entries; yours is last, with an `inferred` chip.
- Sidebar, *Entry points*, group *Other*: an entry named *Member renews a loan before it
  is due*, `LoanService.renew · loan_service.py` — the fallback.
- Click the use-case. *Packages*: three badges — `1.` on `loan_service.py`, `2.` on
  `policies.py`, `3.` on `models.py` — because the two `policies.py` hops share a file.
  The right panel lists the four hops with their roles and the two rules, numbered by
  map badge — so the two `policies.py` hops both read `2`.
- *Flow*: four boxes, `1.` to `4.`, in registry order.
- Click the `loan_service.py` square: *Use-cases passing here (4)* — three existing
  use-cases and yours. This is the file → use-cases reverse index.
- *open symbol map ⌄*, then click `renew`: *Calls (2)* `can_renew`, `loan_period_days`;
  *Called by (0)*.

## 8. How a reviewer checks it

The pull request contains one hunk in `usecases.json`. The reviewer:

1. **Opens each cited symbol** in the code and reads the role against it. Four hops,
   four reads. A role that describes the function in general rather than its part in
   this behavior gets a comment.
2. **Compares the hop list with the extraction.** In the map, the Symbols panel for
   `renew` lists what it calls. Everything the code calls that is not a hop must be a
   deliberate omission the reviewer agrees with (see section 4); everything cited that
   the code does not call is wrong.
3. **Checks the status against the rule.** `inferred` from a human author who read the
   code: correct. The reviewer also reads `notes` and the empty `entry_points` and
   agrees they are the honest rendering.
4. **Blesses, or does not.** If the reviewer has re-read the hops and agrees, the PR
   (or a follow-up commit) changes `"status": "inferred"` to `"human-verified"`. The
   same edit can be produced from the viewer: pick the value in the dropdown, press
   *export local statuses*, paste the snippet's value into the file. Either way the
   blessing is a diff to the registry; who made it and when is in git history and
   nowhere else.

A reviewer who has not re-read the hops does not bless. Approving the PR with
`inferred` unchanged is a fine outcome.

## 9. When the code changes

The registry does not follow the code by itself. After a change that touches any file
a use-case cites, rebuild with `--strict` and read stderr:

| Change | What the build says | What you do |
|---|---|---|
| `renew` renamed to `extend` | `unverified symbol [LoanService.renew not declared in ...]`, exit 0 | fix the citation; status unchanged only if the behavior is |
| `loan_service.py` moved or split | `dropped [file not found ...]`, exit 3 with `--strict` | fix the path (or add the directory to `hop_path_prefixes` in the config, §5.3) |
| a view starts calling `renew` | nothing — the extraction changes, the registry does not | add `"entry_points": ["http: ... (catalog/views.py:BookViewSet)"]`, maybe a hop; `notes` is now stale |
| `MAX_RENEWALS` becomes 3 | nothing | the rule text and hop 2's role are stale; only a read catches this |
| the queue check is removed | nothing | hop 1's role is now wrong: set `status` to `outdated` in the same PR as the code change, or fix the entry; do not delete it |

Two habits make this cheap: touch the registry in the **same PR** as a change to a cited
file, and bump `commit` and `date` in `config/<repo>.json` when you rebuild, since the
header shows those values and nothing reads git for you.

## 10. For your own repository

The same steps apply with two files of your own. `config/<repo>.json` (copy
`config/example-ddd.json` if you have no Django/DRF routes; `config/example.json` if you
do) and `data/<repo>/usecases.json`, which may start as `[]`. Build without `--ucs`
first to see the extracted map alone, pick the first behavior from what you see, and
add it. [QUICKSTART.md](../QUICKSTART.md) has the commands and the paths you control;
[CONTRIBUTING.md](../CONTRIBUTING.md) the hop and entry-point grammar, the status rule
and the maintenance routine; the data contract's §5.1 the `branch:` and `seam:` prefixes
for flows that fork or cross a process boundary.
