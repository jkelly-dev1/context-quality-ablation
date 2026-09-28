"""The ten arms. Model, prompt and question set are fixed; only this varies.

An arm is a function from (world, question) to the exact text placed in the
prompt. Everything that distinguishes one arm from another lives here, so a
difference in the results is attributable to one named change in context and
not to a difference in wording, ordering or instruction.

Two rules that make the ablation mean anything:

  One arm changes one thing. Diluted differs from resolved in the amount of
  irrelevant material and in nothing else: not in policy, not in field
  selection, not in the entities included. An arm that moves two variables
  cannot attribute its own result.

  THE `unresolved` ARM BREAKS THIS RULE AND THE BREAK IS PUBLISHED. 22 of the
  150 questions name an agreement by the world's internal id, CTRnnn, which
  only the RESOLVED view renders; this arm renders raw source rows, and
  neither source system carries that id. So on those 22 it varies the
  identifier space as well as resolution, the model correctly answers null,
  and about half the arm's reported effect is that rather than resolution.
  Excluding them the effect is roughly -11 instead of -19.7, still separates,
  still replicates and keeps its order behind incompleteness.
  It is disclosed rather than fixed because the question text is inside
  `questions.fingerprint` and changing it would invalidate all 5,580 shipped
  generations. README.md carries the correction, derived from the rows;
  `scripts/preflight.py` fails if any OTHER arm acquires the same flaw.

  Every arm assembles as of the question's own timestamp. Leaking a fact from
  after the as-of date inflates every arm at once, which is invisible because
  it moves nothing relative to anything.

The governance path is seeded to fail in one arm. National_id is stripped by
the policy that the resolved path applies. The UNPOLICED arm is that same
content with the policy step skipped, and it matches the baseline's SIZE so
that any accuracy difference cannot be dilution. That is the ordinary shape of
this defect: a control that holds on the primary path and is absent from an
alternate one, and the finding it enables is that skipping it costs nothing a
quality metric can see.
"""
from __future__ import annotations

import hashlib
import random
import re
from datetime import date, timedelta

from . import sources
from .questions import Question
from .world import FORBIDDEN_FIELDS, World

ARMS = ["none", "perfect", "resolved", "unresolved", "stale", "incomplete",
        "diluted", "unpoliced", "nostructure", "governed"]

ARM_LABEL = {
    "none": "no context (floor)",
    "perfect": "perfect context (ceiling)",
    "resolved": "resolved production context (baseline)",
    "unresolved": "resolution disabled, string-match joins only",
    "stale": "volatile fields 30 days stale",
    # Filled in below, once the numbers it quotes exist. A label that states a
    # fraction the code does not produce is a published claim, and this one
    # said "40 percent" against a rendering that drops 44.4.
    "incomplete": None,
    "diluted": "baseline plus every other organization's records",
    "unpoliced": "baseline content with the field policy not applied",
    "nostructure": "same facts rendered as prose",
    "governed": "baseline with the strictest field policy",
}

STALE_DAYS = 30

# The input is the count, and the fraction is derived from it.
#
# Every question offers exactly nine droppable keys. A fraction as the input
# would be rounded: `round(9 * f)` is 4 for every f in [0.39, 0.5], so a
# fraction constant would be decorative across that whole range, rendering
# byte-identical contexts with every fingerprint unchanged, and a round "40
# percent" label would describe an arm that drops 4 of 9 (44.4 percent).
#
# So the count is what the code takes and the fraction is what the code
# reports. No value can be changed without changing the rendering: a
# different count moves every incomplete context immediately.
DROPPED_FIELDS = 4
# Measured over all 150 questions, and pinned by a test:
# the merged view has ten keys, `organization` is never droppable, and none of
# the remaining nine is ever absent.
CANDIDATE_FIELDS = 9
# Derived, never typed. This is the figure README.md and the arm label state.
DROP_FRACTION = DROPPED_FIELDS / CANDIDATE_FIELDS
ARM_LABEL["incomplete"] = (f"{DROPPED_FIELDS} of {CANDIDATE_FIELDS} fields "
                           f"dropped ({100 * DROP_FRACTION:.1f} percent)")


