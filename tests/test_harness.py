"""The harness proof. Everything here runs offline and costs nothing.

This is what must pass before any model call is paid for. The pilot's only job
is to find out whether the arms separate for a model; these tests establish
that they separate in the DATA, which is a different claim and the one that
would invalidate the experiment if it were false.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest

from cqa import assemble, grade, leak, prompt, questions, sources, world

W = world.build()
QS = questions.build(W)
VALUES = leak.forbidden_values(W)


def ctx(q, arm):
    return assemble.context_for(W, q, arm)


# --------------------------------------------------------------- determinism
def test_the_world_is_identical_on_a_second_build_from_the_same_seed():
    a, b = world.build(), world.build()
    assert a.orgs == b.orgs and a.contacts == b.contacts
    assert a.contracts == b.contracts and a.changes == b.changes


def test_every_arm_renders_for_every_question_without_raising():
    for q in QS:
        for arm in assemble.ARMS:
            ctx(q, arm)


def test_context_assembly_is_deterministic_including_the_sampled_arm():
    for q in QS:
        for arm in assemble.ARMS:
            assert ctx(q, arm) == ctx(q, arm)


# ------------------------------------------------------------ the answer key
def test_the_key_orders_by_effective_date_and_the_arrival_system_does_not():
    """The key must not re-derive itself from the function under test.

    Asserting q.answer == W.value_as_of(...) is a tautology: the key was
    PRODUCED by value_as_of, so both sides move together and the effective-
    versus-recorded distinction the whole repository rests on goes untested.

    The independent oracle is CRM_A, which applies a change when it ARRIVES.
    Inside the gap between effective and recorded the two must disagree, and
    the key must side with effective.
    """
    gaps = [ch for ch in W.changes
            if ch.entity == "contract" and ch.field == "renewal_date"
            and ch.recorded > ch.effective]
    assert gaps, "no late corrections seeded"
    checked = 0
    for ch in gaps:
        inside = ch.effective + timedelta(
            days=(ch.recorded - ch.effective).days // 2)
        arrival = sources.crm_a(W, inside)
        agr = next(a for a in arrival["agreements"]
                   if a["agreement_id"] == ch.entity_id.replace("CTR", "AGR-"))
        truth = W.value_as_of("contract", ch.entity_id, "renewal_date", inside)
        # The two orderings must actually disagree here, or the test is blind.
        assert agr["renews_on"] != truth.isoformat(), ch.entity_id
        assert truth == ch.value, ch.entity_id
        checked += 1
    assert checked, "no gap was exercised"


def test_the_lagging_system_is_behind_the_key_where_a_change_is_recent():
    """CRM_B trails by a fixed lag, so a recent change must not appear in it.

    Independent of value_as_of: it compares the rendered system against the
    key, and fails if the lag stops being observable.
    """
    behind = 0
    for ch in [c for c in W.changes
               if c.entity == "org" and c.field == "owner"]:
        just_after = ch.effective + timedelta(days=5)
        b = sources.crm_b(W, just_after)
        idx = int(ch.entity_id.replace("ORG", "")) - 1
        row = next(r for r in b["companies"] if r["company_id"] == 5000 + idx)
        truth = W.value_as_of("org", ch.entity_id, "owner", just_after)
        if row["rep"] != truth:
            behind += 1
    assert behind >= 3, (f"the lagging system trails the truth on only "
                         f"{behind} owner changes; the lag is not observable")


def test_the_question_set_is_stratified_and_every_stratum_is_populated():
    strata = {}
    for q in QS:
        strata[q.stratum] = strata.get(q.stratum, 0) + 1
    assert set(strata) == {"lookup", "resolution", "survivorship",
                           "computation"}
    # Balance, not mere presence. A naive items[:TARGET] truncation yields
    # 64/37/27/22 and clears a ">= 20" floor, so that floor tested nothing.
    target = questions.TARGET / len(strata)
    assert all(abs(n - target) <= target * 0.5 for n in strata.values()), \
        f"strata are not balanced: {strata}"
    assert sum(strata.values()) == questions.TARGET


# ------------------------------------------------------------- the arms work
def test_the_no_context_arm_carries_no_context_at_all():
    for q in QS:
        assert ctx(q, "none") == ""


def test_the_perfect_arm_contains_every_answer_value_it_can_state():
    # Computed answers are derived by the model, not stated, so they are
    # exempt. Everything else must be present or the ceiling is not a ceiling.
    derived = {"total_acv", "days_until_renewal", "organizations",
               "stage_changes", "agreements"}
    missing = []
    for q in QS:
        text = ctx(q, "perfect")
        for key, want in q.answer.items():
            if key in derived:
                continue
            if grade.normalize(want, key) not in _norms(text):
                missing.append((q.qid, key, want))
    assert not missing, missing


def test_the_resolved_arm_also_contains_them_since_it_is_the_baseline():
    derived = {"total_acv", "days_until_renewal", "organizations",
               "stage_changes", "agreements"}
    missing = []
    for q in QS:
        text = ctx(q, "resolved")
        for key, want in q.answer.items():
            if key in derived:
                continue
            if grade.normalize(want, key) not in _norms(text):
                missing.append((q.qid, key, want))
    assert not missing, missing


def test_the_unresolved_arm_fails_to_merge_the_split_identity():
    """String matching cannot see that two spellings are one customer.

    The resolved path merges on a normalized name and a domain key; the
    unresolved path matches the literal name, so the alias record never enters
    its context and the count it could support is wrong.
    """
    split = [o for o in W.orgs
             if W.defects.get(o["org_id"]) == "split_identity"]
    assert split, "no split identities seeded"
    checked = 0
    for o in split:
        alias = sources.split_alias(o)
        for q in QS:
            if q.org_id != o["org_id"] or q.stratum != "resolution":
                continue
            assert alias["name"] not in ctx(q, "unresolved"), q.qid
            assert alias["domain"] not in ctx(q, "unresolved"), q.qid
            checked += 1
    assert checked, "no resolution question on a split-identity org"


def test_the_stale_arm_differs_from_the_baseline_where_a_change_intervened():
    # S1 is asked 40 days after the owner changed, so a 30-day-stale context
    # still shows the change; S2 is well after. The arm must differ from the
    # baseline on at least one question or it is not an ablation.
    differing = [q.qid for q in QS
                 if ctx(q, "stale") != ctx(q, "resolved")]
    assert differing, "the stale arm is identical to the baseline everywhere"


def test_the_stale_arm_keeps_the_contact_roster_current():
    """Staleness is per-field, not a rewind of the whole context.

    The contact roster is what separates the two implementations on this data.
    Contacts change employer, so a whole-context rewind shows who worked
    somewhere 30 days ago; a volatile-field rewind ages the values that a
    broken sync actually ages and leaves membership current. The second
    assertion proves the first is not vacuous: it fails if the world ever
    stops producing that difference, rather than passing silently.
    """
    would_move = [q.qid for q in QS
                  if assemble._resolve(W, q, q.as_of)["contacts"]
                  != assemble._resolve(
                      W, q, q.as_of - timedelta(days=assemble.STALE_DAYS)
                  )["contacts"]]
    assert would_move, ("a whole-context rewind no longer changes any contact "
                        "roster, so this test can no longer detect one")
    for q in QS:
        fresh = assemble._resolve(W, q, q.as_of)
        for c in fresh["contacts"]:
            assert c["name"] in ctx(q, "stale"), (q.qid, c["name"])


def test_the_stale_arm_carries_the_old_value_of_every_volatile_field():
    """It must actually be stale, and stale on the fields that go stale."""
    moved = 0
    for q in QS:
        old = assemble._resolve(
            W, q, q.as_of - timedelta(days=assemble.STALE_DAYS))
        fresh = assemble._resolve(W, q, q.as_of)
        if old["account_owner"] == fresh["account_owner"]:
            continue
        moved += 1
        assert _value_of(ctx(q, "stale"), "account_owner") == \
            str(old["account_owner"]), q.qid
    assert moved >= 5, f"only {moved} questions have a stale owner to check"


def test_the_stale_arm_ages_the_agreement_fields_too():
    """Every volatile field, which is what the arm advertises.

    Three of them live on the customer record and are aged by a loop over
    named keys; two, `acv` and `renewal_date`, live on the AGREEMENTS and are
    aged by a second, separate loop keyed by agreement id. The test above
    exercises one field of the first loop, so the second loop can be removed
    outright with the suite green and the arm silently stops being stale on
    the two fields most likely to move.
    """
    checked = 0
    for q in QS:
        old = assemble._resolve(
            W, q, q.as_of - timedelta(days=assemble.STALE_DAYS))
        fresh = assemble._resolve(W, q, q.as_of)
        by_id = {k["agreement"]: k for k in old.get("agreements", [])}
        for k in fresh.get("agreements", []):
            was = by_id.get(k["agreement"])
            if not was:
                continue
            for field in ("acv", "renewal_date"):
                if str(was[field]) == str(k[field]):
                    continue                      # nothing moved; nothing to see
                rendered = ctx(q, "stale")
                assert str(was[field]) in rendered, (
                    f"{q.qid}: the stale arm shows the CURRENT {field} "
                    f"({k[field]}) where it should show {was[field]}")
                checked += 1
    assert checked >= 5, (
        f"only {checked} agreement fields actually move between the two "
        "dates, so this test cannot tell an aged arm from a fresh one")


def test_the_incomplete_arm_drops_fields_and_stays_reproducible():
    for q in QS:
        assert len(ctx(q, "incomplete")) < len(ctx(q, "resolved"))
    assert ctx(QS[0], "incomplete") == ctx(QS[0], "incomplete")


def test_the_diluted_arm_is_much_larger_and_still_governed():
    """Dilution varies the amount of irrelevant material and nothing else."""
    for q in QS:
        assert len(ctx(q, "diluted")) > 3 * len(ctx(q, "resolved"))
        assert not leak.scan(ctx(q, "diluted"), VALUES)["any"], q.qid


def test_the_unpoliced_arm_is_the_baseline_in_size_and_differs_only_in_policy():
    """It must isolate the policy bypass, not smuggle in a size change too.

    If this arm were also larger, a difference in accuracy could be dilution
    rather than governance, and this arm exists because bypassing the policy
    costs nothing a quality metric can see.
    """
    for q in QS:
        base, unpoliced = ctx(q, "resolved"), ctx(q, "unpoliced")
        # Assert the claim, not a tolerance. A size band is a proxy and a
        # loose one: a 40 percent allowance passed a context 1.39 times the
        # baseline while the document said "same size". What this arm claims
        # is that it differs from the baseline by the forbidden field and
        # nothing else, so remove those lines and the two must be identical.
        without = "\n".join(l for l in unpoliced.splitlines()
                            if "national_id" not in l)
        assert without == base, q.qid
        stripped = "\n".join(l for l in unpoliced.splitlines()
                              if "national_id" not in l)
        assert not leak.scan(stripped, VALUES)["any"], q.qid


def test_the_no_structure_arm_holds_the_same_facts_without_key_value_lines():
    q = next(x for x in QS if "owner" in x.answer and x.stratum == "lookup")
    text = ctx(q, "nostructure")
    assert "account_owner:" not in text
    assert str(q.answer["owner"]) in text


def test_the_governed_arm_coarsens_rather_than_destroys_a_permitted_field():
    """Governance must cost precision, not guarantee a wrong answer.

    A transform whose output can never equal the key turns this arm into a
    deterministic subtraction, and the reported effect is then the transform's
    coarseness rather than anything about governance.
    """
    qs = [x for x in QS if "employees" in x.answer]
    assert len(qs) > 1, "one question cannot show a transform is not a no-op"

    changed = 0
    for q in qs:
        governed = _value_of(ctx(q, "governed"), "employee_count")
        exact = _value_of(ctx(q, "resolved"), "employee_count")
        assert exact.isdigit(), exact
        assert governed.isdigit(), governed
        # Coarsened to TENS: never further than 5 from the true value, and
        # never a multiple of 100 unless the true value already was. Rounding
        # to hundreds is the failure this bound exists to catch; it makes the
        # arm a fixed subtraction under another name.
        assert abs(int(governed) - int(exact)) <= 5, (q.qid, governed, exact)
        assert int(governed) % 10 == 0, (q.qid, governed)
        if governed != exact:
            changed += 1

    # And the transform must actually fire. A single question whose true value
    # is already a round number satisfies every bound above while the arm does
    # nothing at all, so the count is asserted rather than assumed: over the
    # employee questions the coarsening has to change SOME value and leave
    # SOME alone, or it is not lossy-and-observable, it is one or the other.
    assert changed > 0, (
        f"the governed transform changed none of {len(qs)} employee counts; "
        "this arm is measuring nothing")
    assert changed < len(qs), (
        "the governed transform changed every employee count, so it can never "
        "be right and the arm is a deterministic subtraction")


def test_governance_does_not_make_every_such_question_unanswerable():
    """If no governed question can be right, the arm measures the transform."""
    winnable = 0
    for q in QS:
        if "employees" not in q.answer:
            continue
        if _value_of(ctx(q, "governed"), "employee_count") == str(
                q.answer["employees"]):
            winnable += 1
    assert winnable, ("no employee-count question is answerable under the "
                      "governed transform, so the arm is a fixed subtraction")


# -------------------------------------------------------------- the governance
def test_the_forbidden_field_never_reaches_the_baseline_prompt():
    for q in QS:
        text = prompt.user_message(q, ctx(q, "resolved"))
        assert not leak.scan(text, VALUES)["any"], q.qid


def test_the_forbidden_field_never_reaches_any_arm_except_the_bypass():
    leaked = set()
    for q in QS:
        for arm in assemble.ARMS:
            text = prompt.user_message(q, ctx(q, arm))
            if leak.scan(text, VALUES)["any"]:
                leaked.add(arm)
    assert leaked == {"unpoliced"}, leaked


def test_the_bypass_arm_leaks_on_every_question_which_is_the_seeded_defect():
    for q in QS:
        text = prompt.user_message(q, ctx(q, "unpoliced"))
        assert leak.scan(text, VALUES)["any"], q.qid


def test_a_leak_is_detected_by_shape_as_well_as_by_exact_value():
    # A reformatted or partial leak must still be caught, or the check only
    # finds the leak it already knew the value of.
    assert leak.scan("ref 123-45-6789 end", set())["any"]


# ------------------------------------------------------------------ grading
@pytest.mark.parametrize("want,got", [
    ("2026-11-30", "2026-11-30"),
    ("2026-11-30", "November 30, 2026"),
    ("2026-11-30", "11/30/2026"),
    (84000, "84,000"),
    (84000, "$84,000"),
    (84000, 84000.0),
    ("Dana Whitfield", "  dana   whitfield "),
    (12, "12 days"),
])
def test_the_normalization_policy_accepts_these_as_the_same_answer(want, got):
    assert grade.normalize(got, "renewal_date acv days") == \
        grade.normalize(want, "renewal_date acv days")


@pytest.mark.parametrize("want,got", [
    ("2026-11-30", "2026-12-30"),
    (84000, 84001),
    ("Dana Whitfield", "Dana Whitfeld"),
    ("Dana Whitfield", "Marcus Ellery"),
    ("O'Neill", "ONeill"),
])
def test_the_normalization_policy_keeps_these_apart(want, got):
    assert grade.normalize(got, "x") != grade.normalize(want, "x")


def test_a_near_miss_is_a_miss_and_partial_credit_is_recorded_per_field():
    q = next(x for x in QS if set(x.answer) == {"owner", "segment"})
    result = grade.grade_one(q.answer, {"owner": q.answer["owner"],
                                        "segment": "Nonsense"})
    assert result["n_correct"] == 1
    assert result["n_fields"] == 2
    assert result["all_correct"] is False


def test_a_missing_answer_scores_zero_rather_than_raising():
    q = QS[0]
    assert grade.grade_one(q.answer, None)["n_correct"] == 0
    assert grade.grade_one(q.answer, {})["n_correct"] == 0


def test_a_null_answer_is_wrong_not_blank_so_the_floor_can_score_zero():
    q = QS[0]
    got = {k: None for k in q.answer}
    assert grade.grade_one(q.answer, got)["n_correct"] == 0


# ------------------------------------------------------------------ helpers
def _supported(text: str, token: str) -> bool:
    """The token must appear as a KEY, anchored to the start of its line.

    A plain substring test cannot tell a key from a key that merely contains
    it: "_stage_history_removed" contains "stage_history". Anchoring to the
    start of the line and requiring the colon is what turns this into an
    assertion about a named field rather than about the presence of some
    characters.

    The match is exact, with no trailing wildcard. A wildcard closes the
    prefix hole and leaves the suffix one open, so "stage_history_REMOVED"
    would satisfy a check for "stage_history". The alias table names each key
    in full, so no wildcard is needed.
    """
    return bool(re.search(rf"^\s*{re.escape(token)}:", text, re.M))


def _norms(text: str) -> set[str]:
    out = set()
    for tok in re.split(r"[\n]", text):
        if ":" in tok:
            tok = tok.split(":", 1)[1]
        tok = tok.strip().lstrip("- ")
        if tok:
            out.add(grade.normalize(tok, "renewal_date acv days"))
            out.add(grade.normalize(tok, ""))
    return out


def _value_of(text: str, key: str) -> str:
    m = re.search(rf"^\s*{re.escape(key)}:\s*(.+)$", text, re.M)
    return m.group(1).strip() if m else ""


# ------------------------------------- properties a passing suite can still miss
# Everything above can pass while the question set is unanswerable, because
# every assertion above is about the DATA and these are about whether a
# question can be answered at all. A defect of that kind depresses every arm
# equally, so it never shows up as a difference between them.

def test_no_question_asks_for_a_single_agreement_field_ambiguously():
    """An org with two agreements makes "the renewal date" unanswerable.

    A model that returns null to an ambiguous question is behaving correctly,
    so an ambiguous question measures nothing. Either the organization holds
    exactly one agreement or the question text names the one it means.
    """
    per_agreement = {"renewal_date", "acv", "days_until_renewal"}
    bad = []
    for q in QS:
        if not (set(q.answer) & per_agreement):
            continue
        if "total" in " ".join(q.answer):
            continue
        n = len(W.contracts_for(q.org_id, q.as_of))
        names_one = re.search(r"\bCTR\d+\b", q.text)
        if n > 1 and not names_one:
            bad.append((q.qid, q.org_id, n))
    assert not bad, f"ambiguous single-agreement questions: {bad}"


SUPPORTS = {
    "owner": "account_owner", "segment": "segment",
    "stage": "lifecycle_stage", "stage_changes": "stage_history",
    "hq_state": "hq_state", "employees": "employee_count",
    "organization": "organization",
    "organizations": "source_records_merged",
    "source_records": "source_records_merged",
    "renewal_date": "renewal_date",
    "acv": "acv", "total_acv": "acv", "agreements": "agreements",
    "days_until_renewal": "renewal_date",
}


def test_the_perfect_arm_is_never_a_stub_that_cannot_support_its_answer():
    """A ceiling arm must contain what its own question needs.

    Size is not the property to assert; a minimal context is exactly what
    this arm is for. Support is this: a key with no branch in the builder produces
    a smaller context rather than an error, and an unanswerable ceiling drags
    every comparison made against it.
    """
    missing = []
    for q in QS:
        text = ctx(q, "perfect")
        for key in q.answer:
            token = SUPPORTS.get(key)
            if token and not _supported(text, token):
                missing.append((q.qid, key, token))
    assert not missing, f"ceiling context cannot support: {missing}"


def test_every_answer_key_is_supported_by_the_baseline_context_too():
    """The baseline must be able to answer, or the arms below it mean nothing.

    A field that only the ceiling arm carries makes every other arm
    structurally unable to answer, and the spread between them is then a
    missing field rather than an ablation effect.
    """
    missing = []
    for q in QS:
        text = ctx(q, "resolved")
        for key in q.answer:
            token = SUPPORTS.get(key)
            if token and not _supported(text, token):
                missing.append((q.qid, key, token))
    assert not missing, f"baseline cannot support: {missing}"


# ------------------------------------------- the report may not assert loosely
def _stamped_results(tmp: Path, leaky_baseline: bool = False) -> Path:
    """A synthetic results file carrying the CURRENT fingerprint.

    The report tests must actually render a report. Pointing them at the
    shipped results made them exercise only the refusal path, so they returned
    early and asserted nothing, which silently disabled the guards on four
    other fixes at the moment the fingerprint gate was added.
    """
    fp = questions.fingerprint(QS)
    arm_fp = {a: assemble.arm_fingerprint(W, QS, a) for a in assemble.ARMS}
    rows = []
    for q in QS:
        for arm in assemble.ARMS:
            n = len(q.answer)
            correct = 0 if arm == "none" else n
            leak_here = arm == "unpoliced" or (leaky_baseline
                                               and arm == "resolved")
            rows.append({
                "experiment": "arms", "qid": q.qid, "arm": arm,
                "stratum": q.stratum, "as_of": q.as_of.isoformat(),
                "answer": dict(q.answer),
                "grade": {"fields": {}, "n_fields": n, "n_correct": correct,
                          "all_correct": correct == n},
                "governance": {"prompt_leak": leak_here, "prompt_values": [],
                               "output_leak": False, "output_values": [],
                               "inferred_leak": False, "inferred_values": []},
                "usage": {"input": 800, "output": 40},
                "model": "test", "effort": "low",
                "questions_fingerprint": fp,
                "arm_fingerprint": arm_fp[arm],
            })
    path = tmp / "stamped.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    return path


def _run_report(path: Path) -> str:
    import subprocess
    return subprocess.run(
        [sys.executable, "scripts/report.py", str(path)],
        cwd=str(Path(__file__).resolve().parents[1]),
        capture_output=True, text=True).stdout


def test_the_report_renders_a_stamped_results_file(tmp_path):
    out = _run_report(_stamped_results(tmp_path))
    assert "REFUSING TO REPORT" not in out, out[:300]
    assert "micro-d" in out and "paired-d" in out


def test_the_report_refuses_results_that_do_not_match_the_code(tmp_path):
    path = _stamped_results(tmp_path)
    rows = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
    for r in rows:
        r["questions_fingerprint"] = "0000000000000000"
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    assert "REFUSING TO REPORT" in _run_report(path)


def test_the_report_never_prints_a_difference_without_an_interval(tmp_path):
    """A ranking of noisy numbers is not a finding."""
    out = _run_report(_stamped_results(tmp_path))
    delta = re.compile(r"[-+]\d+\.\d")
    interval = re.compile(r"\[\s*[-+]?\d+\.\d,\s*[-+]?\d+\.\d\]")
    naked = [l.strip()[:70] for l in out.splitlines()
             if not l.lstrip().startswith(("micro-d", "paired-d"))
             and delta.search(l) and not interval.search(l)]
    assert not naked, f"differences printed with no interval: {naked}"


def test_the_report_names_the_arms_that_leak_rather_than_asserting_the_rest():
    """The summary was unconditional and would deny a leak shown above it."""
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        out = _run_report(_stamped_results(Path(td), leaky_baseline=True))
    assert "resolved" in out.split("arms with any prompt leak:")[1][:80]


def test_a_comparison_that_cannot_be_made_does_not_print_as_a_zero():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "rep", Path(__file__).resolve().parents[1] / "scripts" / "report.py")
    rep = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rep)
    import random
    assert rep.paired_ci({}, {}, random.Random(1)) == (None, None, None)


# ---------------------------------- guards for fixes nothing else was testing
# A mutation audit reintroduced each fix's original defect and found twelve
# that no test noticed. A fix nothing guards is one edit from being undone
# silently, which is the same position as not having fixed it.

def test_a_contact_email_follows_them_to_their_new_employer():
    """The seeded email change was never read by any consumer.

    The world emitted it and _resolve, crm_a and crm_b all took the base row,
    so the context named one employer on the org line and another in the
    address, on exactly the resolution questions this world exists to pose.
    """
    moves = [ch for ch in W.changes
             if ch.entity == "contact" and ch.field == "org_id"]
    assert moves, "no contact moves seeded"
    for ch in moves:
        after = ch.effective + timedelta(days=30)
        org = W.value_as_of("contact", ch.entity_id, "org_id", after)
        domain = next(o["domain"] for o in W.orgs if o["org_id"] == org)
        for rendered in (
                W.value_as_of("contact", ch.entity_id, "email", after),
                next(r["email"] for r in sources.crm_a(W, after)["contacts"]
                     if r["contact_id"] == ch.entity_id.replace("CON", "CTC-"))):
            assert rendered.endswith(domain), (ch.entity_id, rendered, domain)


def test_no_arm_and_no_curve_budget_ships_an_agreement_that_has_not_started():
    """As-of filtering reached the baseline only; two other paths kept it."""
    offenders = []
    for q in QS:
        future = [k["contract_id"].replace("CTR", "AGR-")
                  for k in W.contracts
                  if k["org_id"] == q.org_id and k["start_date"] > q.as_of]
        if not future:
            continue
        texts = {a: ctx(q, a) for a in assemble.ARMS}
        texts["curve"] = assemble.curve_context(
            W, q, assemble.CURVE_BUDGETS[-1])
        for name, text in texts.items():
            for agr in future:
                if agr in text:
                    offenders.append((q.qid, name, agr))
    assert not offenders, f"future agreements shipped: {offenders[:5]}"


def test_no_seeded_stage_change_restates_the_stage_already_in_effect():
    for o in W.orgs:
        current = o["stage"]
        for ch in [c for c in W.changes if c.entity == "org"
                   and c.entity_id == o["org_id"] and c.field == "stage"]:
            assert ch.value != current, (o["org_id"], ch.value)
            current = ch.value


def test_the_prose_arm_carries_list_values_and_not_only_dict_values():
    """stage_history is a list of strings and was silently dropped."""
    with_history = [q for q in QS
                    if "stage_history:" in ctx(q, "resolved")]
    assert with_history, "no question carries a stage history"
    for q in with_history[:20]:
        history = [l.strip("- ").strip()
                   for l in ctx(q, "resolved").splitlines()
                   if re.match(r"^\s+- \d{4}-\d{2}-\d{2}:", l)]
        prose = ctx(q, "nostructure")
        for entry in history:
            assert entry.split(":")[0] in prose, (q.qid, entry)


def test_the_curve_budget_binds_against_a_measured_size_not_its_own_constant():
    """The old assertion used CHARS_PER_TOKEN on both sides of the compare.

    A constant that appears in the code under test and in the expectation
    cannot be wrong, so changing it passed. This pins the largest budget to a
    measured character count instead.
    """
    q = QS[0]
    smallest = len(assemble.curve_context(W, q, assemble.CURVE_BUDGETS[0]))
    assert smallest < 1200, smallest
    assert assemble.CHARS_PER_TOKEN < 3.0, assemble.CHARS_PER_TOKEN


def test_the_curve_subset_is_drawn_equally_from_every_stratum():
    sub = questions.curve_subset(QS)
    counts = {}
    for q in sub:
        counts[q.stratum] = counts.get(q.stratum, 0) + 1
    assert len(set(counts.values())) == 1, counts
    assert sum(counts.values()) == questions.CURVE_QUESTIONS


def test_the_incomplete_arm_drops_the_fraction_it_advertises():
    q = QS[0]
    full = _keys_of(ctx(q, "resolved"))
    thin = _keys_of(ctx(q, "incomplete"))
    dropped = len(full - thin) / len(full)
    assert abs(dropped - assemble.DROP_FRACTION) < 0.12, (dropped, full - thin)


def test_the_cost_estimator_shares_the_one_token_constant():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "off", Path(__file__).resolve().parents[1] / "scripts" / "offline.py")
    off = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(off)
    assert off.CHARS_PER_TOKEN is assemble.CHARS_PER_TOKEN


def test_a_reformatted_forbidden_value_is_still_a_leak():
    """The detector's own test only ever exercised the dashed shape."""
    real = sorted(VALUES)[0]
    for probe in (real, real.replace("-", ""), real.replace("-", " "),
                  real.replace("-", ".")):
        assert leak.scan(f"the reference is {probe} end", VALUES)["any"], probe
    assert not leak.scan("the owner is Dana Whitfield", VALUES)["any"]


