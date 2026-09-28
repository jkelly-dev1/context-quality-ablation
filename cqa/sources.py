"""The two source systems, and how they disagree.

CRM_A and CRM_B hold the same book of business with different key spaces,
different field names, different completeness and different refresh cadences.
Neither is authoritative and there is no shared identifier, which is what makes
resolution a real step rather than a join.

What each system knows is a function of the world's change log and the
system's own refresh date. A system that last refreshed on day 100 does not
know about a change effective on day 150, and a system that refreshes on
arrival rather than on effect gets the late correction wrong for five months.
That is the mechanism, and staleness here is a property of the data rather
than a flag somebody sets.
"""
from __future__ import annotations

from datetime import date, timedelta

from .world import EPOCH, World

# CRM_B lags. Every volatile field it holds is as of its own refresh, which
# trails the as-of date by this much.
B_LAG_DAYS = 45

SUFFIXES = ["LLC", "Inc.", "Group Ltd", "Holdings LLC"]


def split_alias(org: dict) -> dict:
    """How the lagging system spells a split-identity customer.

    A different legal name and a different domain for the same company, with
    no shared key. The alias is derived from the real name rather than stored,
    so adding an organization cannot leave the alias table behind.
    """
    idx = int(org["org_id"].replace("ORG", ""))
    head = org["name"].split()[0]
    tail = " ".join(org["name"].split()[1:])
    return {
        "name": f"{head} {tail} {SUFFIXES[idx % len(SUFFIXES)]}".strip(),
        "domain": org["domain"].replace(".", "-corp.", 1),
    }


def _as_of(w: World, entity: str, entity_id: str, fname: str,
           base: object, when: date, use_recorded: bool) -> object:
    """The value a system shows on `when`.

    use_recorded is the difference between the two systems. CRM_A applies a
    change when it LEARNS of it, which is what a system fed by an event stream
    does. CRM_B applies it by effective date but only up to its own lagging
    refresh. Neither is wrong; they are wrong in different ways,
    which is what makes survivorship a decision.
    """
    value = base
    for ch in w.changes:
        if ch.entity != entity or ch.entity_id != entity_id:
            continue
        if ch.field != fname:
            continue
        stamp = ch.recorded if use_recorded else ch.effective
        if stamp <= when:
            value = ch.value
    return value


def crm_a(w: World, as_of: date) -> dict:
    """System A. Fresh, keyed on ACC-/CTC-/AGR-, applies changes on arrival."""
    orgs, contacts, contracts = [], [], []
    for o in w.orgs:
        orgs.append({
            "account_id": o["org_id"].replace("ORG", "ACC-"),
            "account_name": o["name"],
            "web_domain": o["domain"],
            "segment": o["segment"],
            "account_owner": _as_of(w, "org", o["org_id"], "owner",
                                    o["owner"], as_of, True),
            "lifecycle_stage": _as_of(w, "org", o["org_id"], "stage",
                                      o["stage"], as_of, True),
            "employee_count": o["employees"],
            "hq_state": o["hq_state"],
        })
    for c in w.contacts:
        org_id = _as_of(w, "contact", c["contact_id"], "org_id",
                        c["org_id"], as_of, True)
        contacts.append({
            "contact_id": c["contact_id"].replace("CON", "CTC-"),
            "account_id": org_id.replace("ORG", "ACC-"),
            "full_name": c["name"],
            "email": _as_of(w, "contact", c["contact_id"], "email",
                            c["email"], as_of, True),
            "job_title": c["title"],
            "national_id": c["national_id"],
        })
    for k in w.contracts:
        contracts.append({
            "agreement_id": k["contract_id"].replace("CTR", "AGR-"),
            "account_id": k["org_id"].replace("ORG", "ACC-"),
            "start": _iso(k["start_date"]),
            "renews_on": _iso(_as_of(w, "contract", k["contract_id"],
                                     "renewal_date", k["renewal_date"],
                                     as_of, True)),
            "annual_value_usd": _as_of(w, "contract", k["contract_id"], "acv",
                                       k["acv"], as_of, True),
            "term_months": k["term_months"],
            "auto_renew": k["auto_renew"],
        })
    return {"system": "CRM_A", "as_of": _iso(as_of), "accounts": orgs,
            "contacts": contacts, "agreements": contracts}


def crm_b(w: World, as_of: date) -> dict:
    """System B. Lagging, keyed on numbers, different field names, gappy.

    B is also where the split identity lives: it carries ORG001 under a second
    name and domain, so a string-match join sees two customers.
    """
    when = as_of - timedelta(days=B_LAG_DAYS)
    if when < EPOCH:
        when = EPOCH
    companies, people, deals = [], [], []
    for i, o in enumerate(w.orgs):
        name, domain = o["name"], o["domain"]
        if w.defects.get(o["org_id"]) == "split_identity":
            alias = split_alias(o)
            name, domain = alias["name"], alias["domain"]
        row = {
            "company_id": 5000 + i,
            "company": name,
            "website": domain,
            "tier": o["segment"],
            "rep": _as_of(w, "org", o["org_id"], "owner", o["owner"],
                          when, False),
            "status": _as_of(w, "org", o["org_id"], "stage", o["stage"],
                             when, False),
        }
        # B does not carry headcount or state for every company. Missing
        # fields are missing, not empty strings, so an assembler cannot
        # accidentally present absence as a value.
        if i % 3 != 1:
            row["headcount"] = o["employees"]
        companies.append(row)
    for j, c in enumerate(w.contacts):
        org_id = _as_of(w, "contact", c["contact_id"], "org_id",
                        c["org_id"], when, False)
        idx = int(org_id.replace("ORG", "")) - 1
        people.append({
            "person_id": 7000 + j,
            "company_id": 5000 + idx,
            "person_name": c["name"],
            "work_email": _as_of(w, "contact", c["contact_id"], "email",
                                 c["email"], when, False),
            "role": c["title"],
            "national_id": c["national_id"],
        })
    for m, k in enumerate(w.contracts):
        idx = int(k["org_id"].replace("ORG", "")) - 1
        deals.append({
            "deal_id": 9000 + m,
            "company_id": 5000 + idx,
            "started": _iso(k["start_date"]),
            "renewal": _iso(_as_of(w, "contract", k["contract_id"],
                                   "renewal_date", k["renewal_date"],
                                   when, False)),
            "value": _as_of(w, "contract", k["contract_id"], "acv",
                            k["acv"], when, False),
        })
    return {"system": "CRM_B", "as_of": _iso(when), "companies": companies,
            "people": people, "deals": deals}


def _iso(d) -> str:
    return d.isoformat() if hasattr(d, "isoformat") else str(d)
