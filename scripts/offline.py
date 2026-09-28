"""Render every prompt the sweep would send, and cost it, without sending one.

It builds every prompt, counts their characters, and estimates the tokens and
the cost at the rates the operator approved. The characters are measured; the
tokens are those characters divided by assemble.CHARS_PER_TOKEN. The shipped
Claude run billed 2,394,166 input tokens against this estimate's 2,161,894,
which is 11 percent more. Nothing here touches the network and nothing here needs a
credential.

    python3 scripts/offline.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from cqa import assemble, leak, prompt, questions, world
import sweep                                              # noqa: E402

# Per million tokens, IMPORTED FROM THE RUNNER and never redefined. Claude
# Sonnet 5 is $2/$10 standard: the increase to $3/$15 once scheduled for
# 2026-09-01 was canceled, so a table still calling $2/$10 "introductory" is
# stale. Batch is half of both, which is a RULE about the standard rate and is
# applied to it here rather than typed as a second pair of numbers.
_STD = (sweep.PROVIDERS["anthropic"]["in"], sweep.PROVIDERS["anthropic"]["out"])
RATES = {
    "sonnet-5 standard": _STD,
    "sonnet-5 batch": (_STD[0] / 2, _STD[1] / 2),
}
# Output is a small JSON object. This is an assumption, not a measurement, and
# the print below says so in those words. The shipped runs report means of
# 35.9 (Claude) and 28.0 (GPT) output tokens, so this over-estimates and the
# estimate it feeds is therefore an upper bound and not a central one, which
# is the direction a budget approval wants to be wrong in. It is not
# replaced by either measured mean because this script runs BEFORE a run, for
# a run that has not happened, and a figure taken from a completed run of a
# different configuration is not this run's mean either.
ASSUMED_OUTPUT_TOKENS = 39
# Imported, never redefined. See assemble.CHARS_PER_TOKEN.
CHARS_PER_TOKEN = assemble.CHARS_PER_TOKEN




def main() -> int:
    w = world.build()
    qs = questions.build(w)
    values = leak.forbidden_values(w)

    per_arm: dict[str, list[int]] = {a: [] for a in assemble.ARMS}
    leaks: dict[str, int] = {a: 0 for a in assemble.ARMS}

    for q in qs:
        for arm in assemble.ARMS:
            text = prompt.SYSTEM + prompt.user_message(
                q, assemble.context_for(w, q, arm))
            per_arm[arm].append(len(text))
            if leak.scan(text, values)["any"]:
                leaks[arm] += 1

    print(f"{len(qs)} questions x {len(assemble.ARMS)} arms = "
          f"{len(qs) * len(assemble.ARMS)} generations\n")
    print(f"{'arm':<13} {'chars avg':>10} {'tokens avg':>11} "
          f"{'tokens tot':>11}  {'leaks':>5}   description")
    total_in = 0
    for arm in assemble.ARMS:
        sizes = per_arm[arm]
        avg = sum(sizes) / len(sizes)
        tok = avg / CHARS_PER_TOKEN
        tot = tok * len(sizes)
        total_in += tot
        print(f"{arm:<13} {avg:>10,.0f} {tok:>11,.0f} {tot:>11,.0f}  "
              f"{leaks[arm]:>5}   {assemble.ARM_LABEL[arm]}")

    # The token-budget curve, on a subset. It is a separate experiment: the
    # arms answer "which property matters", the curve answers "how much".
    curve_qs = questions.curve_subset(qs)
    curve_in = 0
    print(f"\nTOKEN-BUDGET CURVE, {len(curve_qs)} questions x "
          f"{len(assemble.CURVE_BUDGETS)} budgets = "
          f"{len(curve_qs) * len(assemble.CURVE_BUDGETS)} generations")
    print(f"{'budget':>8} {'chars avg':>10} {'tokens avg':>11} "
          f"{'tokens tot':>11}")
    for bkt in assemble.CURVE_BUDGETS:
        sizes = [len(prompt.SYSTEM + prompt.user_message(
            q, assemble.curve_context(w, q, bkt))) for q in curve_qs]
        avg = sum(sizes) / len(sizes)
        tot = avg / CHARS_PER_TOKEN * len(sizes)
        curve_in += tot
        print(f"{bkt:>8} {avg:>10,.0f} {avg / CHARS_PER_TOKEN:>11,.0f} "
              f"{tot:>11,.0f}")
    total_in += curve_in
    n_gen = len(qs) * len(assemble.ARMS) + len(curve_qs) * len(assemble.CURVE_BUDGETS)
    total_out = ASSUMED_OUTPUT_TOKENS * n_gen
    print(f"\nTOTAL, ARMS PLUS CURVE: {n_gen:,} generations")
    print(f"input tokens  {total_in:>12,.0f}  "
          f"(estimated from rendered characters)")
    print(f"output tokens {total_out:>12,.0f}  "
          f"({ASSUMED_OUTPUT_TOKENS}/generation ASSUMED, not measured -- no "
          f"output exists until the run does)")
    print()
    for name, (cin, cout) in RATES.items():
        cost = total_in / 1e6 * cin + total_out / 1e6 * cout
        print(f"  {name:<16} ${cost:,.2f}")
    print("\nLEAK EXPECTATION: only the unpoliced arm should be non-zero, "
          "and it should be all of them.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
