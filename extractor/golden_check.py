#!/usr/bin/env python
"""golden_check.py — comparator for the extract.mjs wrapper's golden test.

Compares golden-run/{scan,im,es}-output.json against the reference
golden output (by default tests/golden/ at the repo root, generated from
examples/sample-drf). Criteria (all mandatory):

  scan:       same total file count and same SET of python paths;
  import-map: same SET of {src -> dst} edges;
  structure:  same analyzed/skipped counts; per path, SAME set of class
              names, SAME set of function names, and SAME count of
              callGraph entries.

Usage: python golden_check.py [--run-dir golden-run] [--golden-dir ../tests/golden]
Both default paths are resolved relative to this script's own location
(the extractor/ directory), not the current working directory, so the
tool behaves the same no matter where it is invoked from.

Exit 0 = PASS; exit 1 = FAIL (divergences listed).
"""

import argparse
import json
import sys
from pathlib import Path

MAX_LIST = 10


def load(path: Path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def show(items):
    items = sorted(items)
    head = ", ".join(repr(i) for i in items[:MAX_LIST])
    more = f" (+{len(items) - MAX_LIST} more)" if len(items) > MAX_LIST else ""
    return head + more


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", default="golden-run")
    ap.add_argument("--golden-dir", default="../tests/golden")
    args = ap.parse_args()

    base = Path(__file__).resolve().parent
    run_dir = (base / args.run_dir).resolve()
    golden_dir = (base / args.golden_dir).resolve()

    failures = []
    checks = []

    def check(name, ok, detail=""):
        checks.append((name, ok, detail))
        if not ok:
            failures.append(name)

    # ------------------------------------------------------------------ scan
    scan_new = load(run_dir / "scan-output.json")
    scan_old = load(golden_dir / "scan-output.json")

    check(
        "scan: totalFiles",
        scan_new["totalFiles"] == scan_old["totalFiles"],
        f"run={scan_new['totalFiles']} golden={scan_old['totalFiles']}",
    )

    py_new = {f["path"] for f in scan_new["files"] if f["language"] == "python"}
    py_old = {f["path"] for f in scan_old["files"] if f["language"] == "python"}
    only_new = py_new - py_old
    only_old = py_old - py_new
    check(
        "scan: python path set",
        not only_new and not only_old,
        f"run={len(py_new)} golden={len(py_old)}"
        + (f"; only-in-run: {show(only_new)}" if only_new else "")
        + (f"; only-in-golden: {show(only_old)}" if only_old else ""),
    )

    all_new = {f["path"] for f in scan_new["files"]}
    all_old = {f["path"] for f in scan_old["files"]}
    d_new, d_old = all_new - all_old, all_old - all_new
    check(
        "scan: full path set",
        not d_new and not d_old,
        f"run={len(all_new)} golden={len(all_old)}"
        + (f"; only-in-run: {show(d_new)}" if d_new else "")
        + (f"; only-in-golden: {show(d_old)}" if d_old else ""),
    )

    # ------------------------------------------------------------ import-map
    im_new = load(run_dir / "im-output.json")
    im_old = load(golden_dir / "im-output.json")

    edges_new = {(src, dst) for src, dsts in im_new["importMap"].items() for dst in dsts}
    edges_old = {(src, dst) for src, dsts in im_old["importMap"].items() for dst in dsts}
    e_new, e_old = edges_new - edges_old, edges_old - edges_new
    check(
        "import-map: edge set",
        not e_new and not e_old,
        f"run={len(edges_new)} golden={len(edges_old)}"
        + (f"; only-in-run: {show(e_new)}" if e_new else "")
        + (f"; only-in-golden: {show(e_old)}" if e_old else ""),
    )

    # ------------------------------------------------------------- structure
    es_new = load(run_dir / "es-output.json")
    es_old = load(golden_dir / "es-output.json")

    check(
        "structure: filesAnalyzed",
        es_new["filesAnalyzed"] == es_old["filesAnalyzed"],
        f"run={es_new['filesAnalyzed']} golden={es_old['filesAnalyzed']}",
    )
    check(
        "structure: filesSkipped",
        len(es_new["filesSkipped"]) == len(es_old["filesSkipped"]),
        f"run={len(es_new['filesSkipped'])} golden={len(es_old['filesSkipped'])}",
    )

    res_new = {r["path"]: r for r in es_new["results"]}
    res_old = {r["path"]: r for r in es_old["results"]}
    p_new, p_old = set(res_new) - set(res_old), set(res_old) - set(res_new)
    check(
        "structure: result path set",
        not p_new and not p_old,
        f"run={len(res_new)} golden={len(res_old)}"
        + (f"; only-in-run: {show(p_new)}" if p_new else "")
        + (f"; only-in-golden: {show(p_old)}" if p_old else ""),
    )

    class_diffs, func_diffs, cg_diffs = [], [], []
    for path in sorted(set(res_new) & set(res_old)):
        rn, ro = res_new[path], res_old[path]
        cn = {c["name"] for c in rn.get("classes", [])}
        co = {c["name"] for c in ro.get("classes", [])}
        if cn != co:
            class_diffs.append((path, sorted(cn - co), sorted(co - cn)))
        fn = {f["name"] for f in rn.get("functions", [])}
        fo = {f["name"] for f in ro.get("functions", [])}
        if fn != fo:
            func_diffs.append((path, sorted(fn - fo), sorted(fo - fn)))
        gn = len(rn.get("callGraph", []))
        go = len(ro.get("callGraph", []))
        if gn != go:
            cg_diffs.append((path, gn, go))

    check(
        "structure: class-name sets (per path)",
        not class_diffs,
        f"{len(class_diffs)} paths differ"
        + (
            "; e.g. "
            + "; ".join(
                f"{p} +run:{a} +golden:{b}" for p, a, b in class_diffs[:3]
            )
            if class_diffs
            else ""
        ),
    )
    check(
        "structure: function-name sets (per path)",
        not func_diffs,
        f"{len(func_diffs)} paths differ"
        + (
            "; e.g. "
            + "; ".join(f"{p} +run:{a} +golden:{b}" for p, a, b in func_diffs[:3])
            if func_diffs
            else ""
        ),
    )
    check(
        "structure: callGraph entry counts (per path)",
        not cg_diffs,
        f"{len(cg_diffs)} paths differ"
        + (
            "; e.g. "
            + "; ".join(f"{p} run={a} golden={b}" for p, a, b in cg_diffs[:5])
            if cg_diffs
            else ""
        ),
    )

    # ---------------------------------------------------------------- report
    print(f"golden_check: run={run_dir}")
    print(f"golden_check: golden={golden_dir}")
    for name, ok, detail in checks:
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {name}" + (f" -- {detail}" if detail else ""))

    if failures:
        print(f"RESULT: FAIL ({len(failures)}/{len(checks)} checks failed)")
        return 1
    print(f"RESULT: PASS ({len(checks)}/{len(checks)} checks)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
