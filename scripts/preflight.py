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
it refuses the floor instead of guessing.

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
    behavior for a reader that only reads, so the checks below exempt them.
    """
    # when the question names an agreement, read from that agreement's block.
    # A reader that takes the first matching key answers about the wrong
    # contract whenever an organization holds two, and then reports a defect
    # in a harness that is correct. A failing preflight check is a claim about
    # the harness OR about the checker, and the two must be told apart before
    # anything is changed.
    # The pattern lives in cqa.questions, which is where the id is written.
    # A second copy here would be one more thing to keep in step, and the
    # checks below decide a published figure by it.
    named = questions.names_internal_id(q)
    if named:
        blocks = re.split(r"^\s*- \[\d+\]\s*$", context, flags=re.M)
        context = next((b for b in blocks if named in b), context)

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

    # Its own as-of date too. The system prompt instructs the model to answer
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
    # oracle over it can only ever return None and would prove nothing. What
    # this checks is that the floor prompt states no answer. Whether a MODEL
    # can answer these questions from general knowledge is measured by the
    # paid floor arm and cannot be established here.
    leaky = [q.qid for q in qs
             if assemble.context_for(w, q, "none").strip()
             or any(v in prompt.user_message(q, "")
                    for v in questions.distinctive_answer_values(q))]
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

    # The curve is 360 of the 1,860 paid generations, so it is checked too.
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

    # Every arm must be able to identify what it is asked about.
    #
    # The check above is about answer values. This one is about the ids the
    # question text names. 22 of the 150 questions name an agreement by the
    # world's internal id ("agreement CTR014 at Northwind"), which neither
    # source system carries, and the unresolved arm renders raw source rows.
    # In those 22 contexts the literal id the question names is absent, the
    # model correctly answers null, and about half that arm's published effect
    # is a failure of identification, not of resolution: that arm changes two
    # things, which README.md discloses.
    #
    # Three arms may legitimately lose an identifier, and each is exempt for a
    # reason that is its own named mechanism rather than an oversight:
    ID_EXEMPT = {
        "none": "renders no context at all, which is the floor's definition",
        "incomplete": "drops a fixed number of top-level fields, which is the "
                      "property it measures; the agreements block is "
                      "sometimes among them",
        "unresolved": "renders raw source rows, and no source system carries "
                      "the internal id -- THE DISCLOSED CONFOUND, see README",
    }
    named = [(q, questions.names_internal_id(q)) for q in qs]
    named = [(q, cid) for q, cid in named if cid]
    lost = []
    for arm in assemble.ARMS:
        if arm in ID_EXEMPT:
            continue
        for q, cid in named:
            if cid not in assemble.context_for(w, q, arm):
                lost.append((q.qid, arm, cid))
    check(r, "every arm states the identifiers its questions name, except the "
          "three that cannot", not lost,
          f"{len(lost)} lost across {len(assemble.ARMS) - len(ID_EXEMPT)} arms")

    # The disclosed confound must be all-or-nothing. README.md excludes the
    # whole set of identifier-naming questions when it restates the unresolved
    # effect, and that arithmetic is only right if the arm loses every one of
    # them, not some. A partial loss would need a different correction and
    # would make the published one wrong.
    kept = [q.qid for q, cid in named
            if cid in assemble.context_for(w, q, "unresolved")]
    check(r, "the unresolved arm loses every named identifier, not some",
          not kept and bool(named),
          f"{len(named)} questions name one, {len(kept)} still identifiable")

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


# The schemes urllib will open that this tool has any business opening.
# urllib honors file://, ftp:// and whatever else is registered, so a URL
# that arrives as a string and is opened without a check is a file read
# waiting for the wrong argument.
_LOCAL_SCHEMES = ("http://", "https://")

# An opener that cannot open a file: the mechanism, not just the promise. The
# string check below refuses the wrong scheme; this makes the refusal true of
# the machinery too, so an edit that drops the sentence still cannot read a
# file.
#
# Built from an empty OpenerDirector, not from build_opener. `build_opener`
# adds the default handlers to whatever it is given, FileHandler among them, so
# `build_opener(HTTPHandler, HTTPSHandler)` reads /etc/passwd perfectly well.
# A restricted opener has to be assembled from nothing, and the claim has to be
# run against the scheme it forbids.
#
# UnknownHandler is what makes the refusal an error. An OpenerDirector with no
# handler for a scheme does not raise; it returns None, and the caller then
# fails on `None.__enter__` with an AttributeError that names nothing. That is
# a refusal by accident. UnknownHandler raises URLError("unknown url type:
# file"), which is a refusal that says what it refused.
_HTTP_ONLY = urllib.request.OpenerDirector()
for _handler in (urllib.request.HTTPHandler, urllib.request.HTTPSHandler,
                 urllib.request.HTTPRedirectHandler,
                 urllib.request.HTTPErrorProcessor,
                 urllib.request.UnknownHandler):
    _HTTP_ONLY.add_handler(_handler())


def ask_local(base_url: str, model: str, q, context: str):
    """One call to an OpenAI-compatible local endpoint.

    The scheme is checked before the URL is opened. `--local` is an operator
    argument, not untrusted input, so this is not a hole somebody is reaching
    through, but `urllib.request.urlopen` will happily open
    `file:///etc/passwd`, and the operator typing it would get a JSON parse
    error instead of a refusal. A one-line scheme check removes the surface
    instead of arguing about how reachable it is.
    """
    if not base_url.startswith(_LOCAL_SCHEMES):
        raise ValueError(
            f"--local must be an http:// or https:// URL, not {base_url!r}. "
            f"urllib would open a file:// or ftp:// URL as readily as an "
            f"endpoint, and layer 2 talks to a model over HTTP.")
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
    with _HTTP_ONLY.open(req, timeout=180) as resp:
        payload = json.load(resp)
    text = payload["choices"][0]["message"]["content"]
    m = re.search(r"\{.*\}", text, re.S)
    return (json.loads(m.group(0)) if m else None), text


def layer2(w, qs, base_url: str, model: str) -> list:
    r: list = []
    # The same refusal as ask_local's, and here first. Both functions take the
    # same (base_url, model), and this one renders a sample of questions before
    # the first request is built, so without the check the operator who typed
    # a file:// URL would wait through that work to be told at the last moment,
    # by the other function. A guard on one of two siblings is a guard with a way
    # around it.
    if not base_url.startswith(_LOCAL_SCHEMES):
        raise ValueError(
            f"--local must be an http:// or https:// URL, not {base_url!r}.")
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
