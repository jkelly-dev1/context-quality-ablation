"""The world, and the truth about it.

Everything downstream depends on one property of this module: the generator
knows the correct answer because it wrote it. There is no human grader and no
judge model anywhere in the measurement path, so the answer key cannot drift
from the data and cannot be argued with.

The world is a small book of business held in two source systems that disagree.
Neither is authoritative. Every disagreement is seeded deliberately and each
one has a known correct resolution:

    SPLIT IDENTITY     the same organization under two names and two domains,
                       with no shared key
    MOVED CONTACT      a person who exists in both systems, attached to
                       different organizations, because they changed jobs
    ONE-SIDED AMENDMENT  a contract amended in one system and not the other
    LATE CORRECTION    a correction whose effective date precedes the row it
                       corrects, so ordering by arrival gets it wrong
    ONE-SIDED STALENESS  a volatile field refreshed in one system only

Determinism is not decoration here. Every published figure has to be
reproducible from the seed alone, so this module uses random.Random(seed) and
never the module-level random, never dict ordering as a source of order, and
never the wall clock. The only time in this world is CLOCK, below.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

# The world's epoch. Every as-of timestamp in the question set is an offset
# from this, so nothing in this repository reads the wall clock.
EPOCH = date(2026, 1, 1)

# Field-level policy. national_id must never reach a prompt, in any arm, by
# any path. It is populated for every contact precisely so that a leak is
# always possible and therefore always measurable.
FORBIDDEN_FIELDS = frozenset({"national_id"})

ORG_NAMES = [
    ("Northwind Health Partners", "northwindhealth.com"),
    ("Cascade Medical Group", "cascademed.com"),
    ("Ridgeline Physicians Network", "ridgelinephys.com"),
    ("Bayview Care Alliance", "bayviewcare.com"),
    ("Summit Valley Clinics", "summitvalley.com"),
    ("Harborlight Medical", "harborlight.com"),
    ("Stonebridge Health Systems", "stonebridgehealth.com"),
    ("Fairmount Provider Group", "fairmountpg.com"),
    ("Lakeshore Family Practice", "lakeshorefp.com"),
    ("Pinecrest Health Network", "pinecresthn.com"),
    ("Willowbrook Medical Partners", "willowbrookmp.com"),
    ("Granite Peak Physicians", "granitepeakphys.com"),
]

OWNERS = ["Dana Whitfield", "Marcus Ellery", "Priya Raghunathan",
          "Tomas Lindqvist", "Adaeze Okonkwo", "Ruth Bergman"]

SEGMENTS = ["Enterprise", "Mid-Market", "Commercial"]
STAGES = ["Prospect", "Active", "Renewal Due", "Churned"]

FIRST = ["Alice", "Bernard", "Chidi", "Daniela", "Emeka", "Farah", "Gustav",
         "Hana", "Ivan", "Jolene", "Kwame", "Lucia", "Mateo", "Nadia",
         "Oskar", "Petra", "Quentin", "Rosa", "Sanjay", "Talia"]
LAST = ["Abernathy", "Baptiste", "Castellanos", "Dubois", "Eriksen",
        "Fontaine", "Guzman", "Halvorsen", "Ibarra", "Jankowski", "Kaufman",
        "Larsson", "Moreau", "Nakamura", "Ortega", "Pereira", "Quiroga",
        "Rosenthal", "Sandoval", "Thibodeaux"]


@dataclass(frozen=True)
class Change:
    """One field change, with the date it BECAME TRUE.

    effective is what the world did; recorded is when a source system found
    out. They differ for the late-correction case, which is the only way to
    make "order by arrival" produce a wrong answer.
    """
    effective: date
    recorded: date
    entity: str
    entity_id: str
    field: str
    value: object


@dataclass
class World:
    orgs: list[dict] = field(default_factory=list)
    contacts: list[dict] = field(default_factory=list)
    contracts: list[dict] = field(default_factory=list)
    changes: list[Change] = field(default_factory=list)
    # Which seeded defect each organization carries, so the question builder
    # can stratify on it rather than guessing from the data.
    defects: dict[str, str] = field(default_factory=dict)

    def org(self, org_id: str) -> dict:
        return next(o for o in self.orgs if o["org_id"] == org_id)

    def contracts_for(self, org_id: str, as_of: date | None = None
                      ) -> list[dict]:
        """The agreements this organization holds, AS OF a date.

        An agreement that has not started is not part of an as-of-t context.
        Without the filter, a context assembled for March carried a contract
        beginning in October, and a question about "the annual contract value"
        had an answer key drawn from a contract that did not yet exist. A
        model that refuses such a question is right and the key was wrong.

        as_of=None returns every agreement regardless of date, which is what
        the generator itself needs while building the world.
        """
        out = [c for c in self.contracts if c["org_id"] == org_id]
        if as_of is not None:
            out = [c for c in out if c["start_date"] <= as_of]
        return out

    def value_as_of(self, entity: str, entity_id: str, fname: str,
                    as_of: date) -> object:
        """The TRUE value on as_of, by effective date, ties broken by order.

        This is the answer key. It reads effective, never recorded, which is
        exactly the distinction the late-correction defect turns on.
        """
        base = {"org": self.orgs, "contact": self.contacts,
                "contract": self.contracts}[entity]
        key = {"org": "org_id", "contact": "contact_id",
               "contract": "contract_id"}[entity]
        row = next(r for r in base if r[key] == entity_id)
        value = row[fname]
        for ch in self.changes:
            if (ch.entity == entity and ch.entity_id == entity_id
                    and ch.field == fname and ch.effective <= as_of):
                value = ch.value
        return value


def build() -> World:
    """The whole world, deterministically.

    There is no seed, and that is the honest shape. This builds exactly one
    world, by modular arithmetic over fixed lists, and reproducibility means
    "this code produces this world" rather than "a seed selects among many".
    A seed argument would be a false affordance: a reader who varied it and
    saw the same numbers would conclude the results were robust across worlds
    having only ever seen one.

    Varying the World is a robustness check this repository has not run. It is
    worth running and it is not what a seed argument alone would give.
    """
    w = World()

    for i, (name, domain) in enumerate(ORG_NAMES):
        org_id = f"ORG{i + 1:03d}"
        w.orgs.append({
            "org_id": org_id,
            "name": name,
            "domain": domain,
            "segment": SEGMENTS[i % len(SEGMENTS)],
            "owner": OWNERS[i % len(OWNERS)],
            "stage": STAGES[(i + 1) % len(STAGES)],
            "employees": 200 + 137 * i,
            "hq_state": ["TX", "WA", "OR", "CA", "CO", "IL"][i % 6],
        })

    # Contacts. Two per organization, plus the one who moves.
    n = 0
    for org in w.orgs:
        for _ in range(2):
            first, last = FIRST[n % len(FIRST)], LAST[(n * 7) % len(LAST)]
            w.contacts.append({
                "contact_id": f"CON{n + 1:03d}",
                "org_id": org["org_id"],
                "name": f"{first} {last}",
                "email": f"{first.lower()}.{last.lower()}@{org['domain']}",
                "title": ["VP Operations", "Director of IT", "CFO",
                          "Chief Medical Officer"][n % 4],
                # Present on every contact so a leak is always possible.
                "national_id": f"{100 + n:03d}-{10 + n % 89:02d}-"
                               f"{1000 + n * 7 % 9000:04d}",
            })
            n += 1

    # Contracts. One or two per organization, amounts and dates deterministic.
    c = 0
    for i, org in enumerate(w.orgs):
        for k in range(1 if i % 3 else 2):
            start = EPOCH + timedelta(days=30 * ((i + k) % 11))
            w.contracts.append({
                "contract_id": f"CTR{c + 1:03d}",
                "org_id": org["org_id"],
                "start_date": start,
                "renewal_date": start + timedelta(days=365),
                "acv": 24000 + 6000 * ((i * 3 + k * 5) % 14),
                "term_months": 12,
                "auto_renew": bool((i + k) % 2),
            })
            c += 1

    _seed_defects(w)
    return w


def _seed_defects(w: World) -> None:
    """The five disagreements, seeded across the whole book of business.

    Every organization carries at least one, deterministically by index. A
    world where only five of twelve customers are interesting cannot support a
    question set that is stratified by defect, because the resolution and
    survivorship strata would be the same few questions asked at different
    dates, which measures the date arithmetic rather than the property.

    The assignment is by modular arithmetic rather than by sampling so that
    the reader of a failing question can work out which defect it exercises
    without running anything.
    """
    n_orgs = len(w.orgs)

    # 1. SPLIT IDENTITY, every fourth organization. It exists in the second
    #    system under a different legal name and domain, with no shared key.
    for i in range(0, n_orgs, 4):
        w.defects[w.orgs[i]["org_id"]] = "split_identity"

    # 2. Moved contacts. Every fifth contact changes employer mid-year. The
    #    lagging system still shows the old organization for a while.
    for j in range(4, len(w.contacts), 5):
        c = w.contacts[j]
        src = c["org_id"]
        dst = w.orgs[(int(src.replace("ORG", "")) % n_orgs)]["org_id"]
        if dst == src:
            continue
        when = EPOCH + timedelta(days=120 + 7 * (j % 9))
        w.changes.append(Change(
            effective=when, recorded=when,
            entity="contact", entity_id=c["contact_id"],
            field="org_id", value=dst))
        # And their email moves with them. Leaving the old domain behind made
        # the assembled context self-contradicting on exactly the resolution
        # questions this world exists to pose: the org line said one employer
        # and the address said another, so a model could read the answer off
        # whichever it trusted. Arms that showed raw rows then scored HIGHER
        # on resolution than the curated baseline, which inverted the finding.
        first, last = c["name"].split()[0], c["name"].split()[-1]
        domain = next(o["domain"] for o in w.orgs if o["org_id"] == dst)
        w.changes.append(Change(
            effective=when, recorded=when,
            entity="contact", entity_id=c["contact_id"], field="email",
            value=f"{first.lower()}.{last.lower()}@{domain}"))
        w.defects.setdefault(src, "moved_contact")

    # 3. One-sided amendments. Every third contract gains value partway
    #    through, and only the fresher system knows.
    # A Change to a contract cannot precede the contract. Anchoring these to
    # the epoch produced amendments effective months before the agreement
    # began, so a question asked at the change date referred to something that
    # did not exist yet and its answer key was drawn from it anyway.
    for m in range(2, len(w.contracts), 3):
        k = w.contracts[m]
        when = k["start_date"] + timedelta(days=60 + 5 * (m % 7))
        w.changes.append(Change(
            effective=when, recorded=when,
            entity="contract", entity_id=k["contract_id"],
            field="acv", value=k["acv"] + 6000 * (1 + m % 3)))
        w.defects.setdefault(k["org_id"], "one_sided_amendment")

    # 4. Late corrections. Every fifth contract has its renewal date corrected
    #    months after the date the correction is effective from. A pipeline
    #    that orders by arrival is wrong for the whole gap, and a question
    #    asked inside that gap separates the two orderings.
    for m in range(3, len(w.contracts), 5):
        k = w.contracts[m]
        eff = k["start_date"] + timedelta(days=20 + 5 * (m % 6))
        w.changes.append(Change(
            effective=eff,
            recorded=eff + timedelta(days=150),
            entity="contract", entity_id=k["contract_id"],
            field="renewal_date",
            value=k["renewal_date"] + timedelta(days=30 + 15 * (m % 4))))
        w.defects.setdefault(k["org_id"], "late_correction")

    # 5. One-sided staleness. Owner changes that the lagging system misses.
    for i in range(1, n_orgs, 2):
        o = w.orgs[i]
        w.changes.append(Change(
            effective=EPOCH + timedelta(days=95 + 11 * (i % 8)),
            recorded=EPOCH + timedelta(days=96 + 11 * (i % 8)),
            entity="org", entity_id=o["org_id"], field="owner",
            value=OWNERS[(i + 3) % len(OWNERS)]))
        w.defects.setdefault(o["org_id"], "one_sided_staleness")

    # 6. STAGE MOVEMENT, so the change-history questions have something to
    #    count and the count differs per organization.
    for i, o in enumerate(w.orgs):
        current = o["stage"]
        for step in range(1 + i % 3):
            nxt = STAGES[(i + step + 1) % len(STAGES)]
            # A no-op event is not a change. An event that restates the
            # stage already in effect must not be seeded, because the answer
            # key counts stage changes and would count it.
            if nxt == current:
                nxt = STAGES[(i + step + 2) % len(STAGES)]
            when = EPOCH + timedelta(days=55 + 45 * step + 3 * i)
            w.changes.append(Change(
                effective=when, recorded=when,
                entity="org", entity_id=o["org_id"], field="stage",
                value=nxt))
            current = nxt

    for o in w.orgs:
        w.defects.setdefault(o["org_id"], "clean")

    w.changes.sort(key=lambda ch: (ch.effective, ch.entity_id, ch.field))
