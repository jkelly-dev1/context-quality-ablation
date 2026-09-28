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
# `scripts/` is not a package, because a scripts/__init__.py gives setuptools
# a second top-level package, so the gates are imported the way an operator
# runs them, by putting that directory on the path.
sys.path.insert(0, str(ROOT / "scripts"))

import pytest

from cqa import assemble, grade, leak, prompt, questions, sources, world

import check_readme_numbers                                # noqa: E402
import mutation_suite                                      # noqa: E402
import preflight                                           # noqa: E402
import report                                              # noqa: E402

W = world.build()
QS = questions.build(W)
VALUES = leak.forbidden_values(W)


def ctx(q, arm):
    return assemble.context_for(W, q, arm)


# --------------------------------------------------------------- determinism
def test_the_world_is_identical_on_a_second_build_with_no_seed_involved():
    """There is one world, and this code always produces it.

    `world.build()` takes no seed, and its docstring says why: a seed argument
    would be a false affordance, because a reader who varied it and saw the
    same numbers would conclude the results were stable across worlds having
    only ever seen one. "Same seed, same output" would be a weaker property
    than the one asserted here.
    """
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
    stops producing that difference, instead of passing silently.
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
    coarseness instead of anything about governance.
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

    # The transform must also actually fire. A single question whose true
    # value is already a round number satisfies every bound above while the arm
    # does nothing at all, so the count is asserted: over the employee
    # questions the coarsening has to change some value and leave some alone,
    # or it is not lossy-and-observable, it is one or the other.
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
        names_one = questions.names_agreement_start(q)
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


def test_every_contract_key_is_what_a_source_showed():
    """A key no source system showed on the date asked is world truth, and an
    arm scored against it measures oracle access. Derived keys included: the
    renewal behind a day count, the acv of every contract behind a total.
    C009's key is 309 days, the renewal both systems still showed on the date
    asked."""
    assert preflight.contract_keys_not_shown(W, QS) == []
    assert preflight.KNOWN_UNSHOWN == set()
    c009 = next(q for q in QS if q.qid == "C009")
    assert c009.answer == {"days_until_renewal": 309}
    # The gate must still look: the old key, world truth no source showed on
    # that date, is flagged. Without this the empty list above passes whether
    # or not the gate checks anything.
    import dataclasses
    old = dataclasses.replace(c009, answer={"days_until_renewal": 339})
    assert preflight.contract_keys_not_shown(W, [old]) == ["C009"]


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
    prompt_fp = prompt.fingerprint(QS)
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
                "prompt_fingerprint": prompt_fp,
                "arm_fingerprint": arm_fp[arm],
            })
    path = tmp / "stamped.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    return path


def _run_report(path: Path, expect: int = None) -> str:
    """The report's stdout, with proof that the report actually ran.

    An empty string satisfies every `not in` assertion in this file. A child
    that never started (a typo in the path, an import error, a kill) hands
    back "" and then `assert "REFUSING TO REPORT" not in out` passes, as does
    `assert "micro-d" not in out`, and the test reports success about a run
    that did not happen. So the exit code is checked here, on every call, and
    `expect` pins it where the caller knows which verdict it wants: 0 for a
    rendered table, 2 for a refusal.
    """
    import subprocess
    r = subprocess.run(
        [sys.executable, "scripts/report.py", str(path)],
        cwd=str(Path(__file__).resolve().parents[1]),
        capture_output=True, text=True)
    assert r.returncode in (0, 2), (
        f"report.py exited {r.returncode}, so it neither rendered nor "
        f"refused:\n{r.stdout[-400:]}\n{r.stderr[-400:]}")
    if expect is not None:
        assert r.returncode == expect, (
            f"report.py exited {r.returncode}, expected {expect}:\n"
            f"{r.stdout[-400:]}")
    return r.stdout


def test_the_report_renders_a_stamped_results_file(tmp_path):
    out = _run_report(_stamped_results(tmp_path), expect=0)
    assert "REFUSING TO REPORT" not in out, out[:300]
    assert "micro-d" in out and "paired-d" in out


def test_the_report_refuses_results_that_do_not_match_the_code(tmp_path):
    path = _stamped_results(tmp_path)
    rows = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
    for r in rows:
        r["questions_fingerprint"] = "0000000000000000"
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    assert "REFUSING TO REPORT" in _run_report(path, expect=2)


def test_the_report_never_prints_a_difference_without_an_interval(tmp_path):
    """A ranking of noisy numbers is not a finding."""
    out = _run_report(_stamped_results(tmp_path), expect=0)
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
        out = _run_report(_stamped_results(Path(td), leaky_baseline=True),
                          expect=0)
    assert "resolved" in out.split("arms with any prompt leak:")[1][:80]


def test_a_comparison_that_cannot_be_made_does_not_print_as_a_zero():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "rep", Path(__file__).resolve().parents[1] / "scripts" / "report.py")
    rep = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rep)
    import random
    assert rep.paired_ci({}, {}, random.Random(1)) == (None, None, None)