def _keys_of(text: str) -> set:
    return {m.group(1) for m in re.finditer(r"^\s*([a-z_]+):", text, re.M)}


def test_the_curve_verdict_requires_the_difference_to_point_the_right_way():
    """A budget that is significantly WORSE is not evidence for the prediction.

    The prediction is that a SMALLER budget scores HIGHER than the largest.
    An interval excluding zero on the negative side is the opposite claim, and
    a verdict keyed on "separated in either direction" reads a losing budget
    as confirmation.
    """
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "rep", Path(__file__).resolve().parents[1] / "scripts" / "report.py")
    rep = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rep)
    src = (Path(__file__).resolve().parents[1] / "scripts"
           / "report.py").read_text()
    assert "sep_any = sep_any or lo > 0" in src, \
        "the verdict must key on the lower bound, not on mere separation"
    assert "sep_any = sep_any or mark ==" not in src


def test_the_floor_arm_carries_no_context_and_no_answer_in_its_prompt():
    """The floor must be a floor, or the whole comparison is against nothing.

    Two ways it can fail: the arm accidentally carries context, or the
    QUESTION TEXT states its own answer. The second is the quiet one, because
    the arm still looks empty while the prompt gives the game away.
    """
    for q in QS:
        assert ctx(q, "none") == "", q.qid
        sent = prompt.user_message(q, "")
        for value in q.answer.values():
            if isinstance(value, str) and len(str(value)) > 4:
                assert str(value) not in sent, (q.qid, value)


