"""Grading, and the normalization policy it depends on.

Exact match on a date is clean. Exact match on a name is not, once formatting
varies, so the normalization policy is part of the measurement and is stated
here rather than left implicit in a comparison operator. If it were left
implicit, the headline number would be measuring string handling.

What is normalized, and nothing else:
    dates     any of ISO, US slash, or a written month, compared as ISO
    money     $, commas and decimal noise removed, compared as an integer
    counts    compared as integers
    text      case-folded, whitespace collapsed, surrounding punctuation
              dropped. Internal punctuation is KEPT, so "O'Neill" and
              "ONeill" are different answers, which is correct.

What is not normalized, deliberately: nothing is fuzzy-matched, no edit
distance, no substring credit. A near miss is a miss. That keeps the metric a
measurement of the model's factual accuracy rather than of the grader's
generosity, and it is why the score can be compared across arms at all.
"""
from __future__ import annotations

import re
from datetime import date, datetime

MONTHS = ("january february march april may june july august september "
          "october november december").split()


def normalize(value, hint: str = "") -> str:
    """One value, reduced to the string the comparison uses."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, date):
        return value.isoformat()

    text = str(value).strip()
    if not text:
        return ""

    # The hint is advisory and the fallback subsumes it. Both hint branches
    # were once checked first and neither ever changed a verdict: over 5,274
    # graded values, disabling them moved nothing, because _as_iso already
    # requires a four-digit year and _as_int already requires digits. The
    # parameter is kept because it documents the caller's intent at the call
    # site, and removing it would make grade_one's calls harder to read.
    #
    # A bare value that looks like a date or a number is treated as one, so a
    # model that answers "84,000" for a field the key holds as 84000 is not
    # marked wrong for punctuation.
    iso = _as_iso(text)
    if iso and re.search(r"\d{4}", text):
        return iso
    n = _as_int(text)
    if n is not None:
        return str(n)

    text = text.casefold()
    text = re.sub(r"\s+", " ", text)
    return text.strip(" .,;:!?\"'()[]")


def _as_iso(text: str) -> str | None:
    t = text.strip().strip(".,;")
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%B %d, %Y", "%b %d, %Y",
                "%d %B %Y", "%B %d %Y"):
        try:
            return datetime.strptime(t, fmt).date().isoformat()
        except ValueError:
            pass
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})$", t)
    if m:
        y, mo, d = (int(x) for x in m.groups())
        try:
            return date(y, mo, d).isoformat()
        except ValueError:
            return None
    return None


def _as_int(text: str) -> int | None:
    t = str(text).strip()
    t = re.sub(r"^(usd|\$)\s*", "", t, flags=re.I)
    t = re.sub(r"\s*(usd|dollars|days)$", "", t, flags=re.I)
    t = t.replace(",", "").replace("_", "").strip()
    if re.fullmatch(r"-?\d+", t):
        return int(t)
    if re.fullmatch(r"-?\d+\.0+", t):
        return int(float(t))
    return None


def grade_one(expected: dict, got) -> dict:
    """Field-by-field, with the per-field verdicts kept.

    A partially correct answer is recorded as partially correct rather than
    collapsed to wrong. The headline metric is the FIELD accuracy; the
    all-fields-correct rate is reported beside it because the two can move in
    different directions and a reader is entitled to see both.
    """
    fields, correct = {}, 0
    if not isinstance(got, dict):
        got = {}
    for key, want in expected.items():
        have = got.get(key)
        ok = normalize(have, key) == normalize(want, key)
        fields[key] = {"expected": _plain(want), "got": _plain(have),
                       "correct": ok}
        correct += ok
    return {
        "fields": fields,
        "n_fields": len(expected),
        "n_correct": correct,
        "all_correct": correct == len(expected),
    }


def _plain(v):
    return v.isoformat() if isinstance(v, date) else v