def _report_module():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "rep", Path(__file__).resolve().parents[1] / "scripts" / "report.py")
    rep = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rep)
    return rep


def _paired_rows(diffs):
    """Synthetic arm/baseline rows whose per-question difference is `diffs`.

    Each question is graded out of 4 fields, so a difference of -25 points is
    one field lost. The baseline is always perfect, which makes the arm's
    per-question difference exactly the number asked for.
    """
    arm, base = {}, {}
    for i, d in enumerate(diffs):
        n = 4
        lost = round(-d * n / 100)
        qid = f"Q{i:03d}"
        base[qid] = {"grade": {"n_fields": n, "n_correct": n,
                               "all_correct": True}}
        arm[qid] = {"grade": {"n_fields": n, "n_correct": n - lost,
                              "all_correct": lost == 0}}
    return arm, base


def test_the_interval_is_computed_and_not_merely_printed():
    """paired_ci on data whose answer is known, in both directions.

    A degenerate interval (`return point, point, point`, zero width around the
    estimate) does not fail loudly; it agrees with whatever the point estimate
    happens to be. On the shipped Claude results it would star 9 of 9
    non-baseline arms and make the curve claim that a smaller budget beats the
    largest by more than noise, the opposite of what this repository concludes
    from the same rows.

    A real difference must therefore separate, noise must not, and the
    interval must be wider than the point in both cases.
    """
    import random
    rep = _report_module()

    # A real effect: every question loses ground, by varying amounts.
    arm, base = _paired_rows([-25.0] * 30 + [-50.0] * 30)
    pt, lo, hi = rep.paired_ci(arm, base, random.Random(rep.SEED))
    assert abs(pt - (-37.5)) < 1e-9, pt
    assert lo < pt < hi, (lo, pt, hi)
    assert hi < 0, (lo, hi, "a 37-point loss over 60 questions must separate")

    # Noise: the same magnitudes, half in each direction, mean zero.
    arm, base = _paired_rows(([-25.0, +25.0] * 30))
    pt, lo, hi = rep.paired_ci(arm, base, random.Random(rep.SEED))
    assert abs(pt) < 1e-9, pt
    assert lo < 0 < hi, (lo, pt, hi,
                         "an interval around zero must contain zero")

    # The width is a property of the data, not a constant: 60 questions
    # of pure noise give a wider interval than 60 questions that agree.
    arm, base = _paired_rows([-37.5] * 60)
    _, lo_tight, hi_tight = rep.paired_ci(arm, base, random.Random(rep.SEED))
    assert hi_tight - lo_tight == 0.0, (lo_tight, hi_tight)


def test_the_report_refuses_an_arm_whose_assembly_no_longer_matches(tmp_path):
    """The per-arm half of "results recorded by different code cannot be
    reported".

    Another test flips the question-set fingerprint. This one flips an arm's:
    without the per-arm check, the shipped `governed` rows (produced by a
    rounding transform) would go on printing "93.3 *" beside an identity
    transform that renders something else entirely.

    The arm must also be NAMED, because a refusal that does not say which
    condition is stale leaves the operator to re-run all ten.
    """
    path = _stamped_results(tmp_path)
    rows = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
    for r in rows:
        if r["arm"] == "governed":
            r["arm_fingerprint"] = "0000000000000000"
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    out = _run_report(path, expect=2)
    assert "REFUSING TO REPORT" in out, out[:400]
    assert "governed" in out, out[:400]
    # and it must not have printed a table anyway
    assert "micro-d" not in out, out[:400]


def test_a_fingerprint_over_no_questions_is_refused_rather_than_returned():
    """A stamp that survives having examined nothing is not a stamp.

    `context_for` raises on an arm it does not know, and the fingerprint
    functions loop over the question set to reach it, so with an empty set
    they never call it, and return the hash of the empty string, which is a
    plausible-looking hex stamp for no questions at all. The report compares
    row stamps against these, so the failure would be a run certified as
    matching code that rendered nothing.
    """
    import pytest as _pytest
    # match= because "raises ValueError" is satisfied by any ValueError,
    # including one from a typo in this test, and then the guard it names
    # could be gone while this stays green.
    for call, phrase in (
            (lambda: assemble.arm_fingerprint(W, [], "resolved"),
             "no questions: an arm fingerprint"),
            (lambda: assemble.curve_fingerprint(W, [], 600),
             "no questions: a curve fingerprint")):
        with _pytest.raises(ValueError, match=phrase):
            call()
    # and the real ones still differ from each other
    assert (assemble.arm_fingerprint(W, QS, "resolved")
            != assemble.arm_fingerprint(W, QS, "unresolved"))


def test_every_arm_that_renders_agreements_can_identify_the_one_asked_about():
    """"One arm changes one thing", held for the questions that name an
    agreement. They name it by start date, which both source systems carry,
    so the unresolved arm, which renders raw source rows, can identify it as
    well as the resolved baseline can. No question names the world's internal
    id, which neither source carries.
    """
    named = [q for q in QS if questions.names_agreement_start(q)]
    assert len(named) == 22
    assert not any(questions.names_internal_id(q) for q in QS)
    for q in named:
        d = questions.names_agreement_start(q)
        for arm in ("resolved", "unresolved"):
            assert d in ctx(q, arm), f"{q.qid}: {arm} does not state {d}"


