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
