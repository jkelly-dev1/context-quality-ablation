"""The question set, and the answer key computed from world state.

Every answer is derived, never written down twice. A template declares which
world facts it wants and the key is computed from World.value_as_of at build
time, so the key cannot drift from the data. Editing the generator changes the
key automatically, which is the property that makes the whole repository
reproducible from the code alone.

Stratification is the defense against an answer key easier than the World. If
every question were a single-field lookup, perfect context and production
context would tie and the experiment would have measured its own generator.
The four strata:

    lookup        one field, one entity. The floor of difficulty.
    resolution    unanswerable without merging two source records
    survivorship  two systems disagree and the effective date decides
    computation   arithmetic over several rows

Results are reported PER STRATUM as well as in aggregate. An arm that only
moves the aggregate is a less interesting finding than one that moves a
stratum, and reporting only the aggregate would hide which.

Questions are generated from templates, not hand-written, because a set large
enough to resolve small differences is a set nobody proof-reads. The templates
are the thing to read; the count is a consequence of them.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import hashlib
import json
import re

from . import sources
from .world import EPOCH, World

# How many questions to build. A 20-question set cannot resolve a difference
# smaller than about three fields, which leaves most of the arms inside the
# noise floor; this is the size at which the design expects them to separate.
TARGET = 150


@dataclass(frozen=True)
class Question:
    qid: str
    stratum: str
    as_of: date
    text: str
    answer: dict
    # The organization the question is about, so context assembly knows what
    # is relevant without parsing the prose.
    org_id: str


def _d(days: int) -> date:
    return EPOCH + timedelta(days=days)


def _iso(d) -> str:
    return d.isoformat() if hasattr(d, "isoformat") else str(d)


# The world's INTERNAL identifier for an agreement, as it appears in question
# text. It is internal in the strict sense: `sources.crm_a` renames it to
# AGR-nnn and `sources.crm_b` gives deals a numeric id of their own, so the
# literal CTRnnn exists only in the world and in what the RESOLVED pipeline
# renders from it. See `names_internal_id` below, and README.md's section on
# what that costs the unresolved arm.
INTERNAL_ID = re.compile(r"\b(CTR\d+)\b")


def names_internal_id(q: "Question") -> str | None:
    """The internal identifier this question's text names, if it names one.

    A question that names one is asking about an entity by a name only the
    resolved view uses. Any arm that does not render that view cannot match
    the question to the entity, and the model correctly answers null, which
    is a failure of identification and not of the property the arm is named
    for. `scripts/preflight.py` checks that no arm loses an identifier except
    the ones documented as legitimately losing it.
    """
    m = INTERNAL_ID.search(q.text)
    return m.group(1) if m else None


# Below this length a value is not evidence. "CA" appears in any prose, and a
# floor check that searched for it would report every prompt as leaking its own
# answer; five characters is where the world's values stop being ambiguous.
MIN_DISTINCTIVE = 5


def distinctive_answer_values(q: "Question") -> list:
    """The answer values long enough that finding one in a prompt MEANS
    something.

    One definition, two callers. `scripts/preflight.py` uses it to decide
    whether the floor arm's prompt states its own answer, and
    tests/test_harness.py asserts the same property. A second copy of the
    length rule in either caller could not fail when this one changed.
    """
    return [str(v) for v in q.answer.values()
            if isinstance(v, str) and len(str(v)) >= MIN_DISTINCTIVE]


def _name_agreement(w: World, org_id: str, k: dict, as_of: date) -> str:
    """Name the organization, and the agreement too when there is more than one.

    An organization with two contracts makes "the renewal date" AMBIGUOUS, and
    a model that answers null to an ambiguous question is behaving correctly.
    An ambiguous question therefore measures nothing, so the text disambiguates
    wherever the world does not.

    It disambiguates by START DATE, which both source systems carry (CRM_A's
    `start`, CRM_B's `started`) and every arm that renders agreements shows.
    The world's internal id, CTRnnn, is never used: neither source carries it,
    so the unresolved arm, which renders raw source rows, could not identify
    the agreement and would score a failure of identification as a failure of
    resolution. No organization holds two contracts that start on the same
    day; tests/test_harness.py holds it.
    """
    name = w.org(org_id)["name"]
    if len(w.contracts_for(org_id, as_of)) > 1:
        return f"the agreement that started on {_iso(k['start_date'])} at {name}"
    return name


#: How a question names one of an organization's agreements.
AGREEMENT_START = re.compile(r"the agreement that started on (\d{4}-\d{2}-\d{2})")


def names_agreement_start(q: "Question") -> str | None:
    """The start date by which this question names an agreement, if it does."""
    m = AGREEMENT_START.search(q.text)
    return m.group(1) if m else None


def shown_contract_value(w: World, cid: str, fname: str, as_of: date):
    """The answer key for a contract field: the truth, if a source showed it.

    The key is World.value_as_of, the value by EFFECTIVE date, whenever either
    source system showed that value on `as_of`. When neither did, the key is
    the value they both showed. A correction that took effect before the date
    asked and was recorded after it is invisible on that date, so a key taken
    from the effective value would be world truth no pipeline could reach.
    Over all 150 questions C009 is the one key this rule decides (309 days,
    the renewal both systems still showed). Where the two systems disagree and
    neither shows the truth, it raises rather than pick one.
    """
    from cqa import sources
    truth = w.value_as_of("contract", cid, fname, as_of)
    base = next(k for k in w.contracts if k["contract_id"] == cid)[fname]
    a = sources._as_of(w, "contract", cid, fname, base, as_of, True)
    b = sources._as_of(w, "contract", cid, fname, base,
                       as_of - timedelta(days=sources.B_LAG_DAYS), False)
    if truth in (a, b):
        return truth
    if a == b:
        return a
    raise ValueError(f"{cid}.{fname} on {as_of}: truth {truth!r} shown by "
                     f"neither system, and they disagree ({a!r}, {b!r})")


def build(w: World) -> list[Question]:
    q: list[Question] = []
    seen: set[tuple] = set()

    def add(stratum, as_of, text, answer, org_id):
        # A duplicate question is a wasted generation and silently reweights
        # the strata, so identity is the text together with the date.
        key = (text, as_of)
        if key in seen:
            return
        seen.add(key)
        q.append(Question("", stratum, as_of, text, answer, org_id))

    def owner(org_id, as_of):
        return w.value_as_of("org", org_id, "owner", as_of)

    def stage(org_id, as_of):
        return w.value_as_of("org", org_id, "stage", as_of)

    def acv(cid, as_of):
        return shown_contract_value(w, cid, "acv", as_of)

    def renewal(cid, as_of):
        return shown_contract_value(w, cid, "renewal_date", as_of)

    def n_stage_changes(org_id, as_of):
        return sum(1 for ch in w.changes
                   if ch.entity == "org" and ch.entity_id == org_id
                   and ch.field == "stage" and ch.effective <= as_of)

    # ---------------------------------------------------------------- LOOKUP
    for i, o in enumerate(w.orgs):
        oid = o["org_id"]
        for day in (170 + 13 * i, 300 - 9 * i):
            add("lookup", _d(day),
                f"Who owns the account {o['name']}, and what segment is it "
                f"in?",
                {"owner": owner(oid, _d(day)), "segment": o["segment"]}, oid)
        add("lookup", _d(210 + 5 * i),
            f"What is the headquarters state and employee count for "
            f"{o['name']}?",
            {"hq_state": o["hq_state"], "employees": o["employees"]}, oid)
        day = 240 + 7 * i
        add("lookup", _d(day),
            f"What is the current lifecycle stage of {o['name']}?",
            {"stage": stage(oid, _d(day))}, oid)
        day = 250 + 3 * i
        for k in w.contracts_for(oid, _d(day)):
            add("lookup", _d(day),
                f"What is the renewal date and annual contract value for "
                f"{_name_agreement(w, oid, k, _d(day))}?",
                {"renewal_date": _iso(renewal(k["contract_id"], _d(day))),
                 "acv": acv(k["contract_id"], _d(day))}, oid)

    # ------------------------------------------------------------ RESOLUTION
    # Split identity: the same company under two names in two systems.
    for o in w.orgs:
        if w.defects.get(o["org_id"]) != "split_identity":
            continue
        oid = o["org_id"]
        for day in (185, 265, 330):
            add("resolution", _d(day),
                f"How many source records across all systems describe "
                f"{o['name']}, and how many separate real companies is that?",
                {"source_records": 2, "organizations": 1}, oid)
        for day in (200, 310):
            ks = w.contracts_for(oid, _d(day))
            if not ks:
                continue
            add("resolution", _d(day),
                f"Counting {o['name']} once even if it appears more than "
                f"once, what is its combined annual contract value across "
                f"every agreement?",
                {"total_acv": sum(acv(k["contract_id"], _d(day))
                                  for k in ks)}, oid)

    # Moved contacts: which employer they have depends on the date asked.
    movers = sorted({ch.entity_id for ch in w.changes
                     if ch.entity == "contact" and ch.field == "org_id"})
    for cid in movers:
        c = next(x for x in w.contacts if x["contact_id"] == cid)
        move = next(ch for ch in w.changes
                    if ch.entity_id == cid and ch.field == "org_id")
        base = (move.effective - EPOCH).days
        for day in (base - 30, base + 60, base + 150):
            if day < 10:
                continue
            oid = w.value_as_of("contact", cid, "org_id", _d(day))
            add("resolution", _d(day),
                f"Which organization does {c['name']} belong to, and what is "
                f"that organization's account owner?",
                {"organization": w.org(oid)["name"],
                 "owner": owner(oid, _d(day))}, oid)

    # ---------------------------------------------------------- SURVIVORSHIP
    # Owner changes, asked inside and outside the lagging system's window.
    for ch in [c for c in w.changes
               if c.entity == "org" and c.field == "owner"]:
        base = (ch.effective - EPOCH).days
        for day in (base + 10, base + 40, base + 120):
            add("survivorship", _d(day),
                f"Who is the current account owner for "
                f"{w.org(ch.entity_id)['name']}?",
                {"owner": owner(ch.entity_id, _d(day))}, ch.entity_id)

    # Amendments, asked after the value moved.
    for ch in [c for c in w.changes
               if c.entity == "contract" and c.field == "acv"]:
        k = next(x for x in w.contracts if x["contract_id"] == ch.entity_id)
        base = (ch.effective - EPOCH).days
        for day in (base + 15, base + 70):
            add("survivorship", _d(day),
                f"What is the annual contract value for "
                f"{_name_agreement(w, k['org_id'], k, _d(day))}?",
                {"acv": acv(k["contract_id"], _d(day))}, k["org_id"])

    # Late corrections, asked INSIDE the gap between effective and recorded,
    # which is the only window where the two orderings disagree.
    for ch in [c for c in w.changes
               if c.entity == "contract" and c.field == "renewal_date"]:
        k = next(x for x in w.contracts if x["contract_id"] == ch.entity_id)
        lo = (ch.effective - EPOCH).days
        hi = (ch.recorded - EPOCH).days
        # Ask only where some source can actually know the answer. Inside the
        # gap the arrival-ordered system has not received the correction, and
        # the lagging system only carries it once ITS refresh has passed the
        # effective date, which is B_LAG_DAYS behind the ask. Before that
        # point neither CRM holds the value, so a baseline that states it is
        # reading world truth no pipeline could reach, and the arm gap would
        # be measuring oracle access rather than survivorship.
        earliest = lo + sources.B_LAG_DAYS + 5
        for day in (earliest, (earliest + hi) // 2, hi - 10):
            if day < earliest or day >= hi:
                continue
            add("survivorship", _d(day),
                f"What is the renewal date for "
                f"{_name_agreement(w, k['org_id'], k, _d(day))}?",
                {"renewal_date": _iso(renewal(k["contract_id"], _d(day)))},
                k["org_id"])

    # ----------------------------------------------------------- COMPUTATION
    for i, o in enumerate(w.orgs):
        oid = o["org_id"]
        for day in (280 + 4 * i, 330 - 6 * i):
            ks = w.contracts_for(oid, _d(day))
            if not ks:
                continue
            add("computation", _d(day),
                f"What is the total annual contract value across all "
                f"agreements for {o['name']}, and how many agreements is "
                f"that?",
                {"total_acv": sum(acv(k["contract_id"], _d(day))
                                  for k in ks),
                 "agreements": len(ks)}, oid)
        day = 200 + 6 * i
        for k in w.contracts_for(oid, _d(day)):
            add("computation", _d(day),
                f"How many days remain until the renewal date for "
                f"{_name_agreement(w, oid, k, _d(day))}?",
                {"days_until_renewal":
                    (renewal(k["contract_id"], _d(day)) - _d(day)).days}, oid)
        day = 290 + 3 * i
        add("computation", _d(day),
            f"What is the lifecycle stage of {o['name']}, and how many stage "
            f"changes has it had?",
            {"stage": stage(oid, _d(day)),
             "stage_changes": n_stage_changes(oid, _d(day))}, oid)

    return _balance(q)


def _balance(items: list[Question]) -> list[Question]:
    """Trim to TARGET while keeping every stratum represented.

    Trimming from the end would silently reweight the set toward whichever
    template happened to generate most, so the trim is taken round-robin
    across strata. Ids are assigned after the trim, so a question's id always
    matches its position in the final set.
    """
    by: dict[str, list[Question]] = {}
    for x in items:
        by.setdefault(x.stratum, []).append(x)
    order = sorted(by)
    picked: list[Question] = []
    i = 0
    while len(picked) < TARGET and any(by[s] for s in order):
        s = order[i % len(order)]
        if by[s]:
            picked.append(by[s].pop(0))
        i += 1

    picked.sort(key=lambda x: (x.stratum, x.as_of, x.text))
    out, n = [], {}
    for x in picked:
        n[x.stratum] = n.get(x.stratum, 0) + 1
        out.append(Question(f"{x.stratum[:1].upper()}{n[x.stratum]:03d}",
                            x.stratum, x.as_of, x.text, x.answer, x.org_id))
    return out

# Questions used for the token-budget curve. A subset, because the curve is
# about the shape rather than about resolving small per-question differences.
CURVE_QUESTIONS = 60


def curve_subset(qs, n=CURVE_QUESTIONS):
    """An EQUAL-SIZED sample from each stratum, n in total.

    Equal rather than proportional: the curve is read per stratum as well as in
    aggregate, and equal draws give every stratum the same power to show its
    own shape.

    A stride over a stratum-sorted list is not a sample. Qs is sorted by
    stratum, so qs[::2][:n] walks the early strata and runs out before
    reaching the last one: it drew 3 survivorship questions out of 60 where an
    equal draw gives 15. Defined here, in the package, so the runner and the
    cost estimator cannot disagree about which questions the curve covers.
    """
    by = {}
    for q in qs:
        by.setdefault(q.stratum, []).append(q)
    order = sorted(by)
    out, i = [], 0
    while len(out) < n and any(by[s] for s in order):
        s = order[i % len(order)]
        if by[s]:
            out.append(by[s].pop(0))
        i += 1
    return sorted(out, key=lambda q: (q.stratum, q.qid))


def fingerprint(qs) -> str:
    """A hash of the question set: every id, date and answer key.

    Results and the code that produced them drift apart silently. Any change
    to the generator moves dates and answer keys, and a results file written
    before that change still aggregates cleanly afterwards: reporting numbers
    computed against questions the code no longer asks. Nothing about that
    failure is visible in the output.

    Every row records this, and the report refuses to mix rows that disagree.
    """
    payload = [
        [q.qid, q.stratum, q.as_of.isoformat(),
         {k: (v.isoformat() if hasattr(v, "isoformat") else v)
          for k, v in sorted(q.answer.items())}]
        for q in qs
    ]
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]