def test_no_organization_holds_two_agreements_starting_the_same_day():
    """The start date names an agreement only while it is unique."""
    seen = {(k["org_id"], k["start_date"]) for k in W.contracts}
    assert len(seen) == len(W.contracts)


def test_the_report_refuses_results_recorded_under_a_different_prompt(tmp_path):
    """The third held-constant input: the prompt is hashed too.

    `cqa/prompt.py`'s own first line calls the prompt "the thing held constant
    while context varies". Without a prompt hash, rewriting the first rule of
    SYSTEM ("Answer strictly from the context") into "Use outside knowledge
    freely", which changes what the floor arm even means, would leave the
    suite, the pre-flight, the report and the figure checker all green.
    """
    path = _stamped_results(tmp_path)
    rows = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
    for r in rows:
        r["prompt_fingerprint"] = "0000000000000000"
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    out = _run_report(path, expect=2)
    assert "REFUSING TO REPORT" in out, out[:400]
    assert "prompt" in out.lower(), out[:400]
    assert "micro-d" not in out, out[:400]


def test_the_prompt_fingerprint_moves_with_the_instruction_and_not_the_context():
    """It must cover the prompt and only the prompt.

    Covering the context too would duplicate `arm_fingerprint` and make one
    arm's change invalidate all ten; covering nothing that can change would
    make it decoration.
    """
    live = prompt.fingerprint(QS)
    assert live == prompt.fingerprint(QS), "not deterministic"
    # A different instruction is a different fingerprint.
    original = prompt.SYSTEM
    try:
        prompt.SYSTEM = original.replace(
            "Answer strictly from the context.",
            "Use outside knowledge freely.")
        assert prompt.SYSTEM != original, "the rule being edited has moved"
        assert prompt.fingerprint(QS) != live
    finally:
        prompt.SYSTEM = original
    assert prompt.fingerprint(QS) == live, "the edit was not undone"
    # The context is NOT part of it: the placeholder is what gets hashed.
    assert prompt.fingerprint(QS) == prompt.fingerprint(QS)


def test_the_report_says_which_stamps_were_written_after_the_run(tmp_path):
    """A hash added afterwards is an assertion, and the report says so where
    the numbers are read.

    Every shipped row passes the report's three refusals, which means its
    stamps match this code, not that they were written when the generation
    was. Until the 2026-09-26 re-run, 360 curve rows and all 5,580 prompt
    stamps had been written afterwards; the rows shipped now carry none, so
    the shipped report must not print the line.

    Both directions: a file with no backfilled rows must NOT print the line,
    or the disclosure becomes decoration that appears everywhere.
    """
    path = _stamped_results(tmp_path)
    clean = _run_report(path, expect=0)
    assert "micro-d" in clean, clean[:300]      # it rendered a table
    assert "PROVENANCE" not in clean, clean[:300]

    rows = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
    for r in rows[:7]:
        r["prompt_fingerprint_backfilled"] = True
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    out = _run_report(path, expect=0)
    assert "PROVENANCE" in out, out[:400]
    assert "prompt 7" in out, out[:400]
    assert "assertion" in out, out[:400]
    # and the real evidence, every stamp written with its row, carries none
    root = Path(__file__).resolve().parents[1]
    shipped = _run_report(root / "results" / "sweep.jsonl", expect=0)
    assert "micro-d" in shipped, shipped[:300]
    assert "PROVENANCE" not in shipped, shipped[:300]


def test_the_shipped_results_still_describe_the_code_that_renders_them():
    """Run the report over every shipped file and require it to aggregate.

    This is the gate that makes an assembly change expensive instead of
    silent, so the suite does not have to guard constants one at a time. `results/*.jsonl` carries a hash of exactly the text each arm
    rendered when the money was spent; if an edit changes one byte of any of
    the ten arms or six budgets, these fingerprints stop matching and the
    report refuses here, in CI, and not the next time somebody happens to run
    it by hand.

    It is also the only test that reads the shipped evidence. Every other
    report test uses a synthetic file, because pointed at results/ they would
    exercise the refusal path and assert nothing.
    """
    root = Path(__file__).resolve().parents[1]
    for name in ("sweep.jsonl", "sweep_openai.jsonl", "sweep_replicate.jsonl"):
        out = _run_report(root / "results" / name, expect=0)
        assert "REFUSING TO REPORT" not in out, (name, out[:400])
        assert "micro-d" in out, (name, out[:200])


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


def _unstarted(q):
    """The asked organization's contracts that have not started on q.as_of,
    as the CRM_A agreement id and the CRM_B deal line that name each."""
    agrs, deals = [], []
    for m, k in enumerate(W.contracts):
        if k["org_id"] == q.org_id and k["start_date"] > q.as_of:
            agrs.append(k["contract_id"].replace("CTR", "AGR-"))
            deals.append(f"deal_id: {9000 + m}")
    return agrs, deals


