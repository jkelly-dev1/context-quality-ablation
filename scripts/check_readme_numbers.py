"""Rebuild README.md's figures from the shipped results and compare.

    python3 scripts/check_readme_numbers.py
    python3 scripts/check_readme_numbers.py --emit    print each row and its match

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
  when the value is short or common: zero, the question count and the
  generation count appear in any plausible README, so requiring only the bare
  value would count figures that cannot fail among the ones that can. Every
  figure whose bare value is short or common therefore carries a pattern, and
  a figure with no pattern is one whose value is distinctive on its own, a
  dollar cost.

It prints how many figures it checked, whether or not any are missing, so a
version that silently stopped deriving half of them is visible instead of clean.
That count is itself one of the figures, so README.md and SAMPLE_RUN.md cannot
go on quoting a count from a version of this file that derived fewer. Rows that
several runs derive identically (the same value in the same sentence) are
counted once, so the count is the number of distinct checks.

What it does not rebuild from the shipped rows: the 95 in "95 percent", which
defines the interval, and the figures of the runs these replaced, whose rows
no longer ship: their largest run-to-run drift, 3.4, and their unresolved-arm
micro-d, -19.7, -17.6 and -13.9. README.md labels each of those as the
replaced runs' figure. They are held below as constants, so an edit to them in
README.md still fails this check, but no shipped row re-derives them. `--emit`
prints every row with the text it matched, so what is covered can be measured.

The same run checks the few figures PREDICTIONS.md and GITHUB_DESCRIPTION.txt
state, and prints their count on a line of its own, so the README's count
stays the count of what the README states.

Exit status is 0 when every derived figure appears and 1 otherwise.
"""
from __future__ import annotations

import json
import random
import re
import sys
from collections import defaultdict
from fractions import Fraction
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
from cqa import assemble, questions, sources, world       # noqa: E402

README = ROOT / "README.md"
RUNS = {"anthropic": ROOT / "results" / "sweep.jsonl",
        "openai": ROOT / "results" / "sweep_openai.jsonl",
        # The replicate is checked too. It is a whole column of the headline
        # table and the sole source of the run-to-run drift figures, and
        # leaving it out meant nine table cells and every drift number in the
        # prose were outside the only thing that compares prose to evidence.
        "replicate": ROOT / "results" / "sweep_replicate.jsonl"}
BASE = "resolved"

# The figures of the runs these replaced, which README.md quotes as such. Their
# rows are in git history, not in results/, so nothing here can re-derive them;
# they are constants so that README.md cannot restate them differently.
REPLACED_MAX_DRIFT = "3.4"
REPLACED_UNRESOLVED = {"anthropic": "-19.7", "replicate": "-17.6",
                       "openai": "-13.9"}

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


def field_frac(rs) -> Fraction:
    """field_pct as an exact fraction, for comparisons where a tie is a tie."""
    c = sum(r["grade"]["n_correct"] for r in rs)
    t = sum(r["grade"]["n_fields"] for r in rs)
    return Fraction(c, t) if t else Fraction(0)


def side(arm_rs, base_rs) -> str:
    """Where an arm sits against the baseline, in the words README.md uses."""
    a, b = field_frac(arm_rs), field_frac(base_rs)
    return "below" if a < b else "above" if a > b else "level with"


def budgets_text(budgets) -> str:
    """[600, 1200] -> "600 and 1,200"."""
    parts = [f"{b:,}" for b in budgets]
    return parts[0] if len(parts) == 1 else (", ".join(parts[:-1])
                                             + " and " + parts[-1])


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


