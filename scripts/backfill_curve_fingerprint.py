"""Stamp curve rows written before the curve carried a condition hash.

What this is and what it is not. `scripts/sweep.py` stamped every arm row with
a hash of what that arm renders and stamped curve rows with the literal string
"curve". 360 of the 1,860 rows in a run, 19.4%, carrying no description of
what produced them. A change to the ranking, to the truncation rule or to
CHARS_PER_TOKEN would have left every one of those rows aggregating under a
label that no longer described them, which is the failure the arm fingerprint
exists to prevent.

The stamp exists now. These rows predate it, so the value this script writes is
an assertion that the code did not change, not a measurement that it did not.
Every row it touches is marked `arm_fingerprint_backfilled: true` so the
difference is legible in the file itself, which is the same convention the
replicate already uses. A reader who does not accept the assertion can drop
every backfilled row and lose the curve rather than be misled by it.

    python3 scripts/backfill_curve_fingerprint.py results/sweep.jsonl
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cqa import assemble, questions, world  # noqa: E402


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    w = world.build()
    qs = questions.build(w)
    live = {f"budget{b}": assemble.curve_fingerprint(w, qs, b)
            for b in assemble.CURVE_BUDGETS}

    for path in (Path(p) for p in sys.argv[1:]):
        rows = [json.loads(x) for x in path.read_text().splitlines() if x.strip()]
        touched = skipped = stale = 0
        for r in rows:
            if r.get("experiment") != "curve":
                continue
            want = live.get(r["arm"])
            if want is None:
                skipped += 1
                continue
            stamp = r.get("arm_fingerprint")
            if stamp == want:
                continue                       # already stamped with it
            if stamp not in (None, "curve"):
                # A real hash of other code. Overwriting it would erase the
                # evidence the report refuses stale rows on.
                stale += 1
                continue
            r["arm_fingerprint"] = want
            r["arm_fingerprint_backfilled"] = True
            touched += 1
        path.write_text("".join(json.dumps(r) + "\n" for r in rows))
        print(f"{path}: {touched} curve rows backfilled"
              + (f", {skipped} at budgets this code no longer runs" if skipped else "")
              + (f", {stale} stamped by other code and left for the report "
                 f"to refuse" if stale else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