def test_every_prompt_states_the_as_of_date_it_must_be_answered_from():
    """The whole experiment is time-dependent and the date is one f-STRING.

    That system prompt instructs "Answer as of the AS-OF DATE given". Every
    arm assembles its context as of a specific date, the stale arm exists
    solely to disagree with it, and the answer key is computed from it. Remove
    the line from user_message and all 1,860 prompts of a run lose the date
    while the instruction to honor it remains, and the preflight check "every
    prompt carries its own question" looks only for the question text, so it
    stays green too.
    """
    for q in QS:
        msg = prompt.user_message(q, ctx(q, "resolved"))
        assert q.as_of.isoformat() in msg, (
            f"{q.qid}: the prompt does not state its as-of date")
        assert "AS-OF DATE:" in msg, q.qid


def test_the_as_of_date_in_the_prompt_is_the_one_the_context_was_built_from():
    """Stating A date is not enough; it has to be THIS question's date. Two
    questions with different as-of dates must not produce the same header."""
    dates = {q.as_of for q in QS}
    assert len(dates) > 1, "every question shares one date; this proves nothing"
    for q in QS:
        msg = prompt.user_message(q, ctx(q, "resolved"))
        others = [d.isoformat() for d in dates if d != q.as_of]
        header = msg.split("CONTEXT:")[0]
        assert q.as_of.isoformat() in header, q.qid
        for other in others:
            assert other not in header, (
                f"{q.qid}: the header also carries {other}")