def provenance_figures() -> list[tuple[str, str, str | None]]:
    """Counts README.md states about the rows themselves and the tree."""
    import mutation_suite
    import preflight
    from datetime import date
    out: list[tuple[str, str, str | None]] = []
    every = [r for path in RUNS.values() for r in load(path)]
    # README.md says no shipped row carries a stamp written after it, which
    # this derives from the rows' own backfill markers rather than asserts.
    backfilled = sum(1 for r in every
                     if any(k.endswith("_backfilled") and v
                            for k, v in r.items()))
    out += [("shipped generations", f"{len(every):,}",
             rf"the {len(every):,} shipped generations"),
            ("rows carrying a stamp written afterwards",
             f"{backfilled}/{len(every):,}",
             rf"{backfilled} of the {len(every):,} generations carries a stamp "
             rf"written after its row")]
    rows = load(RUNS["anthropic"])
    n_curve = sum(r.get("experiment") == "curve" for r in rows)
    out.append(("curve rows in a run", f"{n_curve}/{len(rows)}",
                rf"{n_curve} of a run's {len(rows):,} rows, "
                rf"{100 * n_curve / len(rows):.1f}%"))
    out += [("mutation entries", str(len(mutation_suite.MUTATIONS)),
             rf"holds all {len(mutation_suite.MUTATIONS)}"),
            ("stale window", str(assemble.STALE_DAYS),
             rf"{assemble.STALE_DAYS} days on volatile fields")]
    # The words after each peak are derived too: a re-run that moves the
    # largest budget above or below the peak changes which one is true. Budgets
    # that tie exactly for the top score are all named, with "(tied)", so a
    # sentence naming one of them cannot pass for the whole peak.
    for provider, one, several, down, flat in (
            ("anthropic", "Claude peaks at a {}-token budget",
             r"Claude peaks at {} tokens \(tied\)",
             " and drifts down slightly after", ""),
            ("openai", "GPT climbs to {}", r"GPT climbs to {} \(tied\)",
             r"\s+and dips slightly at {}", r"\s+and stops")):
        peaks, top, dips = curve_shape(provider)
        lead = (one if len(peaks) == 1 else several).format(budgets_text(peaks))
        tail = (down if dips else flat).format(f"{top:,}")
        out.append((f"{provider} curve peak", "/".join(map(str, peaks)),
                    lead + tail))
    return out


def curve_unstarted_deal_contexts() -> list[tuple[str, int]]:
    """(qid, budget) for every curve context that carries the asked
    organization's CRM_B deal for a contract not started on the date asked.

    The curve's ranking filters both systems' agreements and deals by start
    date, so on the shipped code this is empty. README.md states the count it
    returns, so a ranking that stopped filtering either system fails here.
    """
    w = world.build()
    out = []
    for q in questions.curve_subset(questions.build(w)):
        deals = {f"deal_id: {9000 + m}" for m, k in enumerate(w.contracts)
                 if k["org_id"] == q.org_id and k["start_date"] > q.as_of}
        for bkt in assemble.CURVE_BUDGETS:
            lines = {ln.strip() for ln in
                     assemble.curve_context(w, q, bkt).split("\n")}
            if deals & lines:
                out.append((q.qid, bkt))
    return out


def renewal_key_figure(w, qs) -> tuple[str, str, str]:
    """The days-until-renewal key that differs from the world's own renewal.

    For each such question, the contract it asks about is the one whose
    source-shown renewal gives the key. A key is listed when the world's
    effective renewal on the date asked gives a different count, which is a
    correction no source had shown yet. README.md names the one question this
    reaches and both counts.
    """
    differ = []
    for q in qs:
        if "days_until_renewal" not in q.answer:
            continue
        key = q.answer["days_until_renewal"]
        truths = []
        for k in w.contracts_for(q.org_id, q.as_of):
            cid = k["contract_id"]
            shown = questions.shown_contract_value(w, cid, "renewal_date",
                                                   q.as_of)
            if (shown - q.as_of).days == key:
                truths.append((w.value_as_of("contract", cid, "renewal_date",
                                             q.as_of) - q.as_of).days)
        if truths and key not in truths:
            differ.append((q.qid, key, truths[0]))
    if len(differ) != 1:
        return ("renewal key a source decides", str(differ), r"(?!)")
    qid, key, truth = differ[0]
    return ("renewal key a source decides", f"{qid} {key}/{truth}",
            rf"{qid} is the one question where they differ: the world's "
            rf"corrected renewal is {truth} days away, and both systems still "
            rf"showed {key}")


