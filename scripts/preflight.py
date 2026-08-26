"""Prove the harness before spending anything on it.

    python3 scripts/preflight.py                    # no model, no network
    python3 scripts/preflight.py --local <base_url> # a local model too

Two layers, and the first needs nothing.

LAYER 1: the oracle reader. A deterministic stand-in for a model: it reads
the assembled context and returns whatever the context states, using no
knowledge of the world. It is a PERFECT reader with no memory and no
reasoning, which makes it exactly the instrument for the questions a paid run
must never be asked to answer:

    Does every arm render, and does every prompt carry its own question? Is
    the floor really a floor, can a reader with NO context answer? Is the
    ceiling really reachable, does the perfect arm STATE its answers? Does the
    grader accept a correct answer and reject a near miss? Does the leak
    detector fire on exactly the arm that bypasses policy?

Those are properties of the HARNESS, not of any model, and every one of them
has been wrong here at least once. Each was found by paying for a run.

LAYER 2: a local model, optional. Point --local at any OpenAI-compatible
endpoint (llama.cpp's server, ollama, vLLM) and a sample of questions is run
through it for real. What this validates is narrow: that a real model, given
these prompts, returns schema-valid JSON that the grader can score, and that
it refuses the floor rather than guessing.

What it does not validate is the result. A small local model has a different
accuracy profile, so arm separation seen here does not predict the paid run
and must never be reported as if it did. It is a smoke test, not a preview.

Exit status is 0 when every check passes and 1 otherwise, so it can gate.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cqa import assemble, grade, leak, prompt, questions, sources, world

LOCAL_SAMPLE = 12


def oracle(q, context: str) -> dict:
    """Answer only from what the context literally states.

    Reads "key: value" lines and matches them to the answer keys by name. It
    cannot compute, so derived answers come back as None, which is correct
    behavior for a reader that only reads, and is why the checks below exempt
    them rather than pretending otherwise.
    """
    # when the question names an agreement, read from that agreement's block.
    # A reader that takes the first matching key answers about the wrong
    # contract whenever an organization holds two, and then reports a defect
    # in a harness that is correct. A failing preflight check is a claim about
    # the harness OR about the checker, and the two must be told apart before
    # anything is changed.
    named = re.search(r"\b(CTR\d+)\b", q.text)
    if named:
        blocks = re.split(r"^\s*- \[\d+\]\s*$", context, flags=re.M)
        context = next((b for b in blocks if named.group(1) in b), context)

    stated: dict[str, list[str]] = {}
    for line in context.splitlines():
        m = re.match(r"^\s*([a-z_]+):\s*(.+?)\s*$", line)
        if m:
            stated.setdefault(m.group(1), []).append(m.group(2))

    alias = {
        "owner": "account_owner", "segment": "segment",
        "stage": "lifecycle_stage", "hq_state": "hq_state",
        "employees": "employee_count", "organization": "organization",
        "renewal_date": "renewal_date", "acv": "acv",
    }
    out = {}
    for key in q.answer:
        want = alias.get(key)
        out[key] = stated[want][0] if want and want in stated else None
    return out


def check(results: list, name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{'  ' + detail if detail else ''}")


def layer1(w, qs, values) -> list:
    r: list = []
    print("LAYER 1 -- oracle reader, no model, no network")

    # A check that passes a literal True IS NOT A CHECK. Assert a property
    # the rendering could actually violate: every arm but the floor must
    # produce content, and no two arms may be byte-identical, or one of them
    # is not the condition it claims to be.
    empty, identical = [], []
    for q in qs:
        rendered = {arm: assemble.context_for(w, q, arm)
                    for arm in assemble.ARMS}
        for arm, text in rendered.items():
            if arm != "none" and not text.strip():
                empty.append((q.qid, arm))
        seen: dict[str, str] = {}
        for arm, text in rendered.items():
            if arm == "none":
                continue
            if text in seen and {arm, seen[text]} != {"stale", "resolved"}:
                identical.append((q.qid, seen[text], arm))
            seen[text] = arm
    check(r, "every arm produces distinct, non-empty context",
          not empty and not identical,
          f"{len(empty)} empty, {len(identical)} collisions")

    missing = [q.qid for q in qs if q.text not in prompt.user_message(q, "")]
    check(r, "every prompt carries its own question", not missing,
          f"{len(missing)} missing")

    # And its own as-of date. The system prompt instructs the model to answer
    # as of the date given, every arm assembles as of a specific date, the
    # stale arm exists to disagree with it, and the key is computed from it.
    # The check above looks only for the question text, so removing the date
    # header leaves it green while every prompt in the run loses the one fact
    # the instruction refers to.
    undated = [q.qid for q in qs
               if q.as_of.isoformat() not in prompt.user_message(q, "")]
    check(r, "every prompt states its own as-of date", not undated,
          f"{len(undated)} missing")

    # Named for what it actually tests. The oracle reads the context, and the
    # floor arm's context is the empty string by construction, so running the
    # oracle over it can only ever return None. That made the old check a
    # tautology wearing the title of a much stronger claim. Whether a MODEL
    # can answer these questions from general knowledge is measured by the
    # paid floor arm and cannot be established here.
    leaky = [q.qid for q in qs
             if assemble.context_for(w, q, "none").strip()
             or any(str(v) in prompt.user_message(q, "")
                    for v in q.answer.values()
                    if isinstance(v, str) and len(str(v)) > 4)]
    check(r, "the floor arm carries no context and no answer in its prompt",
          not leaky, f"{len(leaky)} prompts contain their own answer")

    derived = {"total_acv", "days_until_renewal", "organizations",
               "stage_changes", "agreements", "source_records"}
    unreachable = []
    for q in qs:
        got = oracle(q, assemble.context_for(w, q, "perfect"))
        for key, want in q.answer.items():
            if key in derived:
                continue
            if grade.normalize(got.get(key), key) != grade.normalize(want, key):
                unreachable.append((q.qid, key))
    check(r, "the ceiling STATES every non-derived answer", not unreachable,
          f"{len(unreachable)} unreachable")

    q0 = qs[0]
    good = grade.grade_one(q0.answer, dict(q0.answer))
    near = grade.grade_one(
        q0.answer, {k: (str(v) + "x") for k, v in q0.answer.items()})
    check(r, "the grader accepts a correct answer", good["all_correct"])
    check(r, "the grader rejects a near miss", near["n_correct"] == 0)

    leaking = set()
    for q in qs:
        for arm in assemble.ARMS:
            text = prompt.user_message(q, assemble.context_for(w, q, arm))
            if leak.scan(text, values)["any"]:
                leaking.add(arm)
    check(r, "exactly one arm bypasses the field policy",
          leaking == {"unpoliced"}, f"leaking: {sorted(leaking) or 'none'}")

    # A length check on a fixed-width slice cannot fail. What matters is that
    # the fingerprint MOVES when the question set moves, since its whole job
    # is to stop results outliving the inputs that produced them.
    fp = questions.fingerprint(qs)
    perturbed = list(qs)
    first = perturbed[0]
    perturbed[0] = type(first)(first.qid, first.stratum, first.as_of,
                               first.text,
                               {**first.answer, "__probe__": "x"},
                               first.org_id)
    check(r, "the fingerprint changes when any answer key changes",
          questions.fingerprint(perturbed) != fp, fp)

    # THE CURVE IS 360 OF 1,860 paid generations and was never exercised here.
    curve_qs = questions.curve_subset(qs)
    sizes, curve_leaks = [], 0
    for q in curve_qs:
        prev = -1
        for bkt in assemble.CURVE_BUDGETS:
            text = assemble.curve_context(w, q, bkt)
            if leak.scan(prompt.user_message(q, text), values)["any"]:
                curve_leaks += 1
            if len(text) < prev:
                sizes.append((q.qid, bkt))
            prev = len(text)
    check(r, "the curve renders and grows with its budget", not sizes,
          f"{len(sizes)} budgets shrank")
    check(r, "the curve carries no forbidden field", curve_leaks == 0,
          f"{curve_leaks} leaking prompts")

    binds = all(
        len(assemble.curve_context(w, q, b)) <= b * assemble.CHARS_PER_TOKEN + 1
        for q in curve_qs for b in assemble.CURVE_BUDGETS)
    check(r, "the curve budget actually bounds the context", binds)

    # The key must be obtainable from a source system. A baseline that states
    # a value neither CRM carries is reading world truth no pipeline could
    # reach, and the arm gap then measures oracle access.
    unobtainable = []
    for q in qs:
        blob = json.dumps(sources.crm_a(w, q.as_of), default=str) + \
            json.dumps(sources.crm_b(w, q.as_of), default=str)
        for key, want in q.answer.items():
            if key in derived or not isinstance(want, (str, int)):
                continue
            if str(want) not in blob:
                unobtainable.append((q.qid, key, want))
    check(r, "every answer key is obtainable from a source system",
          not unobtainable, f"{len(unobtainable)} unobtainable")
    return r


def ask_local(base_url: str, model: str, q, context: str):
    """One call to an OpenAI-compatible local endpoint."""
    body = json.dumps({
        "model": model,
        "messages": [{"role": "system", "content": prompt.SYSTEM},
                     {"role": "user", "content": prompt.user_message(q, context)}],
        "max_tokens": 400,
        "temperature": 0,
    }).encode()
    req = urllib.request.Request(
        base_url.rstrip("/") + "/v1/chat/completions", data=body,
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer local"})
    with urllib.request.urlopen(req, timeout=180) as resp:
        payload = json.load(resp)
    text = payload["choices"][0]["message"]["content"]
    m = re.search(r"\{.*\}", text, re.S)
    return (json.loads(m.group(0)) if m else None), text


def layer2(w, qs, base_url: str, model: str) -> list:
    r: list = []
    print(f"\nLAYER 2 -- local model at {base_url} ({model})")
    sample = qs[::max(1, len(qs) // LOCAL_SAMPLE)][:LOCAL_SAMPLE]
    parsed = floor_ok = 0
    for q in sample:
        try:
            ans, _ = ask_local(base_url, model, q,
                               assemble.context_for(w, q, "perfect"))
        except (urllib.error.URLError, OSError, KeyError) as exc:
            check(r, "local endpoint reachable", False, str(exc)[:60])
            return r
        parsed += isinstance(ans, dict) and set(ans) >= set(q.answer)
        none_ans, _ = ask_local(base_url, model, q,
                                assemble.context_for(w, q, "none"))
        if isinstance(none_ans, dict) and all(
                v in (None, "", "null") for v in none_ans.values()):
            floor_ok += 1
    check(r, "local model returns schema-shaped JSON", parsed == len(sample),
          f"{parsed}/{len(sample)}")
    check(r, "local model refuses the no-context arm rather than guessing",
          floor_ok >= len(sample) * 0.6, f"{floor_ok}/{len(sample)}")
    print("\n  NOTE: layer 2 proves the prompts and the grader work against a"
          "\n  real model. It does NOT predict the paid run's numbers and must"
          "\n  not be reported as if it did.")
    return r


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--local", default="",
                    help="base URL of an OpenAI-compatible local server")
    ap.add_argument("--model", default="local",
                    help="model name the local server expects")
    args = ap.parse_args()

    w = world.build()
    qs = questions.build(w)
    values = leak.forbidden_values(w)

    results = layer1(w, qs, values)
    if args.local:
        results += layer2(w, qs, args.local, args.model)

    failed = [n for n, ok, _ in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    if failed:
        print("REFUSING TO CERTIFY. Do not start a paid run:")
        for n in failed:
            print(f"  - {n}")
        return 1
    print("Harness is sound. A paid run measures the model, not the harness.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
