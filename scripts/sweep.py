"""The full sweep: every question in every arm, plus the token-budget curve.

    ENV_FILE=~/.secrets/ai.env .venv/bin/python scripts/sweep.py
    ENV_FILE=~/.secrets/ai.env .venv/bin/python scripts/sweep.py --workers 8

The key is read from the file ENV_FILE names and is never printed, never put
on a command line and never written to any artifact.

Resumable and concurrent. Each generation is appended as it completes and a
re-run skips what is already recorded, so a rate limit or a dropped connection
costs one call rather than the whole bill. Ordering of the output file is
therefore arrival order, not question order, and every consumer keys on
(qid, arm) rather than on position.

Two experiments share one runner. The arms answer WHICH property of context
matters; the curve answers HOW MUCH context is worth buying. They are recorded
in the same file with an `experiment` field, because they share a model, a
prompt and a question set and separating them would invite the two halves to
drift apart.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cqa import assemble, grade, leak, prompt, questions, world

# Two providers, one harness. The prompts, the grader and the leak detector
# are identical across providers; only the client and the model change. That
# is what makes the comparison a comparison rather than two experiments.
#
# Prices per million tokens, read from a vendor's own published pricing page
# on the date named here and not from any model's cached table. Sonnet 5 is
# $2/$10 standard: the increase to $3/$15 once scheduled for 2026-09-01 was
# formally canceled. Verified 2026-08-24.
PROVIDERS = {
    "anthropic": {"model": "claude-sonnet-5", "in": 2.00, "out": 10.00,
                  "key": "ANTHROPIC_API_KEY"},
    "openai": {"model": "gpt-5.6-terra", "in": 2.00, "out": 12.00,
               "key": "OPENAI_API_KEY"},
}
EFFORT = "low"
MAX_TOKENS = 1024
MODEL = PROVIDERS["anthropic"]["model"]
RESULTS = Path(__file__).resolve().parents[1] / "results" / "sweep.jsonl"

_lock = threading.Lock()


def load_key(name: str = "ANTHROPIC_API_KEY") -> str:
    """Read the key from the file ENV_FILE names. Never print it."""
    if os.environ.get(name):
        return os.environ[name]
    path = Path(os.path.expanduser(os.environ.get("ENV_FILE", ".env")))
    if not path.is_file():
        sys.exit(f"no credentials: set {name} or point ENV_FILE at "
                 f"a file that defines it (looked at {path})")
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("#") or "=" not in line:
            continue
        name_, _, value = line.partition("=")
        if name_.strip() == name:
            return value.strip().strip('"').strip("'")
    sys.exit(f"{name} not defined in {path}")


def done_keys(results: Path) -> set[tuple[str, str]]:
    if not results.is_file():
        return set()
    out = set()
    for line in results.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            out.add((r["qid"], r["arm"]))
    return out


def ask_openai(client, model, q, context: str):
    """One generation against an OpenAI chat-completions endpoint."""
    user = prompt.user_message(q, context)
    last = None
    for attempt in range(5):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "system", "content": prompt.SYSTEM},
                          {"role": "user", "content": user}],
                reasoning_effort="low",
                response_format={
                    "type": "json_schema",
                    "json_schema": {"name": "answer", "strict": True,
                                    "schema": prompt.answer_schema(q)},
                },
            )
            text = resp.choices[0].message.content or ""
            usage = {"input": resp.usage.prompt_tokens,
                     "output": resp.usage.completion_tokens}
            try:
                return json.loads(text), usage, text
            except json.JSONDecodeError:
                return None, usage, text
        except Exception as exc:                      # noqa: BLE001
            last = exc
            if attempt == 4:
                break
            time.sleep(min(2 ** attempt, 8))
    raise RuntimeError(f"failed after retries: {type(last).__name__}: {last}")


def ask(client, q, context: str, model=None):
    """One generation. Returns (parsed answer, usage, raw text)."""
    user = prompt.user_message(q, context)
    last = None
    for attempt in range(7):
        try:
            resp = client.messages.create(
                model=model or MODEL,
                max_tokens=MAX_TOKENS,
                system=prompt.SYSTEM,
                messages=[{"role": "user", "content": user}],
                output_config={
                    "effort": EFFORT,
                    "format": {"type": "json_schema",
                               "schema": prompt.answer_schema(q)},
                },
            )
            text = "".join(b.text for b in resp.content
                           if getattr(b, "type", "") == "text")
            usage = {"input": resp.usage.input_tokens,
                     "output": resp.usage.output_tokens}
            try:
                return json.loads(text), usage, text
            except json.JSONDecodeError:
                return None, usage, text
        except Exception as exc:                      # noqa: BLE001
            last = exc
            if attempt == 4:
                break
            time.sleep(min(2 ** attempt, 8))
    raise RuntimeError(f"failed after retries: {type(last).__name__}: {last}")




def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", default="anthropic",
                    choices=sorted(PROVIDERS))
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    cfg = PROVIDERS[args.provider]
    model = cfg["model"]
    results = (RESULTS if args.provider == "anthropic"
               else RESULTS.with_name(f"sweep_{args.provider}.jsonl"))

    if args.provider == "anthropic":
        import anthropic
        client = anthropic.Anthropic(api_key=load_key(cfg["key"]),
                                     max_retries=3)
    else:
        import openai
        client = openai.OpenAI(api_key=load_key(cfg["key"]), max_retries=3)

    w = world.build()
    qs = questions.build(w)
    values = leak.forbidden_values(w)
    fp = questions.fingerprint(qs)
    arm_fp = {a: assemble.arm_fingerprint(w, qs, a)
              for a in assemble.ARMS}
    # The curve reuses the arm slot for its budget, so its rows are stamped
    # the same way. A curve point is a condition and a row that does not
    # describe what rendered it cannot be invalidated when that changes.
    arm_fp.update({f"budget{b}": assemble.curve_fingerprint(w, qs, b)
                   for b in assemble.CURVE_BUDGETS})
    results.parent.mkdir(parents=True, exist_ok=True)
    already = done_keys(results)

    # The unit of work is (question, arm-label, context). The curve reuses the
    # arm slot for its budget so one results file describes both experiments.
    units = []
    for q in qs:
        for arm in assemble.ARMS:
            if (q.qid, arm) not in already:
                units.append((q, arm, "arms"))
    curve_qs = questions.curve_subset(qs)
    for q in curve_qs:
        for bkt in assemble.CURVE_BUDGETS:
            arm = f"budget{bkt}"
            if (q.qid, arm) not in already:
                units.append((q, arm, "curve"))
    if args.limit:
        units = units[:args.limit]

    print(f"{len(units)} generations to run ({len(already)} already "
          f"recorded), {args.provider} {model}, effort {EFFORT}, "
          f"{args.workers} workers, question set {fp}")

    state = {"n": 0, "tin": 0, "tout": 0, "fail": 0, "reasons": {}}
    fh = results.open("a", encoding="utf-8")
    # Causes go to a file of their own so a redirected run keeps them.
    failures = results.with_suffix(".failures.jsonl").open("a",
                                                          encoding="utf-8")

    def run(unit):
        q, arm, experiment = unit
        if experiment == "curve":
            context = assemble.curve_context(
                w, q, int(arm.replace("budget", "")))
        else:
            context = assemble.context_for(w, q, arm)
        sent = prompt.SYSTEM + prompt.user_message(q, context)
        try:
            if args.provider == "openai":
                answer, usage, raw = ask_openai(client, model, q, context)
            else:
                answer, usage, raw = ask(client, q, context, model)
        except RuntimeError as exc:
            with _lock:
                state["fail"] += 1
                state["reasons"][type(exc.__cause__ or exc).__name__] = \
                    state["reasons"].get(
                        type(exc.__cause__ or exc).__name__, 0) + 1
                print(f"  FAILED {q.qid} {arm}: {exc}", flush=True)
                failures.write(json.dumps(
                    {"qid": q.qid, "arm": arm, "error": str(exc)[:400]}) + "\n")
                failures.flush()
            return
        row = {
            "experiment": experiment, "qid": q.qid, "arm": arm,
            "stratum": q.stratum, "as_of": q.as_of.isoformat(),
            "answer": answer, "grade": grade.grade_one(q.answer, answer),
            "governance": leak.assess(sent, raw, values),
            "usage": usage, "provider": args.provider,
            "model": model, "effort": EFFORT,
            "questions_fingerprint": fp,
            "arm_fingerprint": arm_fp[arm],
        }
        with _lock:
            fh.write(json.dumps(row) + "\n")
            fh.flush()
            state["n"] += 1
            state["tin"] += usage["input"]
            state["tout"] += usage["output"]
            if state["n"] % 100 == 0:
                cost = (state["tin"] / 1e6 * cfg["in"]
                        + state["tout"] / 1e6 * cfg["out"])
                print(f"  {state['n']:>5}/{len(units)}  "
                      f"in {state['tin']:>9,}  out {state['tout']:>7,}  "
                      f"${cost:,.2f}", flush=True)

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        list(pool.map(run, units))
    fh.close()
    failures.close()

    cost = (state["tin"] / 1e6 * cfg["in"]
            + state["tout"] / 1e6 * cfg["out"])
    print(f"\n{state['n']} recorded, {state['fail']} failed"
          + (f" ({state['reasons']})" if state["fail"] else ""))
    if state["fail"]:
        print(f"causes written to {results.with_suffix('.failures.jsonl')}")
        print("THE RUN IS INCOMPLETE. Re-run to fill the gaps; recorded "
              "generations are skipped.")
    print(f"input {state['tin']:,} output {state['tout']:,} tokens; "
          f"about ${cost:,.2f} at list price")
    print(f"results in {results}")
    return 1 if state["fail"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
