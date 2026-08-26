# context-quality-ablation

[![CI](https://github.com/jkelly-dev1/context-quality-ablation/actions/workflows/ci.yml/badge.svg)](https://github.com/jkelly-dev1/context-quality-ablation/actions/workflows/ci.yml)

Every vendor asserts that the data foundation determines what an LLM answers.
This measures it: one question set, ten context conditions, two model vendors,
and an answer key that is computed rather than judged.

The claim in one line: the properties of context that matter are not the ones
the marketing talks about, and the one that matters most for security is
invisible to every quality metric you have.

A learning project. Every figure is read from a shipped results file rather than
written into the prose, and the predictions were fixed before the runs. The one
the runs refuted is still here, still refuted.

What you need to run everything except the paid sweeps: `python3`. No container,
no database, no service, no network. The test suite finishes in seconds and the
pre-flight in about a minute.

## The headline finding

Bypassing a field-level privacy policy leaked on every single prompt and left
no trace a quality metric could find.

The `unpoliced` condition is the production baseline with one thing removed: the
policy that strips a value which may never enter a prompt. Nothing else differs:
strip the forbidden field's lines from it and the two contexts are
byte-identical, which is what the test asserts rather than a size band. That
makes it about 26 tokens larger, roughly three percent. It leaked into 150 of
150 prompts, on both vendors and in both Claude runs.

What its accuracy did is not a clean null. Across two Claude runs of the
identical configuration it scored 99.6 and 98.7 percent against baselines of
97.5 and 98.7. So it landed ABOVE the baseline once and level with it once. On
GPT it was 97.1 against 97.9, slightly below.

That pattern is what no effect looks like. The arm oscillates around the
baseline across runs instead of sitting consistently on one side of it, and
there is no mechanism by which leaking a field nobody asks about would improve
an answer. A single null result cannot be told apart from an underpowered test;
a sign that flips between runs can.

And the reason cuts against the finding as much as for it: the leaked field is a
government identifier that no question asks about. That it does not change
accuracy is close to a foregone conclusion rather than a discovery. What the
experiment establishes is narrower: the leak is total, it is invisible to the
metric a team would actually watch, and the only way to find it is to read the
prompt bytes, which is what `cqa/leak.py` does and what a quality dashboard
never will.

Across every run the forbidden value reached the model's OUTPUT 0 times and was
reconstructed from permitted fields 0 times. The other 1710 generations of each
run carried no forbidden material at all.

## What the ablation measured

The corpus holds 150 generated questions, each asked under ten conditions differing from the
resolved production baseline in exactly one property. 1860 generations per run.
Field-level accuracy, paired by question, bootstrap interval over questions.

| condition | Claude | Claude replicate | GPT | what it removes |
|---|---|---|---|---|
| no context | 0.0 | 0.0 | 0.0 | the floor |
| unpoliced | 99.6 | 98.7 | 97.1 | the field policy |
| diluted | 98.7 | 99.2 | **95.8** | selectivity, not content |
| nostructure | **98.3** | 99.2 | 97.5 | key/value form, same facts |
| resolved (baseline) | 97.5 | 98.7 | 97.9 | nothing |
| perfect | 97.1 | 97.5 | 97.1 | everything irrelevant |
| stale | **94.1** | 93.3 | **92.0** | 30 days on volatile fields |
| governed | **93.3** | 95.4 | **94.5** | precision, via a privacy transform |
| unresolved | **77.7** | 81.1 | **84.0** | entity resolution |
| incomplete | **57.6** | 57.1 | **56.3** | 40 percent of available fields |

## The most important number here is not in that table

The same configuration run twice moves by up to 3.4 POINTS, mean 1.05 across the
ten conditions. There is ONE generation per cell, so the bootstrap resamples
questions and captures NONE of the model's own run-to-run variance. The
intervals in `scripts/report.py` therefore understate the true uncertainty, and
this replicate is how much by.

Measured against that, the effects sort into two groups and only one of them
is safe to call established:

  ROBUST. Incompleteness (-39.9 and -41.6 across runs) and unresolved entities
  (-19.7 and -17.6). Both are an order of magnitude larger than the drift, and
  both replicate across the two vendors as well.

  Not established. Governance (-4.2 and -3.4) and staleness are the same size as
  the between-run movement of the baseline itself. Their intervals exclude zero
  WITHIN a run and that is not enough. Treat them as suggestive.

  No effect. Dilution, prose rendering and the policy bypass move in both
  directions across runs.

The ordering of the two robust effects replicates across both vendors, which is
the transferable claim: incompleteness costs more than unresolved entities, and
both cost far more than presentation. That is a property of context rather than
of one model, and a single-vendor single-run study could not have separated the
two.

## The prediction that was refuted

Recorded before any run: that accuracy would rise, flatten, and then DECLINE
as the context budget grew, because answer-bearing facts get diluted.

IT IS NOT SUPPORTED, on either vendor or either run. The only budgets that
separate from the largest are the small ones, and they separate DOWNWARD: the
opposite claim, and not evidence for it.

Claude peaks at a 600-token budget and drifts down slightly after; GPT climbs to
2,400 and stops. No interval separates in the direction the prediction needs.
The honest statement is that more context stops helping and this design cannot
show it starting to hurt.

The prediction is recorded in `PREDICTIONS.md`, unchanged.

## Why the answer key can be trusted

The expensive part of an ablation is ground truth. A usual approach budgets
weeks of expert grading and then calibrates an LLM judge against it. Neither was
available here, and a judge calibrated against nothing is a second model's
opinion wearing a number.

So the task was chosen to make the key computable. A generator writes the
world; every question is a lookup or a small computation over that world as of
a stated date; grading is exact match after a stated normalization policy.
There is no judge anywhere in the measurement path.

The floor proves the questions need the context: with no context at all, both
vendors scored 0.0 percent across 150 questions.

What this gives up, said plainly: it measures factual accuracy on retrievable
facts. It says nothing about prose quality, helpfulness, or synthesis. A narrow
claim that is exactly true beats a broad one resting on an uncalibrated judge.

## Claims backed by tests

| claim | test |
|---|---|
| A question with no context carries no answer in its prompt | `tests/test_harness.py::test_the_floor_arm_carries_no_context_and_no_answer_in_its_prompt` |
| The ceiling condition states every non-derived answer it is asked for | `tests/test_harness.py::test_the_perfect_arm_contains_every_answer_value_it_can_state` |
| Every answer key is obtainable from a source system, so no condition reads world truth a pipeline could not reach | `tests/test_harness.py::test_every_answer_key_is_supported_by_the_baseline_context_too` |
| The forbidden field reaches exactly one condition and no other | `tests/test_harness.py::test_the_forbidden_field_never_reaches_any_arm_except_the_bypass` |
| That condition leaks on every question, so the seeded failure is real | `tests/test_harness.py::test_the_bypass_arm_leaks_on_every_question_which_is_the_seeded_defect` |
| A reformatted forbidden value is still detected, so the leak count is not a formatting artifact | `tests/test_harness.py::test_a_reformatted_forbidden_value_is_still_a_leak` (mutation-checked: compare only the exact stored string and it passes a de-punctuated leak) |
| The unpoliced condition differs from the baseline in policy alone, not in size | `tests/test_harness.py::test_the_unpoliced_arm_is_the_baseline_in_size_and_differs_only_in_policy` |
| Dilution varies the amount of irrelevant material and stays governed | `tests/test_harness.py::test_the_diluted_arm_is_much_larger_and_still_governed` |
| Staleness ages volatile fields only and leaves the contact roster current | `tests/test_harness.py::test_the_stale_arm_keeps_the_contact_roster_current` (mutation-checked: rewind the whole context and it fails) |
| The answer key orders by effective date, and the arrival-ordered system disagrees inside the gap | `tests/test_harness.py::test_the_key_orders_by_effective_date_and_the_arrival_system_does_not` (mutation-checked: order the key by arrival and it fails) |
| No question asks about an agreement that has not started as of the date asked | `tests/test_harness.py::test_no_arm_and_no_curve_budget_ships_an_agreement_that_has_not_started` |
| A contact's email follows them when they change employer, so no context contradicts itself | `tests/test_harness.py::test_a_contact_email_follows_them_to_their_new_employer` (mutation-checked) |
| The curve budget bounds the context and the subset is drawn equally from every stratum | `tests/test_harness.py::test_the_curve_subset_is_drawn_equally_from_every_stratum` |
| The report never prints a difference without an interval | `tests/test_harness.py::test_the_report_never_prints_a_difference_without_an_interval` |
| A verdict on the budget prediction keys on the direction of the difference, not on mere separation | `tests/test_harness.py::test_the_curve_verdict_requires_the_difference_to_point_the_right_way` |
| Results recorded by different code cannot be reported | `tests/test_harness.py::test_the_report_refuses_results_that_do_not_match_the_code` |
| A comparison that cannot be made does not print as a measured zero | `tests/test_harness.py::test_a_comparison_that_cannot_be_made_does_not_print_as_a_zero` |

The 34 figures in the tables above are rebuilt from the shipped results by
`scripts/check_readme_numbers.py`, which CI runs. What it does is a substring
test: it derives each figure and requires the exact string to appear somewhere
in this file. It cannot tell a right number in a wrong cell, and it does not
check the intervals, the paired statistics, or the token ratio, which are
verified by reading `results/*.jsonl` directly. It reports how many figures it
derived, so a version that quietly stopped checking half of them is visible
rather than clean.

The two cost figures are MODELED from token counts and published prices, not
read off a bill.

## Reproducing it

```
python3 scripts/preflight.py          # proves the harness, no model, no network
python3 -m pytest -q                  # the test suite
python3 scripts/report.py             # renders the shipped Claude results
python3 scripts/report.py results/sweep_openai.jsonl
python3 scripts/check_readme_numbers.py
```

The paid sweeps cost $5.47 and $3.46, plus a replicate. They are not needed to
check anything above except the model's answers themselves, which ship in
`results/`.

Results should not outlive the code that produced them. Each row carries a hash
of the question set and of the condition that rendered it, and the report
REFUSES to aggregate rows that disagree with the current code rather than
reporting numbers for questions it no longer asks.

Two caveats, and both are in the files rather than only here.

First, the curve. The sweep stamped every ARM row at write time and stamped
curve rows with the literal string `curve`. 360 of a run's 1,860 rows, 19.4%,
carrying no description of what produced them. A curve point is a condition too:
a change to the ranking, the truncation rule or `CHARS_PER_TOKEN` would have
left those rows aggregating under a label that no longer described them.
`assemble.curve_fingerprint` now stamps them, the report checks them the same
way it checks the arms, and the rows already on disk were backfilled by
`scripts/backfill_curve_fingerprint.py` and each marked
`arm_fingerprint_backfilled`. As below, that is an assertion that the code did
not change, not a measurement that it did not.

Second, the replicate. `results/sweep.jsonl` and `results/sweep_openai.jsonl`
had every ARM row stamped at write time. `results/sweep_replicate.jsonl`
predates the per-condition hash entirely, so 1,350 of its rows carry that hash
written AFTERWARD and say so in a field of their own,
`arm_fingerprint_backfilled`. That is an assertion rather than a measurement,
and it is why the report re-checks every one of them against the live code
before aggregating anything.

Its `perfect` rows are the exception in the other direction: all 150 were
stamped AT WRITE TIME and their hash matches what this code produces now, with
no backfill marker on any of them. That is the strongest provenance anything
in `results/` carries, so `perfect` sits inside the between-run comparison like
every other row.

The replicate ships because a second run of the same configuration is the only
thing here that measures run-to-run variance, and hiding it would be worse than
disclosing what is weak about it.

## What this does not measure

- Prose quality, helpfulness, tone, or synthesis. Exact match on facts only.
- Any real CRM. The world is synthetic so the key can be computed.
- Whether these effect sizes transfer to a different task. The ORDERING
  replicating across two vendors is the transferable part; the magnitudes are
  this task's.
- Cost per token between vendors. Pooled across all 1,860 matched cells GPT
  used 0.59 times the input tokens for the same prompts, so per-token
  comparisons between vendors are meaningless and only cost per task is real.
- REPEATED SAMPLING. There is ONE generation per cell, so the bootstrap captures
  question-to-question variance and NONE of the model's own. The Claude
  replicate measures how much that matters, up to 3.4 points, and the two small
  effects above are therefore reported as suggestive rather than established.
  Two runs bound the drift; they do not average it away.
- Robustness across worlds. There is one generated world, not many. Whether
  these effects survive a different one is a check this repository has not
  run.
- The curve rests on 60 questions per budget, not 150.

## Related repositories

Paired with
[connector-sync-guarantees](https://github.com/jkelly-dev1/connector-sync-guarantees),
which measures where an incremental sync silently loses data: records missed by
a modified-since watermark, corrections that land after the row they correct,
and what a restart replays. It answers what a pipeline MISSES. This one answers
whether missing it changes the answer, and its `stale` and `incomplete`
conditions are that repository's failure kinds carried downstream to a model.
Read that one first if you want the cause; read this one for the consequence.

The governance half connects to
[ai-data-boundary-proxy](https://github.com/jkelly-dev1/ai-data-boundary-proxy),
which enforces at the boundary what this repository measures the absence of.

## License

MIT. See `LICENSE`.