def _norm(name: str) -> str:
    """Normalize an organization name for matching.

    Drops legal suffixes and punctuation, which is what lets the resolved path
    see that "Northwind Health Partners" and "Northwind Health Partners LLC"
    are one customer. The unresolved path deliberately does not call this.
    """
    n = name.lower()
    n = re.sub(r"\b(llc|inc|incorporated|ltd|limited|corp|corporation|co)\b",
               " ", n)
    return re.sub(r"[^a-z0-9]+", "", n)


def _domain_key(domain: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", domain.lower().split(".")[0])


def _strip_policy(row: dict, strict: bool = False) -> dict:
    """Field-level policy. Removes what may never enter a prompt.

    strict additionally buckets the fields that are permitted but precise, so
    the governed arm answers "what does governance cost in accuracy" rather
    than "what does redaction cost".
    """
    out = {k: v for k, v in row.items() if k not in FORBIDDEN_FIELDS}
    if strict:
        if "employee_count" in out:
            out["employee_count"] = _bucket(out["employee_count"])
        if "headcount" in out:
            out["headcount"] = _bucket(out["headcount"])
        for k in ("email", "work_email"):
            if k in out:
                out[k] = "[redacted]@" + str(out[k]).split("@")[-1]
    return out


def _bucket(n) -> str:
    """Coarsen a precise but permitted value.

    A bucket that cannot contain the answer measures the bucket, not the
    policy. Returning a range where the key holds an exact number guaranteed a
    wrong answer on every employee-count question, and that deterministic loss
    was most of this arm's reported effect. The value is rounded instead, so
    the arm costs precision without costing the answer outright, which is what
    a real privacy transform does.
    """
    try:
        n = int(n)
    except (TypeError, ValueError):
        return str(n)
    # Granularity the key can survive. Rounding to hundreds failed exact
    # match on seven of eight employee counts, which made this arm a fixed
    # subtraction again under a different name. Ten keeps the transform
    # lossy and observable without guaranteeing a wrong answer.
    return str(round(n, -1))


def _resolve(w: World, q: Question, as_of: date, strict: bool = False) -> dict:
    """The pipeline's own output: one merged view of the relevant customer.

    Survivorship is by EFFECTIVE DATE, which is the decision that makes the
    late correction come out right and the one-sided staleness come out right,
    the decision the unresolved arm does not get to make.
    """
    a = sources.crm_a(w, as_of)
    b = sources.crm_b(w, as_of)
    org = w.org(q.org_id)
    akey = q.org_id.replace("ORG", "ACC-")

    acct = next(r for r in a["accounts"] if r["account_id"] == akey)
    bmatch = [r for r in b["companies"]
              if _norm(r["company"]) == _norm(org["name"])
              or _domain_key(r["website"]) == _domain_key(org["domain"])]

    merged = {
        "organization": org["name"],
        "segment": acct["segment"],
        # Truth by effective date, which is what the world says, not what a
        # system happened to have refreshed.
        "account_owner": w.value_as_of("org", q.org_id, "owner", as_of),
        "lifecycle_stage": w.value_as_of("org", q.org_id, "stage", as_of),
        "hq_state": acct["hq_state"],
        "employee_count": acct["employee_count"],
        "source_records_merged": 1 + len(bmatch),
    }
    contacts = []
    for c in w.contacts:
        cur = w.value_as_of("contact", c["contact_id"], "org_id", as_of)
        if cur == q.org_id:
            contacts.append(_strip_policy(
                {"name": c["name"],
                 "email": w.value_as_of("contact", c["contact_id"],
                                        "email", as_of),
                 "title": c["title"],
                 "national_id": c["national_id"]}, strict))
    agreements = []
    for k in w.contracts_for(q.org_id, as_of):
        agreements.append({
            "agreement": k["contract_id"],
            "start_date": k["start_date"].isoformat(),
            "renewal_date": w.value_as_of(
                "contract", k["contract_id"], "renewal_date",
                as_of).isoformat(),
            "acv": w.value_as_of("contract", k["contract_id"], "acv", as_of),
            "term_months": k["term_months"],
        })
    merged = _strip_policy(merged, strict)
    # Stage history is a context primitive, not a nicety: a question about
    # what changed cannot be answered from a current-state snapshot, and an
    # arm that cannot answer it is measuring the assembly's field list rather
    # than the property the arm is named for.
    merged["stage_history"] = [
        f"{ch.effective.isoformat()}: {ch.value}"
        for ch in w.changes
        if ch.entity == "org" and ch.entity_id == q.org_id
        and ch.field == "stage" and ch.effective <= as_of]
    merged["contacts"] = contacts
    merged["agreements"] = agreements
    return merged


def _render(obj, indent: int = 0) -> str:
    """Structured facts as indented key/value text. No JSON braces noise."""
    pad = "  " * indent
    out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, (dict, list)):
                out.append(f"{pad}{k}:")
                out.append(_render(v, indent + 1))
            else:
                out.append(f"{pad}{k}: {v}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj, 1):
            if isinstance(v, (dict, list)):
                out.append(f"{pad}- [{i}]")
                out.append(_render(v, indent + 1))
            else:
                out.append(f"{pad}- {v}")
    else:
        out.append(f"{pad}{obj}")
    return "\n".join(x for x in out if x)


def _prose(obj) -> str:
    """The same facts as sentences, for the no-structure arm.

    This arm must vary rendering and nothing else. Two earlier defects here
    made it vary three things: a list of SCALARS fell through the walk and was
    silently dropped, taking the stage history with it, and the wrapper cut
    every 78 characters by index, splitting values mid-token so that a graded
    answer could be broken across a line. Either one turns a rendering arm
    into a content arm and makes its result unattributable.
    """
    bits = []

    def walk(o, prefix=""):
        if isinstance(o, dict):
            for k, v in o.items():
                if isinstance(v, (dict, list)):
                    walk(v, f"{prefix}{k} ")
                else:
                    bits.append(f"The {prefix}{k.replace('_', ' ')} is {v}.")
        elif isinstance(o, list):
            for v in o:
                if isinstance(v, (dict, list)):
                    walk(v, prefix)
                else:
                    bits.append(f"The {prefix}entry is {v}.")

    walk(obj)
    # Wrap on whitespace only. A value must never be split.
    out, line = [], ""
    for word in " ".join(bits).split(" "):
        if line and len(line) + 1 + len(word) > 78:
            out.append(line)
            line = word
        else:
            line = f"{line} {word}".strip()
    if line:
        out.append(line)
    return "\n".join(out)


# The budgets the curve is measured at, in tokens.
#
# The curve does not saturate, and that is a limit on what it can say. This
# world holds about 6,900 tokens of ranked facts per question, so the largest
# budget here keeps roughly 69% of the available material and truncates the
# rest. Every "paired against the largest budget" comparison is therefore
# paired against a 69% cut and not against all available context: the curve
# measures the shape of the climb, not where it flattens, because it does not
# reach the flat part. Raising the top of the range would cost a proportional
# amount of money per point and buy a different experiment, so the limit is
# disclosed rather than removed.
CURVE_BUDGETS = [150, 300, 600, 1200, 2400, 4800]
# Measured, and defined once. This value cuts the budget, so a wrong one
# mislabels every point on the curve. It lives here and the cost estimator
# imports it: two copies of one constant is the drift shape that already
# mislabeled this axis once.
CHARS_PER_TOKEN = 2.1


def ranked_facts(w: World, q: Question, as_of) -> list[str]:
    """Every available fact, most relevant first.

    The ranking is what the curve reports. Truncating an unordered blob
    measures how lucky the cut was. Ranking first and then cutting measures
    what a budget actually buys: the curve starts with the answer-bearing
    facts and then spends the remaining budget on progressively less relevant
    ones, which is the mechanism the prediction is about.
    """
    tiers: list[list[str]] = [[], [], []]
    tiers[0] = _render(_resolve(w, q, as_of)).split("\n")

    a = sources.crm_a(w, as_of)
    b = sources.crm_b(w, as_of)
    akey = q.org_id.replace("ORG", "ACC-")
    idx = int(q.org_id.replace("ORG", "")) - 1
    started = {k["contract_id"].replace("CTR", "AGR-")
               for k in w.contracts_for(q.org_id, as_of)}
    for row in (a["accounts"] + a["contacts"]
                + [r for r in a["agreements"]
                   if r["agreement_id"] in started
                   or r["account_id"] != q.org_id.replace("ORG", "ACC-")]):
        line = _render(_strip_policy(row))
        (tiers[1] if row.get("account_id") == akey else tiers[2]).append(line)
    # CRM_B's deals are filtered by start date as CRM_A's agreements are, so
    # no budget ships the asked organization's deal for a contract that had
    # not started on the date asked. The unresolved arm filters them the same
    # way.
    live = {9000 + i for i, k in enumerate(w.contracts)
            if k["contract_id"] in {c["contract_id"]
                                    for c in w.contracts_for(q.org_id, as_of)}}
    deals = [r for r in b["deals"]
             if r["company_id"] != 5000 + idx or r["deal_id"] in live]
    for row in b["companies"] + b["people"] + deals:
        line = _render(_strip_policy(row))
        same = (row.get("company_id") == 5000 + idx)
        (tiers[1] if same else tiers[2]).append(line)
    return [ln for tier in tiers for ln in tier if ln.strip()]


def curve_context(w: World, q: Question, budget_tokens: int) -> str:
    """Ranked facts, cut at a token budget."""
    limit = int(budget_tokens * CHARS_PER_TOKEN)
    out, used = [], 0
    for line in ranked_facts(w, q, q.as_of):
        if used + len(line) + 1 > limit:
            break
        out.append(line)
        used += len(line) + 1
    return "\n".join(out)


def context_for(w: World, q: Question, arm: str) -> str:
    """The exact context text for one question under one arm."""
    as_of = q.as_of

    if arm == "none":
        return ""

    if arm == "perfect":
        # Exactly the fields the answer needs, current and resolved, and
        # nothing else. The ceiling this engineering can reach.
        full = _resolve(w, q, as_of)
        keep = {"organization": full["organization"]}
        for key in q.answer:
            if key in ("owner",):
                keep["account_owner"] = full["account_owner"]
            elif key == "segment":
                keep["segment"] = full["segment"]
            elif key == "stage":
                keep["lifecycle_stage"] = full["lifecycle_stage"]
            elif key in ("hq_state", "employees", "employee_count"):
                keep["hq_state"] = full["hq_state"]
                keep["employee_count"] = full["employee_count"]
            elif key in ("acv", "total_acv", "renewal_date",
                         "days_until_renewal", "agreements"):
                keep["agreements"] = full["agreements"]
            elif key == "organizations":
                keep["source_records_merged"] = full["source_records_merged"]
                keep["note"] = ("all source records listed here are the same "
                                "organization")
            elif key == "organization":
                keep["organization"] = full["organization"]
                # A ceiling must contain what the Question asks about. When
                # the question names a person, stating only the organization
                # leaves the model unable to verify that the two are
                # connected, and it answered null. Minimal is not the same as
                # sufficient, and an arm that is minimal to the point of
                # ambiguity is not an upper bound on anything.
                keep["contacts"] = [
                    {"name": c["name"], "title": c["title"]}
                    for c in full.get("contacts", [])
                    if c["name"] in q.text]
            elif key == "days_until_renewal":
                keep["as_of_date"] = as_of.isoformat()
                keep["agreements"] = full["agreements"]
            elif key == "stage_changes":
                keep["stage_history"] = [
                    f"{ch.effective.isoformat()}: {ch.value}"
                    for ch in w.changes
                    if ch.entity == "org" and ch.entity_id == q.org_id
                    and ch.field == "stage" and ch.effective <= as_of]
        return _render(keep)

    if arm == "resolved":
        return _render(_resolve(w, q, as_of))

    if arm == "governed":
        return _render(_resolve(w, q, as_of, strict=True))

    if arm == "stale":
        # Volatile fields only, which is what a broken incremental sync
        # actually produces. Rewinding the whole context instead would also
        # age the fields that never change, names, segments, headcounts,
        # start dates, and measure a condition no pipeline produces. The
        # arm would then be easier to separate for the wrong reason.
        fresh = _resolve(w, q, as_of)
        old = _resolve(w, q, as_of - timedelta(days=STALE_DAYS))
        for key in ("account_owner", "lifecycle_stage", "stage_history"):
            if key in old:
                fresh[key] = old[key]
        by_id = {k["agreement"]: k for k in old.get("agreements", [])}
        for k in fresh.get("agreements", []):
            stale_k = by_id.get(k["agreement"])
            if stale_k:
                for field in ("acv", "renewal_date"):
                    k[field] = stale_k[field]
        return _render(fresh)

    if arm == "incomplete":
        merged = _resolve(w, q, as_of)
        rng = random.Random(f"{q.qid}:incomplete")
        keys = [k for k in merged if k not in ("organization",)]
        # A COUNT, not a fraction of a count. `round(len(keys) * 0.4)` gave 4
        # here and gave 4 for every fraction from 0.39 to 0.5, which made the
        # fraction unfalsifiable. min() is a bound and not a policy: it exists
        # so a world with fewer keys degrades instead of raising, and the test
        # asserts len(keys) == CANDIDATE_FIELDS on every question so it cannot
        # silently start binding.
        drop = set(rng.sample(keys, min(DROPPED_FIELDS, len(keys))))
        return _render({k: v for k, v in merged.items() if k not in drop})

    if arm == "unresolved":
        # String-match joins only, both source rows kept, contradictions
        # intact. This is the arm that cannot see that ORG001 is one company.
        a = sources.crm_a(w, as_of)
        b = sources.crm_b(w, as_of)
        org = w.org(q.org_id)
        akey = q.org_id.replace("ORG", "ACC-")
        arows = [r for r in a["accounts"] if r["account_id"] == akey]
        brows = [r for r in b["companies"] if r["company"] == org["name"]]
        acont = [r for r in a["contacts"]
                 if r["account_id"] == akey]
        cids = {r["company_id"] for r in brows}
        bpeople = [r for r in b["people"] if r["company_id"] in cids]
        started = {k["contract_id"].replace("CTR", "AGR-")
                   for k in w.contracts_for(q.org_id, as_of)}
        aagr = [r for r in a["agreements"]
                if r["account_id"] == akey and r["agreement_id"] in started]
        live = {9000 + i for i, k in enumerate(w.contracts)
                if k["contract_id"] in {c["contract_id"]
                                        for c in w.contracts_for(q.org_id,
                                                                 as_of)}}
        bdeals = [r for r in b["deals"]
                  if r["company_id"] in cids and r["deal_id"] in live]
        # Stage history is org-level and both systems carry it. Dropping it
        # here was an accident of how the raw rows are shaped, not a
        # consequence of disabling resolution, and it made every
        # stage-change question unanswerable in this arm alone.
        history = [f"{ch.effective.isoformat()}: {ch.value}"
                   for ch in w.changes
                   if ch.entity == "org" and ch.entity_id == q.org_id
                   and ch.field == "stage" and ch.effective <= as_of]
        return _render({
            "CRM_A": {"accounts": [_strip_policy(r) for r in arows],
                      "contacts": [_strip_policy(r) for r in acont],
                      "agreements": aagr},
            "CRM_B": {"companies": [_strip_policy(r) for r in brows],
                      "people": [_strip_policy(r) for r in bpeople],
                      "deals": bdeals},
            "stage_history": history,
        })

    if arm == "diluted":
        # The baseline plus irrelevant entities, and nothing else changed.
        # Same resolution, same survivorship, same rendering, same policy.
        # The only variable is how much correct-but-irrelevant material sits
        # around the answer, which is what "more context" actually means when
        # a retrieval step is not selective.
        mine = _resolve(w, q, as_of)
        others = []
        for o in w.orgs:
            if o["org_id"] == q.org_id:
                continue
            other = Question(q.qid, q.stratum, q.as_of, q.text, q.answer,
                             o["org_id"])
            others.append(_resolve(w, other, as_of))
        return _render({"organization_asked_about": mine,
                        "other_organizations": others})

    if arm == "unpoliced":
        # The baseline with the field policy not applied, and nothing else.
        # Same content, same ranking, same rendering. Its accuracy should
        # match the baseline almost exactly, and that is the finding: a
        # governance failure costs nothing a quality metric can see, so no
        # amount of output-quality monitoring will ever surface it.
        full = _resolve(w, q, as_of)
        full["contacts"] = [
            {"name": c["name"],
             "email": w.value_as_of("contact", c["contact_id"], "email",
                                    as_of),
             "title": c["title"], "national_id": c["national_id"]}
            for c in w.contacts
            if w.value_as_of("contact", c["contact_id"], "org_id",
                             as_of) == q.org_id]
        return _render(full)

    if arm == "nostructure":
        return _prose(_resolve(w, q, as_of))

    raise ValueError(f"unknown arm {arm!r}")


def arm_fingerprint(w, qs, arm: str) -> str:
    """A hash of everything this arm actually renders, across every question.

    The Question fingerprint is not enough. It covers ids, dates and answer
    keys, so a change to how an ARM assembles context leaves it untouched and
    the stale rows for that arm keep aggregating. Rows that no longer
    describe the condition they are labeled with, with nothing in the output
    to say so.

    Per arm. A change to one arm invalidates that arm and not the other nine,
    so a fix costs one arm's re-run instead of a whole sweep.
    """
    if not qs:
        # An empty question set is not a condition. `context_for` refuses an
        # arm it does not know, and this loop would never reach it: zero
        # questions render zero contexts, and the hash of the empty string is
        # a perfectly plausible-looking fingerprint for nothing at all. A
        # stamp that survives having examined no question is the shape this
        # whole mechanism exists to prevent.
        raise ValueError("no questions: an arm fingerprint over an empty "
                         "question set describes nothing")
    blob = "\n".join(context_for(w, q, arm) for q in qs)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def curve_fingerprint(w, qs, budget: int) -> str:
    """The same hash, for one point on the budget curve.

    A curve point is a condition too: 360 of the 1,860 rows in a run, 19.4%,
    are curve rows. Without a hash of what each budget renders, a change to
    the ranking, to the truncation rule or to CHARS_PER_TOKEN would leave
    every one of those rows aggregating under a label that no longer
    describes them, which is exactly what the arm fingerprint exists to
    prevent.
    """
    if not qs:
        raise ValueError("no questions: a curve fingerprint over an empty "
                         "question set describes nothing")
    blob = "\n".join(curve_context(w, q, budget) for q in qs)
    return hashlib.sha256(f"curve:{budget}\n{blob}".encode("utf-8")).hexdigest()[:16]
