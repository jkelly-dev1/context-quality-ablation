"""The prompt, which is the thing held constant while context varies.

One template, every arm. If the instruction changed between arms the
experiment would be measuring prompting, not data. The only text that differs
between two arms is the block returned by assemble.context_for.

The task is deliberately framed so that a model with no context should refuse
rather than guess. An arm-0 score above noise means the questions are
answerable from general knowledge, which would mean the entities are not
synthetic enough and the whole ablation is measuring fluency.
"""
from __future__ import annotations

import hashlib
import json

from .questions import Question

SYSTEM = (
    "You answer questions about a company's customer records using ONLY the "
    "context provided.\n"
    "\n"
    "Rules:\n"
    "- Answer strictly from the context. Do not use outside knowledge about "
    "any organization or person named.\n"
    "- If the context does not contain what is needed, return null for that "
    "field. A null is better than a guess.\n"
    "- Dates are ISO (YYYY-MM-DD). Money is a plain integer of US dollars, "
    "with no symbol, comma or decimal.\n"
    "- Answer as of the AS-OF DATE given, not as of any later state.\n"
)


def user_message(q: Question, context: str) -> str:
    schema = json.dumps({k: "..." for k in q.answer}, indent=2)
    block = context.strip() or "(no context provided)"
    return (
        f"AS-OF DATE: {q.as_of.isoformat()}\n"
        f"\n"
        f"CONTEXT:\n"
        f"{block}\n"
        f"\n"
        f"QUESTION: {q.text}\n"
        f"\n"
        f"Return a JSON object with exactly these keys:\n"
        f"{schema}\n"
    )


# A placeholder, so that hashing the prompt hashes the PROMPT. Substituting a
# real context would fold the arm into this hash, and the arm already has one.
_PLACEHOLDER = "<context>"


def fingerprint(qs) -> str:
    """A hash of the prompt every generation in a run was sent inside.

    This module's own first line calls the prompt "the thing held constant
    while context varies". The question-set and arm hashes say nothing about
    the instruction the model was answering under, and rewriting the rule at
    the top of SYSTEM ("Answer strictly from the context" into "Use outside
    knowledge freely") changes what the floor arm means. This hash makes a
    results row describe that input too.

    What it covers: SYSTEM, and the rendered user message for every question
    with a placeholder in place of the context. That takes in the wording, the
    AS-OF DATE header, the question line, the JSON schema and the order they
    appear in. What it deliberately does not cover is the context itself,
    which is what `assemble.arm_fingerprint` is for.
    """
    blob = SYSTEM + "\n".join(user_message(q, _PLACEHOLDER) for q in qs)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def answer_schema(q: Question) -> dict:
    """A strict object schema, so the answer arrives parsed rather than read.

    Values are typed as string-or-number-or-null rather than tightly, because
    a model forced to emit an integer for a field it does not know cannot
    express "I do not know", and the ability to return null is what makes the
    no-context floor meaningful.
    """
    return {
        "type": "object",
        "additionalProperties": False,
        "required": list(q.answer),
        "properties": {
            k: {"type": ["string", "number", "null"]} for k in q.answer
        },
    }