def test_a_value_reconstructed_from_permitted_fields_is_counted_as_a_leak():
    """The count the README publishes as zero.

    "reconstructed from permitted fields 0 times" is the one number in the
    leak section worth publishing if it ever moves, and `inferred`, the set of
    forbidden values present in the ANSWER but absent from the PROMPT, is the
    only thing that can move it. Nothing called it. Replacing it with an empty
    list makes the count structurally incapable of firing, and a zero that
    cannot become anything else is not a measurement.
    """
    forbidden = {"91000", "Palo Alto"}
    # Present in the answer, absent from the prompt: reconstructed.
    out = leak.assess("no secrets here", "the figure is 91000", forbidden)
    assert out["inferred_leak"] is True
    assert out["inferred_values"] == ["91000"]

    # Present in both: an ordinary prompt leak, NOT an inferred one. The
    # distinction is the finding, so it is asserted in both directions.
    out = leak.assess("the figure is 91000", "the figure is 91000", forbidden)
    assert out["prompt_leak"] is True
    assert out["inferred_leak"] is False, (
        "a value the prompt handed over was scored as reconstructed")

    # In neither: silent.
    out = leak.assess("nothing", "nothing", forbidden)
    assert out["inferred_leak"] is False and out["output_leak"] is False


def test_the_top_budget_does_not_reach_the_end_of_the_ranked_material():
    """The curve's stated limit, asserted so the prose cannot drift from it.

    This world holds about 6,900 tokens of ranked facts per question and the
    largest budget keeps roughly 69% of it, so every comparison against the
    largest budget is a comparison against a truncated context and the curve
    never reaches a flat part. That is a real limit on what the curve can say,
    it is stated in assemble.py beside CURVE_BUDGETS, and this test is what
    keeps the stated figure and the world in step.
    """
    top = assemble.CURVE_BUDGETS[-1]
    ratios = []
    for q in QS:
        full = len(assemble.curve_context(W, q, 10 ** 9))
        assert full > 0, q.qid
        ratios.append(len(assemble.curve_context(W, q, top)) / full)
    kept = sum(ratios) / len(ratios)
    assert kept < 0.95, (
        f"the top budget now keeps {kept:.0%} of the ranked material; the "
        "curve may saturate after all and assemble.py's note is stale")
    assert 0.55 < kept < 0.85, (
        f"the top budget keeps {kept:.0%}; assemble.py says roughly 69%")