def token_figures() -> list[tuple[str, str, str | None]]:
    """The token figures README.md states, from the rows' own usage counts.

    The unpoliced arm's size is compared with the resolved arm on the same
    questions. For the vendor ratio, input tokens are pooled over every
    (question, condition) cell both vendors answered.
    """
    out: list[tuple[str, str, str | None]] = []
    for provider in ("anthropic", "openai"):
        arms = _arms(RUNS[provider])
        base = {r["qid"]: r["usage"]["input"] for r in arms[BASE]}
        unp = {r["qid"]: r["usage"]["input"] for r in arms["unpoliced"]}
        common = sorted(set(base) & set(unp))
        diff = sum(unp[q] - base[q] for q in common)
        tokens = f"{diff / len(common):.0f}"
        share = 100 * diff / sum(base[q] for q in common)
        disp = DISPLAY[provider]
        out.append((f"{provider} unpoliced extra tokens and share",
                    f"{tokens}/{share:.1f}",
                    rf"{tokens} tokens larger on the {disp} run, "
                    rf"{share:.1f} percent"))

    cells = {}
    for provider in ("anthropic", "openai"):
        cells[provider] = {(r["qid"], r["arm"]): r["usage"]["input"]
                           for r in load(RUNS[provider])}
    both = set(cells["anthropic"]) & set(cells["openai"])
    ratio = (sum(cells["openai"][k] for k in both)
             / sum(cells["anthropic"][k] for k in both))
    out += [("cells both vendors answered", f"{len(both):,}",
             rf"all {len(both):,} matched cells"),
            ("GPT to Claude input-token ratio", f"{ratio:.2f}",
             rf"used {ratio:.2f} times the input tokens")]
    return out


def curve_shape(provider: str) -> tuple[list[int], int, bool]:
    """(peak budgets, largest budget, whether the largest scores below the peak).

    Every budget that ties for the top score is a peak, in budget order. The
    scores are compared as exact fractions, so a tie is a tie and not whichever
    budget a sort put first.
    """
    by_b = defaultdict(list)
    for r in load(RUNS[provider]):
        if r.get("experiment") == "curve":
            by_b[int(r["arm"].replace("budget", ""))].append(r)
    score = {b: field_frac(rs) for b, rs in by_b.items()}
    best = max(score.values())
    peaks = [b for b in sorted(by_b) if score[b] == best]
    top = max(by_b)
    return peaks, top, score[top] < best


# The two other documents that state figures. They are checked here, and
# counted apart from README.md's, so the README's own count stays the count
# of what the README states.
OTHER_DOCS = {"PREDICTIONS.md": ROOT / "PREDICTIONS.md",
              "GITHUB_DESCRIPTION.txt": ROOT / "GITHUB_DESCRIPTION.txt"}


