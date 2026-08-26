"""Rebuild every figure in README.md from the shipped results and compare.

    python3 scripts/check_readme_numbers.py

Why this exists. A number typed into prose is a copy, and a copy drifts from
its source without anything failing. This rebuilds each figure from
results/*.jsonl and requires the exact string to appear in README.md.

It covers sentences, not only table rows. A percentage inside a paragraph does
not look like a figure to a reader or to whoever writes a checker, which makes
it the one most likely to drift. Every figure below is looked for in the whole
document, wherever it sits.

It prints how many figures it checked, whether or not any are missing, so a
version that quietly stopped deriving half of them is visible instead of clean.

Exit status is 0 when every derived figure appears and 1 otherwise.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
RUNS = {"anthropic": ROOT / "results" / "sweep.jsonl",
        "openai": ROOT / "results" / "sweep_openai.jsonl",
        # The replicate is checked too. It is a whole column of the headline
        # table and the sole source of the run-to-run drift figures, and
        # leaving it out meant nine table cells and every drift number in the
        # prose were outside the only thing that compares prose to evidence.
        "replicate": ROOT / "results" / "sweep_replicate.jsonl"}
BASE = "resolved"


def load(path: Path) -> list:
    rows = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            rows[(r["qid"], r["arm"])] = r
    return list(rows.values())


def field_pct(rs) -> float:
    c = sum(r["grade"]["n_correct"] for r in rs)
    t = sum(r["grade"]["n_fields"] for r in rs)
    return 100.0 * c / t if t else 0.0


def derive() -> list[tuple[str, str]]:
    """Every figure the README is allowed to state, as (label, exact string)."""
    out: list[tuple[str, str]] = []
    for provider, path in RUNS.items():
        rows = load(path)
        arms = defaultdict(list)
        for r in rows:
            if r.get("experiment", "arms") == "arms":
                arms[r["arm"]].append(r)

        out.append((f"{provider} generations", str(len(rows))))
        out.append((f"{provider} questions",
                    str(len({r["qid"] for r in rows
                             if r.get("experiment", "arms") == "arms"}))))
        for arm, rs in sorted(arms.items()):
            out.append((f"{provider} {arm} field%", f"{field_pct(rs):.1f}"))

        leaks = sum(r["governance"]["prompt_leak"] for r in rows)
        clean = len(rows) - leaks
        out.append((f"{provider} prompt leaks", str(leaks)))
        out.append((f"{provider} clean generations", str(clean)))
        out.append((f"{provider} output leaks",
                    str(sum(r["governance"]["output_leak"] for r in rows))))
        out.append((f"{provider} inferred leaks",
                    str(sum(r["governance"]["inferred_leak"] for r in rows))))

        if provider != "replicate":
            tin = sum(r["usage"]["input"] for r in rows)
            tout = sum(r["usage"]["output"] for r in rows)
            rate_out = 12.00 if provider == "openai" else 10.00
            cost = tin / 1e6 * 2.00 + tout / 1e6 * rate_out
            out.append((f"{provider} cost", f"${cost:.2f}"))

    # The drift figures, which are the point of shipping a replicate. The
    # README leads a whole section with them and nothing derived them.
    base = {a: field_pct(rs) for a, rs in _arms(RUNS["anthropic"]).items()}
    rep = {a: field_pct(rs) for a, rs in _arms(RUNS["replicate"]).items()}
    both = sorted(set(base) & set(rep))
    deltas = [abs(base[a] - rep[a]) for a in both]
    out.append(("run-to-run max drift", f"{max(deltas):.1f}"))
    out.append(("run-to-run mean drift", f"{sum(deltas) / len(deltas):.2f}"))
    out.append(("conditions compared across runs", str(len(both))))
    return out


def _arms(path: Path) -> dict:
    arms = defaultdict(list)
    for r in load(path):
        if r.get("experiment", "arms") == "arms":
            arms[r["arm"]].append(r)
    return arms


def main() -> int:
    if not README.is_file():
        print("README.md is missing")
        return 1
    text = README.read_text(encoding="utf-8")
    figures = derive()
    missing = [(label, value) for label, value in figures
               if value not in text]

    print(f"{len(figures)} figures derived from "
          f"{', '.join(p.name for p in RUNS.values())}")
    print(f"{len(figures) - len(missing)} found in README.md, "
          f"{len(missing)} missing")
    for label, value in missing:
        print(f"  MISSING  {label}: {value}")
    if missing:
        print("\nA figure the README states must be derivable from the shipped "
              "evidence.\nEither the prose is stale or the evidence changed.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
