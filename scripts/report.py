"""Read the results and report what the sweep actually shows.

    python3 scripts/report.py                 # the full sweep
    python3 scripts/report.py results/x.jsonl # any results file

Reports paired differences against the resolved baseline, per stratum as well
as in aggregate, and states the resolution floor rather than ranking noise.

The resolution floor is computed, not asserted. It comes from a bootstrap over
questions, which is the right unit: the same question in two arms is a matched
pair, and pairing is what cuts the variance enough to see a small difference at
all. A difference whose interval spans zero is reported as not separated, and
the word "not separated" is used rather than a rank.
"""
from __future__ import annotations

import json
import random
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cqa import assemble, questions, world

DEFAULT = Path(__file__).resolve().parents[1] / "results" / "sweep.jsonl"
BASE = "resolved"
BOOTSTRAP = 2000
SEED = 20260824


def load(path: Path):
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    dedup = {}
    for r in rows:
        dedup[(r["qid"], r["arm"])] = r      # a resumed run may append twice
    return list(dedup.values())


def field_acc(rs) -> float:
    c = sum(r["grade"]["n_correct"] for r in rs)
    t = sum(r["grade"]["n_fields"] for r in rs)
    return 100.0 * c / t if t else 0.0


def exact(rs) -> float:
    return 100.0 * sum(r["grade"]["all_correct"] for r in rs) / len(rs)