def other_documents() -> list[tuple[str, str, str, str]]:
    """(document, label, derived value, pattern) for PREDICTIONS.md and the
    repository description."""
    (pa, _, da), (po, _, do) = curve_shape("anthropic"), curve_shape("openai")

    def level(peaks):
        # A dip follows the last of a tied peak; the first is named as where
        # the level stretch begins.
        return rf" \(level from {peaks[0]:,}\)" if len(peaks) > 1 else ""
    both = (rf"Both vendors' point estimates dip slightly after their peak, "
            rf"Claude's after {pa[-1]:,} tokens{level(pa)} and GPT's after "
            rf"{po[-1]:,}{level(po)}")
    # A re-run in which either curve stops dipping makes the sentence false
    # whatever its numbers say, so it can no longer match.
    dip = both if (da and do) else r"(?!)"
    n_questions = len(questions.build(world.build()))
    return [
        ("PREDICTIONS.md", "both curve peaks, and both curves dipping after",
         f"{pa[-1]} and {po[-1]}", dip),
        ("PREDICTIONS.md", "curve questions per budget",
         str(questions.CURVE_QUESTIONS),
         rf"{questions.CURVE_QUESTIONS} questions per budget"),
        ("GITHUB_DESCRIPTION.txt", "questions",
         str(n_questions), rf"{n_questions} questions"),
    ]


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
        ]
        # Built from the derived count, like every other row. A literal
        # pattern here would match README.md whatever the rows said.
        n_out = sum(r["governance"]["output_leak"] for r in rows)
        n_inf = sum(r["governance"]["inferred_leak"] for r in rows)
        out += [
            (f"{provider} output leaks", str(n_out),
             rf"OUTPUT {n_out} times"),
            (f"{provider} inferred leaks", str(n_inf),
             rf"permitted fields {n_inf} times"),
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
    # The effects the drift section sorts, on the two Claude runs. Micro-d is
    # field% minus the baseline's; paired-d is report.py's point estimate.
    def effects(path):
        by_arm = _arms(path)
        base_by_q = {r["qid"]: r for r in by_arm[BASE]}
        stats = report.paired_by_arm(by_arm, base_by_q,
                                     random.Random(report.SEED))
        b = field_pct(by_arm[BASE])
        return ({a: f"{field_pct(rs) - b:.1f}" for a, rs in by_arm.items()},
                {a: f"{st[0]:.1f}" for a, st in stats.items()
                 if st[0] is not None})
    m1, p1 = effects(RUNS["anthropic"])
    m2, p2 = effects(RUNS["replicate"])
    mo, _ = effects(RUNS["openai"])
    arms_of = {p: _arms(path) for p, path in RUNS.items()}
    # How many runs separate an arm, in the words the drift section uses.
    seps = {p: separated_arms(path) for p, path in RUNS.items()}

    def separates_in(*arms):
        n = sum(a in seps[p] for p in RUNS for a in arms)
        return "no run" if n == 0 else "some run"
    for label, arm, lead, with_paired in (
            ("incompleteness", "incomplete", "Incompleteness", False),
            ("unresolved entities", "unresolved", "unresolved entities", False),
            ("governance", "governed", "Governance", True),
            ("staleness", "stale", "Staleness", True)):
        pat = rf"{lead} \(micro-d {re.escape(m1[arm])} and {re.escape(m2[arm])}"
        if with_paired:
            pat += (rf"; paired-d {re.escape(p1[arm])} and "
                    rf"{re.escape(p2[arm])}\)")
        if arm == "governed":
            pat += rf" separates in {separates_in(arm)}"
        out.append((f"{label} across the two Claude runs",
                    f"{m1[arm]}/{m2[arm]}", pat))
    stale_move = abs(float(m1["stale"]) - float(m2["stale"]))
    out.append(("staleness movement between the Claude runs",
                f"{stale_move:.1f}", rf"moved {stale_move:.1f} points"))

    # Where the presentation arms and the policy bypass sit against the
    # baseline across all three runs. The sentence has no digit in it, and
    # its meaning inverts with one word, so the words are derived.
    def sides(*arms):
        found = {side(arms_of[p][a], arms_of[p][BASE])
                 for p in RUNS for a in arms}
        if found <= {"above", "level with"}:
            return "at or above" if "above" in found else "level with"
        if found <= {"below", "level with"}:
            return "at or below" if "below" in found else "level with"
        return "on both sides of"
    out.append(("presentation arms and the policy bypass against the baseline",
                f"{sides('diluted', 'nostructure')}/{sides('unpoliced')}",
                rf"Dilution and prose rendering sit "
                rf"{sides('diluted', 'nostructure')} the baseline in every run "
                rf"and separate in {separates_in('diluted', 'nostructure')}; "
                rf"the policy bypass lands {sides('unpoliced')} it"))

    # The headline section restates the unpoliced and baseline cells in prose,
    # with the side of the baseline each run landed on.
    cell = {p: {a: f"{field_pct(arms_of[p][a]):.1f}" for a in ("unpoliced", BASE)}
            for p in RUNS}
    s_a = side(arms_of["anthropic"]["unpoliced"], arms_of["anthropic"][BASE])
    s_r = side(arms_of["replicate"]["unpoliced"], arms_of["replicate"][BASE])
    s_o = side(arms_of["openai"]["unpoliced"], arms_of["openai"][BASE])
    out += [
        ("unpoliced against the baseline on the two Claude runs",
         f"{cell['anthropic']['unpoliced']}/{cell['replicate']['unpoliced']}",
         rf"scored {cell['anthropic']['unpoliced']} and "
         rf"{cell['replicate']['unpoliced']} percent against baselines of "
         rf"{cell['anthropic'][BASE]} and {cell['replicate'][BASE]}\. So it "
         rf"landed {s_a} the baseline in the first run and {s_r} it in the "
         rf"replicate\."),
        ("unpoliced against the baseline on GPT",
         f"{cell['openai']['unpoliced']}/{cell['openai'][BASE]}",
         rf"On GPT it was {cell['openai']['unpoliced']} against "
         rf"{cell['openai'][BASE]}, {s_o} it\."),
    ]

    # The floor, as the answer-key section states it.
    floors = {f"{field_pct(arms_of[p]['none']):.1f}"
              for p in ("anthropic", "openai")}
    n_floor = len(arms_of["anthropic"]["none"])
    floor = floors.pop() if len(floors) == 1 else None
    out.append(("floor on both vendors", str(floor),
                rf"both vendors scored {re.escape(floor)} percent across "
                rf"{n_floor} questions" if floor else r"(?!)"))

    out += [
        ("run-to-run max drift", f"{max(deltas):.1f}",
         rf"up to {max(deltas):.1f} POINTS"),
        ("run-to-run max drift, restated in Limits", f"{max(deltas):.1f}",
         rf"up to {max(deltas):.1f} points on these runs and "
         rf"{re.escape(REPLACED_MAX_DRIFT)} on the ones they replaced"),
        ("replaced runs' max drift (a constant, not re-derived)",
         REPLACED_MAX_DRIFT,
         rf"The replaced runs moved by up to "
         rf"{re.escape(REPLACED_MAX_DRIFT)} points"),
        ("run-to-run mean drift", f"{sum(deltas) / len(deltas):.2f}",
         rf"mean {sum(deltas) / len(deltas):.2f}"),
        ("conditions compared across runs", str(len(both)),
         rf"{len(both)} conditions"),
    ]

    # The unresolved arm on the current question set, against the replaced
    # runs' figures, and how much of the replaced effect the identifier
    # artifact accounts for, in the words README.md uses.
    shares = {"a fifth": Fraction(1, 5), "a quarter": Fraction(1, 4),
              "a third": Fraction(1, 3), "half": Fraction(1, 2),
              "two thirds": Fraction(2, 3)}

    def share(provider, now):
        f = 1 - float(now) / float(REPLACED_UNRESOLVED[provider])
        return min(shares, key=lambda w: abs(float(shares[w]) - f))
    now = {"anthropic": m1["unresolved"], "replicate": m2["unresolved"],
           "openai": mo["unresolved"]}
    old = REPLACED_UNRESOLVED
    out.append((
        "unresolved micro-d on the three runs, against the replaced runs'",
        "/".join(now.values()),
        rf"the arm's micro-d is {re.escape(now['anthropic'])} \(Claude\), "
        rf"{re.escape(now['replicate'])} \(replicate\) and "
        rf"{re.escape(now['openai'])} \(GPT\)\. The replaced runs, whose "
        rf"questions named agreements by internal id, gave "
        rf"{re.escape(old['anthropic'])}, {re.escape(old['replicate'])} and "
        rf"{re.escape(old['openai'])}, which puts the identifier's share of "
        rf"their effect at about {share('anthropic', now['anthropic'])} "
        rf"\(Claude\), {share('replicate', now['replicate'])} \(replicate\) "
        rf"and {share('openai', now['openai'])} \(GPT\)"))

    # The questions that name one of two agreements, and how the unresolved arm
    # does on them. They name it by start date, which both sources carry, so
    # the arm can identify it as the baseline does. README.md states the arm's
    # score on them beside the baseline's, so an arm that could not identify
    # them would show as a gap here.
    w = world.build()
    qs = questions.build(w)
    named = {q.qid for q in qs if questions.names_agreement_start(q)}
    out.append(("questions naming an agreement by start date", str(len(named)),
                rf"Of the {len(qs)} question texts, {len(named)} name one of "
                rf"an organization's two agreements"))
    out.append(("curve questions per budget",
                str(questions.CURVE_QUESTIONS),
                rf"The curve rests on {questions.CURVE_QUESTIONS} questions "
                rf"per budget, not {len(qs)}"))
    out.append(renewal_key_figure(w, qs))
    for provider, path in RUNS.items():
        disp = DISPLAY[provider]
        arms = _arms(path)
        on = [r for r in arms["unresolved"] if r["qid"] in named]
        b_on = [r for r in arms[BASE] if r["qid"] in named]
        out.append((f"{provider} unresolved and baseline on the named questions",
                    f"{field_pct(on):.1f}/{field_pct(b_on):.1f}",
                    rf"{field_pct(on):.1f} against {field_pct(b_on):.1f} "
                    rf"\({disp}\)"))
    out += token_figures()
    out += provenance_figures()

    hits = curve_unstarted_deal_contexts()
    n_cq = len(questions.curve_subset(questions.build(world.build())))
    n_ctx = n_cq * len(assemble.CURVE_BUDGETS)
    n_hq = len({qid for qid, _ in hits})
    out.append(("curve contexts carrying an unstarted deal",
                f"{len(hits)}/{n_ctx}",
                rf"{len(hits)} of the {n_ctx} curve contexts, on {n_hq} of "
                rf"the {n_cq} curve questions"))

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
    # A row several runs derive identically (the same value and the same
    # pattern, such as each run's generation count) matches the same sentence
    # each time, so it is one check and is counted once. Where the runs
    # differ, each keeps its own row and a mismatch still fails.
    prose, seen = [], set()
    for label, value, pattern in derive():
        if (value, pattern) not in seen:
            seen.add((value, pattern))
            prose.append((label, value, pattern))
    prose.append(("condition-table cells", str(len(cells)),
                  rf"The {len(cells)} condition-table cells"))
    # Plus one for the count itself, which README.md and SAMPLE_RUN.md quote.
    n_figures = len(cells) + len(prose) + 1
    prose.append(("figures checked", str(n_figures), rf"{n_figures} figures"))

    if "--emit" in sys.argv:
        for (arm, provider), value in sorted(cells.items()):
            print(f"table cell {arm}/{provider}\n{value}")
        for label, value, pattern in prose:
            m = re.search(pattern, flat) if pattern else None
            print(f"{label}\n{m.group(0) if m else value}")
        return 0

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
    others = other_documents()
    other_missing = []
    for doc, label, value, pattern in others:
        body = re.sub(r"\s+", " ", OTHER_DOCS[doc].read_text(encoding="utf-8"))
        if not re.search(pattern, body):
            other_missing.append(f"{doc}: {label}: no match for /{pattern}/ "
                                 f"(derived {value})")
    print(f"{len(others) - len(other_missing)} of {len(others)} figures found "
          f"in {' and '.join(OTHER_DOCS)}")
    problems += other_missing
    for detail in problems:
        print(f"  MISSING  {detail}")
    if problems:
        print("\nA figure the README states must be derivable from the shipped "
              "evidence.\nEither the prose is stale or the evidence changed.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
