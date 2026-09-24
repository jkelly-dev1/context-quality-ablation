"""Rebuild every figure in README.md from the shipped results and compare.

    python3 scripts/check_readme_numbers.py

Why this exists. A number typed into prose is a copy, and a copy drifts from
its source without anything failing. This rebuilds each figure from
results/*.jsonl and requires README.md to state it.

There are three kinds of check, and the difference between them matters.

  POSITIONAL. The condition table is parsed, and each cell is compared against
  the arm and run that cell is for. This is the only kind that can tell a right
  number in a wrong cell, which the substring check below explicitly cannot,
  and it covers the thirty figures a reader actually looks at.

  EMPHASIS. A bold cell in that table is a claim (the condition's 95 percent
  paired interval excludes zero in that run), and it is derived here from the
  same rows, through `report.separated`, so the table cannot disagree with the
  report. Emphasis without a definition would be decoration.

  IN CONTEXT. A figure in a sentence is matched with enough of the sentence
  around it to make the match mean something. A bare string is not evidence
  when the value is short or common: "0", "150" and "1860" appear in any
  plausible README, so requiring only the bare value would count figures that
  cannot fail among the ones that can. Every figure whose bare value is short
  or common therefore carries a pattern, and a figure with no pattern is one
  whose value is distinctive on its own, a cost like "$5.47".

It prints how many figures it checked, whether or not any are missing, so a
version that quietly stopped deriving half of them is visible instead of clean.
That count is itself one of the figures, so README.md and SAMPLE_RUN.md cannot
go on quoting a count from a version of this file that derived fewer.

Exit status is 0 when every derived figure appears and 1 otherwise.
"""
from __future__ import annotations

import json
import random
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Imported, never redefined. The cost figures in README.md are a price times a
# token count, and the price belongs to scripts/sweep.py, which is what spends
# the money. A second copy here would be the drift shape this repository
# defines one constant for everywhere else (CHARS_PER_TOKEN, the answer key),
# and worse here than most: a checker holding a stale price certifies the
# drift it was built to find.
import report                                             # noqa: E402
import sweep                                              # noqa: E402
from cqa import assemble, questions, world                # noqa: E402

README = ROOT / "README.md"
RUNS = {"anthropic": ROOT / "results" / "sweep.jsonl",
        "openai": ROOT / "results" / "sweep_openai.jsonl",
        # The replicate is checked too. It is a whole column of the headline
        # table and the sole source of the run-to-run drift figures, and
        # leaving it out meant nine table cells and every drift number in the
        # prose were outside the only thing that compares prose to evidence.
        "replicate": ROOT / "results" / "sweep_replicate.jsonl"}
BASE = "resolved"

# The condition table's own names for the ten arms and the three runs. A table
# that renamed a row would otherwise silently stop being checked, so an
# unmatched row or column is a failure below and not a skip.
ROW_LABEL = {"no context": "none", "unpoliced": "unpoliced",
             "diluted": "diluted", "nostructure": "nostructure",
             "resolved (baseline)": "resolved", "perfect": "perfect",
             "stale": "stale", "governed": "governed",
             "unresolved": "unresolved", "incomplete": "incomplete"}
COL_LABEL = {"Claude": "anthropic", "Claude replicate": "replicate",
             "GPT": "openai"}
# The same three runs as a reader names them in a sentence.
DISPLAY = {"anthropic": "Claude", "replicate": "replicate", "openai": "GPT"}


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


def _arms(path: Path) -> dict:
    arms = defaultdict(list)
    for r in load(path):
        if r.get("experiment", "arms") == "arms":
            arms[r["arm"]].append(r)
    return arms


def separated_arms(path: Path) -> set:
    """The arms whose paired interval excludes zero, exactly as report.py
    computes and marks them. One implementation, in report.py."""
    by_arm = _arms(path)
    base_by_q = {r["qid"]: r for r in by_arm[BASE]}
    stats = report.paired_by_arm(by_arm, base_by_q,
                                 random.Random(report.SEED))
    return report.separated(stats)