def paired_ci(arm_rows: dict, base_rows: dict, rng: random.Random):
    """Bootstrap CI of the paired field-accuracy difference, in points."""
    qids = sorted(set(arm_rows) & set(base_rows))
    if not qids:
        # A comparison that cannot be made must not print as a measured zero.
        # Any partial resume leaves an arm and the baseline covering disjoint
        # questions, and returning zeros rendered a large real difference as
        # "no difference, interval [0, 0]".
        return None, None, None
    diffs = []
    for qid in qids:
        a, b = arm_rows[qid]["grade"], base_rows[qid]["grade"]
        diffs.append(100.0 * (a["n_correct"] - b["n_correct"]) / a["n_fields"])
    point = sum(diffs) / len(diffs)
    boots = []
    for _ in range(BOOTSTRAP):
        s = [diffs[rng.randrange(len(diffs))] for _ in diffs]
        boots.append(sum(s) / len(s))
    boots.sort()
    return point, boots[int(0.025 * len(boots))], boots[int(0.975 * len(boots))]


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT
    rows = load(path)
    rng = random.Random(SEED)

    # Refuse to aggregate rows the current code no longer produces. A
    # results file outlives the generator that wrote it, and rendering it
    # afterwards reports numbers for questions that no longer exist.
    live = questions.fingerprint(questions.build(world.build()))
    stamps = {r.get("questions_fingerprint", "unstamped") for r in rows}
    if stamps != {live}:
        print(f"REFUSING TO REPORT. The current question set fingerprints as "
              f"{live};\nthese results carry {sorted(stamps)}.\n"
              f"They were produced by a different generator, so the numbers "
              f"below would\ndescribe questions this code no longer asks. "
              f"Re-run, or report against the\ncode revision that produced "
              f"them.")
        return 2
    # Per-arm staleness, named. A question-set match is not enough: an arm
    # whose assembly changed is stale on its own, and dropping it silently
    # would leave a table that looks complete.
    _w = world.build()
    _qs = questions.build(_w)
    live_arm = {a: assemble.arm_fingerprint(_w, _qs, a) for a in assemble.ARMS}
    # The curve is checked the same way. Its rows reuse the arm slot for their
    # budget, and a budget is a condition: a change to the ranking or the
    # truncation rule invalidates those rows exactly as a change to an arm's
    # assembly invalidates that arm's. A row carrying no condition hash matches
    # nothing here and is reported stale, which is the correct answer; nothing
    # in it can certify what rendered it.
    live_arm.update({f"budget{b}": assemble.curve_fingerprint(_w, _qs, b)
                     for b in assemble.CURVE_BUDGETS})
    stale_arms = sorted({
        r["arm"] for r in rows
        if r.get("arm_fingerprint", "unstamped") != live_arm.get(r["arm"])})
    if stale_arms:
        print(f"REFUSING TO REPORT. These arms were recorded by a different "
              f"assembly than\nthe code now produces: {', '.join(stale_arms)}."
              f"\nRe-run them, or report against the revision that produced "
              f"them.")
        return 2
    arms_rows = [r for r in rows if r.get("experiment", "arms") == "arms"]
    curve_rows = [r for r in rows if r.get("experiment") == "curve"]

    by_arm = defaultdict(list)
    for r in arms_rows:
        by_arm[r["arm"]].append(r)
    n_q = len({r["qid"] for r in arms_rows})
    strata = sorted({r["stratum"] for r in arms_rows})

    print(f"{len(rows)} generations | {len(arms_rows)} arms + "
          f"{len(curve_rows)} curve | {n_q} questions | "
          f"{rows[0]['model']} effort {rows[0]['effort']}\n")

    base_by_q = {r["qid"]: r for r in by_arm[BASE]}
    # Two averages, both named. Field% weights every FIELD equally (micro);
    # paired weights every QUESTION equally (macro) and is the one the
    # interval is computed on, because pairing is what cuts the variance.
    # They can differ by several points and a reader must not be left to
    # subtract one column from another and wonder why it does not reconcile.
    print(f"{'arm':<13} {'field%':>7} {'exact%':>7} {'micro-d':>8} "
          f"{'paired-d':>9} {'95% CI':>16} {'in tok':>8} {'sig':<1} "
          f"{'leak':>5}  " +
          " ".join(f"{s[:4]:>5}" for s in strata))
    for arm in assemble.ARMS:
        rs = by_arm.get(arm, [])
        if not rs:
            continue
        pt, lo, hi = paired_ci({r["qid"]: r for r in rs}, base_by_q, rng)
        if pt is None:
            print(f"{arm:<13} {field_acc(rs):>7.1f} {exact(rs):>7.1f} "
                  f"{'n/a':>8} {'n/a':>9} {'no paired questions':>16}")
            continue
        tok = sum(r["usage"]["input"] for r in rs) / len(rs)
        leaks = sum(r["governance"]["prompt_leak"] for r in rs)
        per = " ".join(
            f"{field_acc([r for r in rs if r['stratum'] == s]):>5.0f}"
            for s in strata)
        sep = " " if arm == BASE else ("*" if lo > 0 or hi < 0 else " ")
        micro = field_acc(rs) - field_acc(by_arm[BASE])
        print(f"{arm:<13} {field_acc(rs):>7.1f} {exact(rs):>7.1f} "
              f"{micro:>+8.1f} {pt:>+9.1f} {f'[{lo:+.1f}, {hi:+.1f}]':>16} "
              f"{tok:>8,.0f} {sep:<1} {leaks:>5}  {per}")
    print(f"\nstrata: {', '.join(strata)}    "
          f"* = interval excludes zero, so the difference is separated")
    print("micro-d = field% minus the baseline's field%, every FIELD weighted "
          "equally.\npaired-d = mean over QUESTIONS of the per-question "
          "difference, which is what\nthe interval is computed on. Quote which "
          "one you mean; they are not the same\nnumber and on this data they "
          "differ by up to about seven points.")

    if curve_rows:
        print("\nTOKEN-BUDGET CURVE (ranked context cut at a budget):")
        by_b = defaultdict(list)
        for r in curve_rows:
            by_b[int(r["arm"].replace("budget", ""))].append(r)
        print(f"{'budget':>8} {'field%':>7} {'exact%':>7} {'in tok':>8}  n")
        best = None
        for bkt in sorted(by_b):
            rs = by_b[bkt]
            acc = field_acc(rs)
            tok = sum(r["usage"]["input"] for r in rs) / len(rs)
            print(f"{bkt:>8} {acc:>7.1f} {exact(rs):>7.1f} {tok:>8,.0f}  "
                  f"{len(rs)}")
            if best is None or acc > best[1]:
                best = (bkt, acc)
        last = sorted(by_b)[-1]
        # An eyeballed peak is not a peak. Each budget is paired against the
        # LARGEST budget, which turns "does more context hurt" into an
        # interval instead of a ranking of six noisy numbers.
        print(f"\n  paired against the largest budget ({last}):")
        biggest = {r["qid"]: r for r in by_b[last]}
        sep_any = False
        for bkt in sorted(by_b):
            if bkt == last:
                continue
            pt, lo, hi = paired_ci({r["qid"]: r for r in by_b[bkt]},
                                   biggest, rng)
            # Direction matters. The prediction is that a SMALLER budget
            # scores HIGHER than the largest, so only lo > 0 supports it. An
            # interval that excludes zero on the NEGATIVE side means the
            # smaller budget is worse, which is the opposite claim, and
            # treating "separated" as "supported" made a losing budget read
            # as confirmation.
            mark = "*" if lo > 0 or hi < 0 else " "
            sep_any = sep_any or lo > 0
            print(f"    budget {bkt:>5} vs {last}: {pt:>+6.1f} "
                  f"{f'[{lo:+.1f}, {hi:+.1f}]':>16} {mark}")
        print(f"\n  peak at budget {best[0]} ({best[1]:.1f}%); "
              f"largest budget {last} scores {field_acc(by_b[last]):.1f}%")
        if sep_any:
            print("  A SMALLER BUDGET BEATS THE LARGEST BY MORE THAN NOISE, "
                  "which is the\n  prediction holding: more context is not "
                  "monotonically better.")
        else:
            print("  NO BUDGET BEATS THE LARGEST BY MORE THAN NOISE, so the "
                  "prediction that\n  accuracy DECLINES with budget is NOT "
                  "supported by this run. A star on a\n  negative row means "
                  "that budget is significantly WORSE than the largest, which"
                  "\n  is the opposite claim and is not evidence for it.")
        print("  The curve uses 60 questions drawn equally from the four "
              "strata, so its\n  levels are not directly comparable with the "
              "arm table above, which uses 150.")

    print("\nGOVERNANCE:")
    for arm in assemble.ARMS:
        rs = by_arm.get(arm, [])
        if not rs:
            continue
        p = sum(r["governance"]["prompt_leak"] for r in rs)
        o = sum(r["governance"]["output_leak"] for r in rs)
        i = sum(r["governance"]["inferred_leak"] for r in rs)
        if p or o or i:
            print(f"  {arm:<13} prompt {p:>4}/{len(rs)}  output {o:>4}  "
                  f"inferred {i:>4}")
    leaky = sorted({r["arm"] for r in rows if r["governance"]["prompt_leak"]})
    clean_rows = [r for r in rows if r["arm"] not in leaky]
    # Name the arms that leak rather than asserting the rest are clean. The
    # previous sentence was unconditional and would print "0 leaks everywhere
    # else" directly beneath a line showing the baseline leaking.
    print(f"  arms with any prompt leak: {', '.join(leaky) or 'none'}")
    print(f"  all other arms and budgets: 0 prompt leaks across "
          f"{len(clean_rows)} generations")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
