"""Stamp rows written before the prompt carried a hash of its own.

Model, prompt and question set are the three inputs this experiment holds
constant while context varies. The paid rows were written with two of them
hashed (`questions_fingerprint` and `arm_fingerprint`) and not the prompt, and
rewriting the first rule of `prompt.SYSTEM` from "Answer strictly from the
context" to "Use outside knowledge freely" changes what the floor arm
measures. Rows written now carry a prompt hash from write time.

The shipped rows predate it, so the value this script writes is an assertion
that the prompt did not change, not a measurement that it did not.
Every row it touches is marked `prompt_fingerprint_backfilled: true` so the
difference is legible in the file itself, which is the convention the curve
backfill and the replicate already use. A reader who does not accept the
assertion can drop every backfilled row and lose the run instead of being
misled by it.

How big the assertion is. The prompt is SYSTEM plus a template filled with the
question's text, its as-of date and its answer schema. Everything filled IN is
already covered by `questions_fingerprint`, which these rows do carry from
write time, so what this script asserts is only the part that is not: the
wording of SYSTEM and of the template around them.

Whether the shipped rows can check even that was measured. Every row records
the vendor's own input-token count, and every prompt can be re-rendered today,
so input tokens were regressed on today's rendered characters, over the floor
arm (where the prompt is almost all template) and over all 1,500 arm rows. Residual spread: 15.9 tokens on the
Claude floor arm, 28.1 across its arms, 5.0 and 21.0 for GPT. Two template
edits were then applied to the re-rendering and the fit recomputed:

    SYSTEM, 40 more characters       residual spread x1.00 on all four
    the schema block re-indented     residual spread x0.96 - x1.00

Neither is visible. A constant edit is absorbed by the intercept, and a
per-question edit is smaller than the tokenizer noise it has to clear. So the
rows cannot check this assertion, and a figure claiming otherwise would be
worse than the assertion itself.

So `scripts/report.py` prints, above every table it renders, how many of the
rows carry a hash written after the run, and says in those words that such a
hash is an assertion and not a measurement. The limit is disclosed where the
numbers are read instead of only here.

A re-run is what settles it, and a re-run stamps the hash at write time and
needs no assertion at all.

    python3 scripts/backfill_prompt_fingerprint.py results/sweep.jsonl
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cqa import prompt, questions, world  # noqa: E402


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    w = world.build()
    qs = questions.build(w)
    live = prompt.fingerprint(qs)

    for path in (Path(p) for p in sys.argv[1:]):
        rows = [json.loads(x) for x in path.read_text().splitlines()
                if x.strip()]
        touched = already = stale = 0
        for r in rows:
            stamp = r.get("prompt_fingerprint")
            if stamp == live:
                already += 1
                continue
            if stamp is not None:
                # Stamped under a different prompt. Overwriting it would
                # erase the evidence the report refuses stale rows on.
                stale += 1
                continue
            r["prompt_fingerprint"] = live
            r["prompt_fingerprint_backfilled"] = True
            touched += 1
        path.write_text("".join(json.dumps(r) + "\n" for r in rows))
        print(f"{path}: {touched} rows backfilled with prompt {live}"
              + (f", {already} already stamped with it" if already else "")
              + (f", {stale} stamped with another prompt and left for the "
                 f"report to refuse" if stale else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