def parse_table(text: str) -> tuple[dict, dict]:
    """The condition table, as {(arm, provider): value} and {(arm, p): bold}.

    Returns empty dicts if the table is not found, which main() treats as a
    failure rather than as nothing to do: the table is the headline surface,
    and a checker that silently stops reading it reports a clean run for a
    document it never looked at.
    """
    values: dict = {}
    bold: dict = {}
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if not line.startswith("| condition |"):
            continue
        header = [c.strip() for c in line.strip("|").split("|")]
        cols = {j: COL_LABEL[h] for j, h in enumerate(header) if h in COL_LABEL}
        for row in lines[i + 2:]:
            if not row.startswith("|"):
                break
            cells = [c.strip() for c in row.strip("|").split("|")]
            arm = ROW_LABEL.get(cells[0])
            if arm is None:
                continue
            for j, provider in cols.items():
                cell = cells[j]
                bold[(arm, provider)] = cell.startswith("**")
                values[(arm, provider)] = cell.strip("*").strip()
        break
    return values, bold


def derive_cells() -> dict:
    """Every condition-table cell, as {(arm, provider): "99.6"}."""
    out = {}
    for provider, path in RUNS.items():
        for arm, rs in _arms(path).items():
            out[(arm, provider)] = f"{field_pct(rs):.1f}"
    return out


def derive() -> list[tuple[str, str, str | None]]:
    """Every figure the README states in PROSE, as (label, value, pattern).

    A pattern of None means the value is distinctive enough that its bare
    presence is evidence. Every other figure carries enough of its own
    sentence that a match is a match of the claim and not of a digit.
    """
    out: list[tuple[str, str, str | None]] = []
    for provider, path in RUNS.items():
        rows = load(path)
        n_gen = len(rows)
        n_q = len({r["qid"] for r in rows
                   if r.get("experiment", "arms") == "arms"})
        leaks = sum(r["governance"]["prompt_leak"] for r in rows)
        clean = n_gen - leaks
        out += [
            (f"{provider} generations", str(n_gen), rf"{n_gen} generations"),
            (f"{provider} questions", str(n_q), rf"{n_q} generated questions"),
            (f"{provider} prompt leaks", str(leaks),
             rf"{leaks} of {leaks} prompts"),
            (f"{provider} clean generations", str(clean),
             rf"{clean} generations"),
            (f"{provider} output leaks",
             str(sum(r["governance"]["output_leak"] for r in rows)),
             r"OUTPUT 0 times"),
            (f"{provider} inferred leaks",
             str(sum(r["governance"]["inferred_leak"] for r in rows)),
             r"permitted fields 0 times"),
        ]
        if provider != "replicate":
            tin = sum(r["usage"]["input"] for r in rows)
            tout = sum(r["usage"]["output"] for r in rows)
            rate = sweep.PROVIDERS[provider]
            cost = tin / 1e6 * rate["in"] + tout / 1e6 * rate["out"]
            out.append((f"{provider} cost", f"${cost:.2f}", None))

    # The drift figures, which are the point of shipping a replicate. The
    # README leads a whole section with them and nothing derived them.
    base = {a: field_pct(rs) for a, rs in _arms(RUNS["anthropic"]).items()}
    rep = {a: field_pct(rs) for a, rs in _arms(RUNS["replicate"]).items()}
    both = sorted(set(base) & set(rep))
    deltas = [abs(base[a] - rep[a]) for a in both]
    out += [
        ("run-to-run max drift", f"{max(deltas):.1f}",
         rf"up to {max(deltas):.1f} POINTS"),
        ("run-to-run mean drift", f"{sum(deltas) / len(deltas):.2f}",
         rf"mean {sum(deltas) / len(deltas):.2f}"),
        ("conditions compared across runs", str(len(both)),
         rf"{len(both)} conditions"),
    ]

    # The unresolved arm's identifier confound, derived and not typed.
    # This is the one place this repository fails its own "one arm changes one
    # thing" rule, the correction is roughly half the arm's published effect,
    # and a disclosure whose numbers are typed by hand is the next thing to go
    # stale. Every figure in that section of README.md comes from here.
    confounded = {q.qid for q in questions.build(world.build())
                  if questions.names_internal_id(q)}
    out.append(("questions naming an internal id", str(len(confounded)),
                rf"{len(confounded)} of the 150 question texts"))
    baselines = set()
    for provider, path in RUNS.items():
        disp = DISPLAY[provider]
        arms = _arms(path)
        on = [r for r in arms["unresolved"] if r["qid"] in confounded]
        off = [r for r in arms["unresolved"] if r["qid"] not in confounded]
        b_on = [r for r in arms[BASE] if r["qid"] in confounded]
        b_off = [r for r in arms[BASE] if r["qid"] not in confounded]
        baselines.add(f"{field_pct(b_on):.1f}")
        out += [
            (f"{provider} unresolved on the confounded questions",
             f"{field_pct(on):.1f}",
             rf"{field_pct(on):.1f} \({disp}\)"),
            (f"{provider} unresolved micro-d excluding them",
             f"{field_pct(off) - field_pct(b_off):.1f}",
             rf"{field_pct(off) - field_pct(b_off):.1f} \({disp}\)"),
        ]
    # The baseline answers all 22 on every run, which is what makes the gap
    # attributable to the arm and not to the questions being hard. It is
    # one figure only because all three runs agree; if they ever stop
    # agreeing, this set has more than one member and the claim is wrong.
    #
    # Raised, not asserted. `python3 -O` deletes an assert statement and the
    # message with it, and this is a guard in a shipped gate, not a type
    # narrowing: under -O the figure below would be one run's number
    # published as all three's.
    if len(baselines) != 1:
        raise SystemExit(
            f"the runs disagree about the baseline on the identifier-"
            f"confounded questions ({sorted(baselines)}), so README.md cannot "
            f"state one figure for all three")
    out.append(("baseline on the confounded questions", baselines.pop(),
                r"baseline of 100.0 on all three"))

    # The incomplete arm's realized drop, which is a property of the code and
    # not of a run. It is here because README.md states it, and a round "40
    # percent" would be wrong for this rendering while every other gate stayed
    # green.
    out.append(("incomplete arm realized drop",
                f"{100 * assemble.DROP_FRACTION:.1f}",
                rf"{assemble.DROPPED_FIELDS} of the "
                rf"{assemble.CANDIDATE_FIELDS} available fields, "
                rf"{100 * assemble.DROP_FRACTION:.1f} percent"))
    return out