def test_no_arm_ships_an_agreement_or_deal_that_has_not_started():
    """As-of filtering reached the baseline only; two other paths kept it.
    Checked in both systems' vocabularies: an AGR id and a CRM_B deal line."""
    offenders = []
    for q in QS:
        agrs, deals = _unstarted(q)
        for arm in assemble.ARMS:
            text = ctx(q, arm)
            lines = {ln.strip() for ln in text.split("\n")}
            offenders += [(q.qid, arm, x) for x in agrs if x in text]
            offenders += [(q.qid, arm, x) for x in deals if x in lines]
    assert not offenders, f"unstarted contracts shipped: {offenders[:5]}"


def test_the_curve_ships_no_unstarted_agreement_and_no_unstarted_deal():
    """The curve's ranking filters the asked organization's CRM_A agreements
    and, since 2026-09-26, its CRM_B deals by start date at every budget.
    Before that the deals were not filtered, and 32 of the 360 curve contexts
    carried the organization's own deal for a contract not yet started."""
    agr_hits, deal_hits = [], []
    for q in questions.curve_subset(QS):
        agrs, deals = _unstarted(q)
        for bkt in assemble.CURVE_BUDGETS:
            text = assemble.curve_context(W, q, bkt)
            lines = {ln.strip() for ln in text.split("\n")}
            agr_hits += [(q.qid, bkt, x) for x in agrs if x in text]
            if any(x in lines for x in deals):
                deal_hits.append((q.qid, bkt))
    assert not agr_hits, f"unstarted agreements in the curve: {agr_hits[:5]}"
    assert not deal_hits, f"unstarted deals in the curve: {deal_hits[:5]}"
    assert check_readme_numbers.curve_unstarted_deal_contexts() == []


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
    """The budget binds against a measured size, not against its own constant.

    A constant that appears in the code under test and in the expectation
    cannot be wrong, so changing it would pass. This pins the largest budget
    to a measured character count instead.
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


def _top_level_keys_of(text: str) -> set:
    """Keys at column zero. The arm drops TOP-LEVEL keys and nothing else.

    `_keys_of` matches at any indentation, so dropping one top-level key takes
    every nested key under it with it and the count means nothing.
    """
    return {m.group(1) for m in re.finditer(r"^([a-z_]+):", text, re.M)}


def test_the_incomplete_arm_drops_the_count_it_advertises_on_every_question():
    """No tolerance, no sampling, and the whole question set.

    A tolerance check of the realized fraction against the constant that
    produced it cannot fail for a wrong constant, and one question is not the
    set. What is asserted is the rendering: every question offers exactly
    CANDIDATE_FIELDS droppable keys, exactly DROPPED_FIELDS of them go, and
    `organization` never does. A world that started offering a different number
    of keys would change the realized fraction that README.md states, and this
    is what notices.
    """
    for q in QS:
        full = _top_level_keys_of(ctx(q, "resolved"))
        thin = _top_level_keys_of(ctx(q, "incomplete"))
        candidates = full - {"organization"}
        assert len(candidates) == assemble.CANDIDATE_FIELDS, (
            f"{q.qid} offers {len(candidates)} droppable keys, not "
            f"{assemble.CANDIDATE_FIELDS}: {sorted(candidates)}. The realized "
            f"drop fraction README.md states is DROPPED_FIELDS over this "
            f"number, so it has just moved.")
        dropped = full - thin
        assert len(dropped) == assemble.DROPPED_FIELDS, (
            q.qid, sorted(dropped))
        assert "organization" in thin, q.qid
    # The label quotes the rendering, not a round number. The label is built
    # from the two constants, so this cannot pass while the prose beside it
    # says 40 percent.
    assert assemble.ARM_LABEL["incomplete"] == (
        f"{assemble.DROPPED_FIELDS} of {assemble.CANDIDATE_FIELDS} fields "
        f"dropped ({100 * assemble.DROP_FRACTION:.1f} percent)")
    assert abs(assemble.DROP_FRACTION - 4 / 9) < 1e-12, assemble.DROP_FRACTION


def _script(name: str):
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        name, Path(__file__).resolve().parents[1] / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_one_price_table_and_every_consumer_reads_it():
    """Two published cost figures, three files that could state a price.

    `scripts/sweep.py` spends the money, `scripts/offline.py` estimates it
    before the run and `scripts/check_readme_numbers.py` rebuilds README.md's
    two cost figures after it. A consumer with its own copy of a price is the
    drift shape this rule removes, and in the checker it is worse than most: a
    checker with a stale price certifies the drift it exists to find.
    """
    scripts = str(Path(__file__).resolve().parents[1] / "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    import sweep                                          # noqa: PLC0415

    # Assert an effect a no-op could not produce. Comparing today's numbers
    # proves nothing: a hard-coded (1.00, 5.00) equals half of (2.00, 10.00)
    # for exactly as long as the price does not move, which is the situation
    # the one-table rule exists for. So move the price and require every
    # consumer to move with it. `offline` is re-executed here, and its
    # `import sweep` resolves to the module this test just edited.
    original = dict(sweep.PROVIDERS["anthropic"])
    try:
        sweep.PROVIDERS["anthropic"]["in"] = 7.0
        sweep.PROVIDERS["anthropic"]["out"] = 99.0
        offline = _script("offline")
        assert offline.RATES["sonnet-5 standard"] == (7.0, 99.0), (
            offline.RATES, "the estimator holds its own copy of the price")
        assert offline.RATES["sonnet-5 batch"] == (3.5, 49.5), (
            offline.RATES, "batch is half of standard; it is a rule about the "
            "standard rate, not a second pair of numbers")
    finally:
        sweep.PROVIDERS["anthropic"].update(original)
    assert _script("offline").RATES["sonnet-5 standard"] == (
        original["in"], original["out"]), "the price edit was not undone"
    # No file may reintroduce a literal price beside the one table.
    checker_src = (Path(__file__).resolve().parents[1] / "scripts"
                   / "check_readme_numbers.py").read_text()
    body = "\n".join(l for l in checker_src.splitlines()
                     if not l.lstrip().startswith("#"))
    for literal in ("12.00", "10.00", "2.00"):
        assert literal not in body, (
            f"{literal} is written into check_readme_numbers.py again; the "
            f"prices live in sweep.PROVIDERS")


def test_the_report_main_returns_a_verdict_ci_can_act_on(tmp_path,
                                                        monkeypatch):
    """The refusals print a sentence and set an exit code, and CI reads the
    code. Every other report test here reads the sentence out of stdout, which
    is the half that would still look right if `return 2` became `return 0`:
    the workflow step would pass while the tool printed REFUSING TO REPORT.
    """
    path = _stamped_results(tmp_path)
    monkeypatch.setattr(sys, "argv", ["report.py", str(path)])
    assert report.main() == 0

    # EVERY refusal, not one of them: each has its own `return 2`, and a test
    # that exercises one leaves the others free to become `return 0`.
    for field in ("questions_fingerprint", "prompt_fingerprint",
                  "arm_fingerprint"):
        rows = [json.loads(l) for l in _stamped_results(tmp_path).read_text()
                .splitlines() if l.strip()]
        for r in rows:
            r[field] = "0000000000000000"
        broken = tmp_path / f"broken_{field}.jsonl"
        broken.write_text("".join(json.dumps(r) + "\n" for r in rows))
        monkeypatch.setattr(sys, "argv", ["report.py", str(broken)])
        assert report.main() == 2, (
            f"the {field} refusal did not set a non-zero exit code")


def test_the_mutation_suite_main_returns_a_verdict_ci_can_act_on(monkeypatch,
                                                                capsys):
    """CI gates on this script, so its exit code is a verdict too.

    MUTATIONS is emptied or replaced instead of run. The suite's own sweep
    starts a pytest child per entry, and one of those children runs this test,
    so a test that called `main()` with the real table would re-enter the
    sweep from inside it. What is asserted is the mapping from state to exit
    code, which is the part a `return 0` would remove, and the sweep itself is
    proven by running it.
    """
    monkeypatch.setattr(mutation_suite, "MUTATIONS", [])
    assert mutation_suite.main() == 0

    monkeypatch.setattr(mutation_suite, "MUTATIONS", [{
        "name": "an entry whose target text is not in the file",
        "file": "cqa/assemble.py",
        "find": "a string that is not in assemble.py anywhere at all",
        "replace": "x",
        "test": "tests/test_harness.py::test_the_world_is_identical_on_a_"
                "second_build_with_no_seed_involved",
    }])
    with pytest.raises(SystemExit) as exc:
        mutation_suite.main()
    assert exc.value.code == 2, (
        "an entry that would patch nothing did not refuse to start")
    # Which failure, not just a failure. Any SystemExit satisfies the raises
    # above, including one from this test's own fixture, so the refusal has to
    # be identified by what it said.
    printed = capsys.readouterr().out
    assert "REFUSING TO START" in printed, printed[-400:]
    assert "occurs 0 times" in printed, printed[-400:]


def test_the_figure_checker_main_returns_a_verdict_ci_can_act_on(tmp_path,
                                                                monkeypatch):
    """CI runs the figure checker's `main()`, so its exit code is a verdict.

    A gate whose non-zero return is flipped to 0 goes on printing its own
    failure while the workflow step passes. Both directions are asserted: 0 on
    the shipped tree, and 1 on a README with a figure changed.
    """
    assert check_readme_numbers.main() == 0, (
        "the shipped README no longer checks out")

    root = Path(__file__).resolve().parents[1]
    broken = tmp_path / "README.md"
    text = (root / "README.md").read_text(encoding="utf-8")
    assert "| unresolved | **84.9**" in text
    broken.write_text(text.replace("| unresolved | **84.9**",
                                   "| unresolved | **70.7**"))
    monkeypatch.setattr(check_readme_numbers, "README", broken)
    assert check_readme_numbers.main() == 1, (
        "a wrong table cell did not fail the checker")


def test_the_leak_figures_are_matched_against_the_derived_count(tmp_path,
                                                               monkeypatch,
                                                               capsys):
    """README.md says the forbidden value reached the OUTPUT 0 times. Those
    patterns were literals, which matched whatever the rows said. Five rows
    that leak through the output and through inference must now fail the
    checker, and name both figures."""
    root = Path(__file__).resolve().parents[1]
    runs = {}
    for provider, path in check_readme_numbers.RUNS.items():
        copy = tmp_path / path.name
        rows = [json.loads(ln) for ln in path.read_text().splitlines()]
        if provider == "anthropic":
            flipped = 0
            for r in rows:
                if r["arm"] == "resolved" and flipped < 5:
                    r["governance"]["output_leak"] = True
                    r["governance"]["inferred_leak"] = True
                    flipped += 1
            assert flipped == 5
        copy.write_text("".join(json.dumps(r) + "\n" for r in rows))
        runs[provider] = copy
    monkeypatch.setattr(check_readme_numbers, "RUNS", runs)
    assert check_readme_numbers.README == root / "README.md"
    assert check_readme_numbers.main() == 1
    out = capsys.readouterr().out
    assert "anthropic output leaks: no match for /OUTPUT 5 times/" in out
    assert "anthropic inferred leaks: no match for /permitted fields 5 times/" \
        in out


def test_the_backfills_stamp_only_rows_that_carry_no_hash(tmp_path,
                                                          monkeypatch):
    """A row stamped at run time under other code is the evidence the report
    refuses on. Both backfills fill in an ABSENT stamp and leave a mismatched
    one alone."""
    import backfill_curve_fingerprint as bc
    import backfill_prompt_fingerprint as bp
    bkt = assemble.CURVE_BUDGETS[0]
    rows = [{"experiment": "arms", "arm": "resolved"},
            {"experiment": "arms", "arm": "resolved",
             "prompt_fingerprint": "0123456789abcdef"},
            {"experiment": "curve", "arm": f"budget{bkt}",
             "arm_fingerprint": "curve"},
            {"experiment": "curve", "arm": f"budget{bkt}",
             "arm_fingerprint": "fedcba9876543210"}]
    path = tmp_path / "rows.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    monkeypatch.setattr(sys, "argv", ["backfill", str(path)])
    assert bp.main() == 0
    assert bc.main() == 0
    out = [json.loads(ln) for ln in path.read_text().splitlines()]
    assert out[0]["prompt_fingerprint"] == prompt.fingerprint(QS)
    assert out[0]["prompt_fingerprint_backfilled"] is True
    assert out[1]["prompt_fingerprint"] == "0123456789abcdef"
    assert "prompt_fingerprint_backfilled" not in out[1]
    assert out[2]["arm_fingerprint"] not in ("curve", "fedcba9876543210")
    assert out[2]["arm_fingerprint_backfilled"] is True
    assert out[3]["arm_fingerprint"] == "fedcba9876543210"
    assert "arm_fingerprint_backfilled" not in out[3]


def test_a_local_endpoint_that_fails_on_the_floor_call_is_a_fail_line(
        monkeypatch):
    """Layer 2 asks twice per question. An error on the second, floor-arm call
    must end as the same FAIL line as one on the first, not a traceback."""
    import urllib.error
    calls = []

    def flaky(base_url, model, q, context):
        calls.append(context)
        if len(calls) == 2:
            raise urllib.error.URLError("connection reset")
        return dict(q.answer), {}
    monkeypatch.setattr(preflight, "ask_local", flaky)
    r = preflight.layer2(W, QS, "http://127.0.0.1:1", "m")
    assert len(calls) == 2
    assert r == [("local endpoint reachable", False,
                  "<urlopen error connection reset>")]


def test_the_local_endpoint_url_must_be_http():
    """`--local` is opened with urllib, which opens more than HTTP.

    An operator argument is not untrusted input, and this is not a hole
    somebody reaches through, but `urllib.request.urlopen` opens
    `file:///etc/passwd` as readily as an endpoint, and a tool that reads a
    file when it was told to call a model should refuse instead of returning a
    JSON parse error.
    """
    import pytest as _pytest
    for bad in ("file:///etc/passwd", "ftp://example.invalid",
                "localhost:11434", ""):
        with _pytest.raises(ValueError, match="must be an http"):
            preflight.ask_local(bad, "m", QS[0], "")
    # An http URL gets past the check and fails later, on the socket, which is
    # a different error and proves the guard is not refusing everything.
    with _pytest.raises(Exception) as exc:
        preflight.ask_local("http://127.0.0.1:1/", "m", QS[0], "")
    assert not isinstance(exc.value, ValueError) or \
        "must be an http" not in str(exc.value), exc.value

    # The second layer, asserted separately. The check above is a sentence in
    # one function; this is the opener the request actually goes through, and
    # it carries no FileHandler. `build_opener(HTTPHandler, HTTPSHandler)`
    # would carry one, because it adds the defaults to what it is given, and
    # would read /etc/passwd while looking restricted. So this asserts the
    # opener directly instead of trusting how it was built.
    # The sibling function, asserted so that only it can satisfy the check.
    # layer2 takes the same (base_url, model) and renders a sample of
    # questions before the first request is built. `raises(ValueError)` alone
    # does NOT test it: with layer2's own check removed, layer2 runs on and
    # calls ask_local, which raises the same ValueError with the same message
    # and the test stays green. So ask_local is replaced with something that
    # cannot be mistaken for it, and layer2 must refuse WITHOUT reaching it.
    def _must_not_be_reached(*a, **k):
        raise AssertionError("layer2 reached ask_local with a file:// URL, so "
                             "its own check did not fire")
    real_ask_local = preflight.ask_local
    try:
        preflight.ask_local = _must_not_be_reached
        with _pytest.raises(ValueError, match="must be an http"):
            preflight.layer2(W, QS[:1], "file:///etc/passwd", "m")
    finally:
        preflight.ask_local = real_ask_local
    assert preflight.ask_local is real_ask_local

    import urllib.request
    for url in ("file:///etc/passwd", "ftp://example.invalid/x"):
        with _pytest.raises(Exception) as exc:
            preflight._HTTP_ONLY.open(urllib.request.Request(url), timeout=5)
        assert "root:" not in str(exc.value), (url, exc.value)


def test_the_preflight_main_returns_a_verdict_ci_can_act_on(monkeypatch):
    """The same for the harness gate, without paying its 30 seconds twice.

    `layer1` is what does the work and is exercised for real by CI; what is
    unguarded is the MAPPING from a failed check to a non-zero exit, which is
    the part a `return 0` would silently remove.
    """
    # It parses sys.argv, and under pytest that is pytest's argv.
    monkeypatch.setattr(sys, "argv", ["preflight.py"])
    monkeypatch.setattr(
        preflight, "layer1",
        lambda w, qs, values: [("a check that failed", False, "")])
    assert preflight.main() == 1, "a failed check did not refuse to certify"
    monkeypatch.setattr(
        preflight, "layer1",
        lambda w, qs, values: [("a check that passed", True, "")])
    assert preflight.main() == 0


def test_the_default_credential_path_is_ignored_by_git():
    """SECURITY.md says credentials are never committed; this is what makes
    that true.

    `sweep.load_key` falls back to `./.env` when ENV_FILE is unset, so the
    shortest path an operator can take leaves a key file in the working tree.
    Untracked is not ignored: an untracked .env is exactly what `git add -A`
    picks up.
    """
    root = Path(__file__).resolve().parents[1]
    sweep_src = (root / "scripts" / "sweep.py").read_text()
    assert 'os.environ.get("ENV_FILE", ".env")' in sweep_src, (
        "the default credential path moved; this test names the path it is "
        "checking and must be updated with it")
    ignored = {l.strip() for l in (root / ".gitignore").read_text().splitlines()
               if l.strip() and not l.startswith("#")}
    assert ".env" in ignored, ".gitignore does not ignore the default .env"


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
    a, b, c = real.split("-")
    for probe in (real, real.replace("-", ""), real.replace("-", " "),
                  real.replace("-", "."), f"{a}/{b}/{c}", f"{a}_{b}_{c}",
                  f"({a}) {b}-{c}"):
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
    worse = (-7.5, -12.0, -2.0)            # separated, on the wrong side
    better = (3.0, 0.5, 6.0)               # separated, the prediction's side
    level = (0.8, -4.2, 6.7)               # not separated
    no_pairs = (None, None, None)          # no questions in common
    assert not report.curve_supports_prediction([worse, level, no_pairs])
    assert report.curve_supports_prediction([worse, better])
    assert not report.curve_supports_prediction([])


def test_the_shipped_curve_verdict_is_the_one_the_readme_reports(
        monkeypatch, capsys):
    """The verdict line itself, from main() on the shipped Claude rows. The
    function test above pins the rule; this pins that main() prints the
    verdict the rule gives and not a sentence of its own."""
    monkeypatch.setattr(sys, "argv", ["report.py",
                                      str(ROOT / "results" / "sweep.jsonl")])
    assert report.main() == 0
    out = capsys.readouterr().out
    assert "NO BUDGET BEATS THE LARGEST BY MORE THAN NOISE" in out
    assert "A SMALLER BUDGET BEATS THE LARGEST" not in out


def test_the_micro_and_paired_gap_is_measured_not_typed(monkeypatch, capsys):
    """The footer quotes how far the two averages differ. It is computed from
    the same rows, here independently of the loop that prints it."""
    path = ROOT / "results" / "sweep.jsonl"
    rows = [r for r in report.load(path)
            if r.get("experiment", "arms") == "arms"]
    by_arm = {}
    for r in rows:
        by_arm.setdefault(r["arm"], []).append(r)
    base_by_q = {r["qid"]: r for r in by_arm[report.BASE]}
    import random
    stats = report.paired_by_arm(by_arm, base_by_q,
                                 random.Random(report.SEED))
    base = report.field_acc(by_arm[report.BASE])
    gap = max(abs(report.field_acc(rs) - base - stats[arm][0])
              for arm, rs in by_arm.items() if stats[arm][0] is not None)
    monkeypatch.setattr(sys, "argv", ["report.py", str(path)])
    assert report.main() == 0
    out = capsys.readouterr().out
    assert f"differ by up to {gap:.1f} points" in out
    assert "seven" not in out


def test_the_floor_arm_carries_no_context_and_no_answer_in_its_prompt():
    """The floor must be a floor, or the whole comparison is against nothing.

    Two ways it can fail: the arm accidentally carries context, or the
    QUESTION TEXT states its own answer. The second is the silent one, because
    the arm still looks empty while the prompt gives the game away.
    """
    searched = 0
    for q in QS:
        assert ctx(q, "none") == "", q.qid
        sent = prompt.user_message(q, "")
        # The shipped predicate, not a second copy of it. If this and
        # scripts/preflight.py's floor check each computed the length rule for
        # themselves, a change to one would leave the other asserting
        # something else under the same name.
        for value in questions.distinctive_answer_values(q):
            assert value not in sent, (q.qid, value)
            searched += 1
    # MEASURED, not guessed: 113 of the 150 questions carry at least one
    # string answer of five characters or more, and the rest answer with an
    # integer or a date, which this predicate deliberately excludes. The floor
    # is below that count and well above zero, so a change that stopped
    # searching for most values fails here instead of passing silently.
    assert searched >= 100, (
        f"only {searched} values across {len(QS)} questions were distinctive "
        f"enough to search for, against 113 when this floor was measured, so "
        f"this test is close to vacuous")


def test_a_value_is_distinctive_at_five_characters_and_not_at_four():
    """The predicate the floor check searches with, pinned at its edge.

    Without this, widening MIN_DISTINCTIVE until nothing qualifies leaves both
    the pre-flight check and the test above green while neither looks for
    anything: the loop body simply stops executing. A threshold is a claim
    about which values are evidence, so it is asserted where it bites.
    """
    from cqa.questions import Question
    q = Question("X", "lookup", QS[0].as_of, "text",
                 {"five": "abcde", "four": "abcd", "number": 12345}, "ORG001")
    got = questions.distinctive_answer_values(q)
    assert "abcde" in got, got
    assert "abcd" not in got, got
    # Non-strings are excluded because a computed integer answer appears in
    # any prompt that states a date or a count, and searching for it would
    # report every question as leaking.
    assert "12345" not in got, got


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

    The table's shape is therefore asserted separately from its values. A
    condition that genuinely cannot be reported should say why in the prose
    and be dropped from the table, not left as a dash the checker reads as
    present.
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


def test_a_sweep_will_not_resume_into_rows_from_another_question_set(tmp_path):
    """Resuming skips every (qid, arm) already on file, whatever question set
    produced it, so a sweep after the questions change would make almost no
    calls and leave the old rows standing. It must refuse instead."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "sweep_under_test", ROOT / "scripts" / "sweep.py")
    sweep = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sweep)
    f = tmp_path / "rows.jsonl"
    f.write_text(json.dumps({"qid": "L001", "arm": "resolved",
                             "questions_fingerprint": "old"}) + "\n")
    assert sweep.stale_fingerprints(f, "new") == {"old"}
    assert sweep.stale_fingerprints(f, "old") == set()
    assert sweep.stale_fingerprints(tmp_path / "absent.jsonl", "new") == set()


def test_the_sweep_main_refuses_to_resume_into_another_question_set(
        tmp_path, monkeypatch):
    """The helper above can be right while main() ignores it. main() is run
    against a results file carrying another fingerprint and must refuse to
    resume before it reads a credential or appends a row.

    No model is reachable from here: the credential reader is replaced with
    one that fails the test, so a main() that went past the refusal stops at
    the client instead of calling a vendor.
    """
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "sweep_main_under_test", ROOT / "scripts" / "sweep.py")
    sweep = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sweep)

    def no_credential(*_a, **_k):
        raise AssertionError("main() went past the refusal to the client")
    monkeypatch.setattr(sweep, "load_key", no_credential)
    f = tmp_path / "rows.jsonl"
    body = json.dumps({"qid": "L001", "arm": "resolved",
                       "questions_fingerprint": "another-set"}) + "\n"
    f.write_text(body)
    monkeypatch.setattr(sys, "argv", ["sweep.py", "--out", str(f)])
    with pytest.raises(SystemExit) as exc:
        sweep.main()
    assert "REFUSING TO RESUME" in str(exc.value), exc.value
    assert "another-set" in str(exc.value)
    assert f.read_text() == body, "a refused sweep wrote to the results file"