def test_the_condition_table_has_a_value_in_every_cell():
    """A blank cell is a claim, and the number checker cannot see it.

    check_readme_numbers.py requires every figure it derives to appear
    SOMEWHERE in the document, which is the right design for a percentage
    buried in a paragraph and the wrong one for a missing table cell: a value
    that happens to match another row's passes, and a cell replaced by a dash
    removes a figure without removing any string.

    So the table's shape is asserted separately from its values. A condition
    that genuinely cannot be reported should say why in the prose and be
    dropped from the table, not left as a dash the checker reads as present.
    """
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    header = "| condition | Claude | Claude replicate | GPT | what it removes |"
    assert header in readme, "the condition table's header changed"
    body = readme.split(header, 1)[1].split("\n\n", 1)[0].splitlines()
    rows = [ln for ln in body if ln.startswith("|") and not set(ln) <= set("|- ")]
    assert len(rows) == len(assemble.ARMS), (
        f"{len(rows)} table rows against {len(assemble.ARMS)} arms")
    for row in rows:
        cells = [c.strip().strip("*") for c in row.strip("|").split("|")]
        condition, values = cells[0], cells[1:4]
        for col, value in zip(("Claude", "replicate", "GPT"), values):
            assert value not in ("", "--", "-", "n/a"), (
                f"{condition}: the {col} cell is blank. If that run cannot be "
                f"reported, say so in the prose and drop the row.")
            float(value)   # raises if it is not a figure at all