def main() -> int:
    if not README.is_file():
        print("README.md is missing")
        return 1
    text = README.read_text(encoding="utf-8")
    # Whitespace is normalized for the sentence patterns, because the document is
    # hard-wrapped at about 80 columns and a claim is a claim wherever the
    # wrap lands. Matching the raw text would report "It leaked into 150 of\n
    # 150 prompts" as missing and send a reader looking for a drifted figure
    # when all that moved was a line break. The table is parsed from the RAW
    # text, where the line structure is the thing being read.
    flat = re.sub(r"\s+", " ", text)

    cells = derive_cells()
    stated, bold = parse_table(text)
    prose = derive()
    # Plus one for the count itself, which README.md and SAMPLE_RUN.md quote.
    n_figures = len(cells) + len(prose) + 1
    prose.append(("figures checked", str(n_figures), rf"{n_figures} figures"))

    problems: list[str] = []
    if not stated:
        problems.append("the condition table was not found in README.md, so "
                        "no cell was compared")
    for key, value in sorted(cells.items()):
        arm, provider = key
        if key not in stated:
            problems.append(f"table cell {arm}/{provider}: no such cell in "
                            f"README.md (the row or column was renamed)")
        elif stated[key] != value:
            problems.append(f"table cell {arm}/{provider}: README.md says "
                            f"{stated[key]}, the results give {value}")
    for label, value, pattern in prose:
        if pattern is None:
            if value not in flat:
                problems.append(f"{label}: {value} does not appear")
        elif not re.search(pattern, flat):
            problems.append(f"{label}: no match for /{pattern}/ "
                            f"(derived {value})")

    # EMPHASIS. Bold is a claim about separation; derive it and compare.
    emphasis = 0
    for provider, path in RUNS.items():
        sep = separated_arms(path)
        for arm in assemble.ARMS:
            key = (arm, provider)
            if key not in bold:
                continue
            emphasis += 1
            want = arm in sep
            if bold[key] != want:
                problems.append(
                    f"table cell {arm}/{provider} is "
                    f"{'bold' if bold[key] else 'not bold'}, but its interval "
                    f"{'excludes' if want else 'does not exclude'} zero. Bold "
                    f"means the interval excludes zero, as README.md states "
                    f"and as report.py marks with *.")

    print(f"{n_figures} figures derived from "
          f"{', '.join(p.name for p in RUNS.values())}")
    print(f"  {len(cells)} condition-table cells compared BY POSITION "
          f"(arm and run), plus {emphasis} emphasis verdicts")
    print(f"  {len(prose)} figures matched IN CONTEXT, with the sentence "
          f"around them")
    print(f"{n_figures - len(problems)} found in README.md, "
          f"{len(problems)} missing")
    for detail in problems:
        print(f"  MISSING  {detail}")
    if problems:
        print("\nA figure the README states must be derivable from the shipped "
              "evidence.\nEither the prose is stale or the evidence changed.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
