# Predictions, recorded before the runs

Written down before any model was called, so that a refuted one cannot quietly
become a footnote. Both are reproduced here unchanged.

What this file can and cannot establish, said plainly: it is a claim of
pre-registration, not a proof of it. Nothing here is timestamped by a third
party, and a reader who wants proof rather than a claim will not find it. The
reason to believe it is that the refuted prediction is still here, stated as
strongly as it was made.

## 1. The token-budget curve is not monotonic

> More context is NOT monotonically better. Accuracy will rise, flatten, and
> then DECLINE at large budgets as the answer-bearing fields are diluted by
> correct-but-irrelevant ones. If that is refuted, say so and publish it.

Refuted, on both vendors. No budget beats the largest by more than noise. The
only budgets that separate do so downward, which is the opposite claim. Claude's
point estimates do fall past 600 tokens and GPT's do not fall at all, but
neither separation supports the prediction.

The finding that survives is weaker and duller: more context stops helping.
This design cannot show it starting to hurt.

## 2. The optimum is lower for unresolved context

> The budget at which accuracy peaks is LOWER for unresolved context than for
> resolved, because unresolved context spends its budget on duplicates. That
> would make the token-budget curve a diagnostic for resolution quality rather
> than a separate finding.

Not tested. The curve was run against ranked production context only, so there
is no unresolved curve to compare. It is recorded here because it was recorded
before the run, and dropping a prediction because it went unmeasured is how a
prediction list becomes a list of successes.

## What was expected and did happen

That the ablation would separate the conditions at all, and that incompleteness
and unresolved entities would be among the larger effects. That is a weak
prediction and it is marked as one: it is not evidence of much, and it is
listed so this file is not only the two that failed.
