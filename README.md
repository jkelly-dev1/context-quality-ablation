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
the runs did not support is still here, stated as strongly as it was made.

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
| no context | **0.0** | **0.0** | **0.0** | the floor |
| unpoliced | **99.6** | 98.7 | 97.1 | the field policy |
| diluted | 98.7 | 99.2 | 95.8 | selectivity, not content |
| nostructure | 98.3 | 99.2 | 97.5 | key/value form, same facts |
| resolved (baseline) | 97.5 | 98.7 | 97.9 | nothing |
| perfect | 97.1 | 97.5 | 97.1 | everything irrelevant |
| stale | **94.1** | **93.3** | **92.0** | 30 days on volatile fields |
| governed | **93.3** | **95.4** | **94.5** | precision, via a privacy transform |
| unresolved | **77.7** | **81.1** | **84.0** | entity resolution |
| incomplete | **57.6** | **57.1** | **56.3** | 4 of the 9 available fields, 44.4 percent |

A bold cell means one thing and is checked: that condition's 95 percent paired
interval EXCLUDES ZERO in that column's own run, which is the same set of rows
`scripts/report.py` marks with `*`. It is a claim about separation from the
baseline within a single run. It is not a claim about the size of the effect,
and it is not a claim that the separation replicates: the `unpoliced` cell is
bold on Claude and not on the replicate of the identical configuration, as the
section below explains. `scripts/check_readme_numbers.py` derives the bold set
from the shipped rows and fails if this table disagrees with it, so the
emphasis cannot drift back into decoration.

## The most important number here is not in that table

The same configuration run twice moves by up to 3.4 POINTS, mean 1.05 across
the 10 conditions. There is ONE generation per cell, so the bootstrap resamples
questions and captures NONE of the model's own run-to-run variance. The
intervals in `scripts/report.py` therefore understate the true uncertainty, and
this replicate is how much by.

Measured against that, the effects sort into two groups and only one of them
is safe to call established. EVERY FIGURE IN THIS SECTION IS A MICRO-d: field%
minus the baseline's field%, every FIELD weighted equally. The intervals
referred to are computed on the PAIRED-d, which weights every QUESTION equally
and is a different number; `scripts/report.py` prints both side by side and
its footer says to quote which one you mean, so this section does.

  ROBUST. Incompleteness (micro-d -39.9 and -41.6 across the two Claude runs)
  and unresolved entities (micro-d -19.7 and -17.6). Both are an order of
  magnitude larger than the drift, and both replicate across the two vendors as
  well. READ THE LIMITATION ON THE UNRESOLVED ARM BELOW BEFORE QUOTING ITS
  MAGNITUDE: about half of it is an identifier artifact, and the corrected
  figure is roughly -11.

  Not established. Governance (micro-d -4.2 and -3.4; paired-d -3.7 and -3.3)
  and staleness are the same size as the between-run movement of the baseline
  itself. Their PAIRED intervals exclude zero WITHIN a run and that is not
  enough. Treat them as suggestive.

  No effect. Dilution, prose rendering and the policy bypass move in both
  directions across runs.

The ordering of the two robust effects replicates across both vendors, which is
the transferable claim: incompleteness costs more than unresolved entities, and
both cost far more than presentation. That is a property of context rather than
of one model, and a single-vendor single-run study could not have separated the
two.

## The unresolved arm changes two things, and one of them is an artifact

Every other section of this document rests on one rule, stated at the top of
`cqa/assemble.py`: ONE ARM CHANGES ONE THING. The `unresolved` arm breaks it,
and about half of its published effect is the breakage rather than the
property it is named for.

22 of the 150 question texts name an agreement by the identifier the RESOLVED
view gives it ("agreement CTR014 at Northwind Health Partners"), because an
organization holding two contracts makes "the renewal date" ambiguous and an
ambiguous question measures nothing. CTRnnn is INTERNAL TO THE WORLD. CRM_A
renames it to AGR-nnn, CRM_B gives its deals numeric ids of their own, and the
unresolved arm renders raw source rows. So in all 22 of those contexts the
literal identifier the question names is ABSENT.

The model behaves correctly and the measurement does not. On those 22 questions
`unresolved` scores 14.3 (Claude), 21.4 (replicate) and 39.3 (GPT) percent
against a baseline of 100.0 on all three, and on the Claude run 21 of the 24
failing fields are NULLS: the model looked for the agreement it was asked
about, did not find it, and declined to answer instead of guessing. That is a
failure of IDENTIFICATION, not of entity resolution.

Excluding those 22 questions, the arm's micro-d against the baseline is
-11.0 (Claude), -9.5 (replicate) and -7.6 (GPT), against the -19.7, -17.6 and
-13.9 the table above reports for all 150. Every one of those figures is
derived from the shipped rows by `scripts/check_readme_numbers.py`.

WHAT SURVIVES, AND IT IS MOST OF THE CLAIM. The corrected effect is still
three times the 3.4-point run-to-run drift, still separates on all three runs,
still replicates across two vendors, and is still ordered behind
incompleteness, which is the transferable claim this repository makes. What
does not survive is the magnitude: quote roughly -11 and not -19.7 for the cost
of losing entity resolution, and treat the table's `unresolved` row as an upper
bound.

WHY IT IS DISCLOSED AND NOT CHANGED. Removing it means changing the question
text, and the question text is inside `questions.fingerprint`, which every one
of the 5,580 shipped generations is stamped with. Changing it makes the report
refuse every row in `results/`, correctly, and the only way back is to pay for
three more runs. Disclosure plus a gate costs a reader one paragraph; the
alternative costs the evidence.

THE GATE. `scripts/preflight.py` checks that every arm states the identifiers
its questions name, exempting exactly three that cannot: `none`, which renders
nothing; `incomplete`, which drops fields as its whole mechanism; and
`unresolved`, which is this confound and is named in the exemption. A fourth
arm acquiring the same flaw fails the pre-flight. It also checks that the
unresolved arm loses EVERY named identifier rather than some, because the
correction above excludes all 22 and that arithmetic is only right if the loss
is total.

## The prediction that was not supported

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
| Results recorded under a different PROMPT cannot be reported either | `tests/test_harness.py::test_the_report_refuses_results_recorded_under_a_different_prompt` (mutation-checked: switch the gate off with `if False:` and this fails; rewriting the first rule of `prompt.SYSTEM` fails the shipped-results guard below) |
| Results recorded by a different ARM ASSEMBLY cannot be reported, and the arm is named | `tests/test_harness.py::test_the_report_refuses_an_arm_whose_assembly_no_longer_matches` (mutation-checked: `if stale_arms:` to `if False:` and it fails) |
| The shipped results still describe the code that renders them | `tests/test_harness.py::test_the_shipped_results_still_describe_the_code_that_renders_them` (mutation-checked: any change to an arm's assembly fails it) |
| The interval is computed from the data, not printed around the estimate | `tests/test_harness.py::test_the_interval_is_computed_and_not_merely_printed` (mutation-checked: an interval of zero width fails it) |
| The incomplete condition drops the number of fields it advertises, on every question | `tests/test_harness.py::test_the_incomplete_arm_drops_the_count_it_advertises_on_every_question` |
| The unresolved condition's identifier confound is exactly what this document discloses | `tests/test_harness.py::test_the_unresolved_arms_identifier_confound_is_exactly_as_disclosed` (mutation-checked in both directions) |
| One price table, and every consumer reads it | `tests/test_harness.py::test_one_price_table_and_every_consumer_reads_it` (mutation-checked: a second copy of the price fails it) |
| The default credential path is ignored by git | `tests/test_harness.py::test_the_default_credential_path_is_ignored_by_git` (mutation-checked: drop `.env` from `.gitignore` and it fails) |
| A fingerprint over no questions is refused rather than returned | `tests/test_harness.py::test_a_fingerprint_over_no_questions_is_refused_rather_than_returned` |
| Each gate returns the verdict CI acts on | `tests/test_harness.py::test_the_figure_checker_main_returns_a_verdict_ci_can_act_on`, `tests/test_harness.py::test_the_preflight_main_returns_a_verdict_ci_can_act_on` (mutation-checked: flip either non-zero return to 0 and they fail) |

Every parenthetical above names a mutation that is recorded rather than
asserted, AND THAT YOU CAN RE-RUN. `scripts/mutation_suite.py` holds all 30
entries and applies them one at a time: it patches the real file, runs the
single test that is supposed to catch the edit, requires that test to go red,
and puts the file back. CI runs it on every push.

It refuses to start instead of reporting a green sweep it did not earn: if an
entry's target text has left its file, if a named test no longer collects, or
if a named test does not pass ON ITS OWN before anything is patched, because
each of those makes an entry score by something other than the mutation. An
interrupted run is repairable: the original is copied outside the tree and its
hash recorded before the patch is written, the catchable signals restore and
re-raise, and the next run puts back what a kill left behind.

The 63 figures in this document are rebuilt from the shipped results by
`scripts/check_readme_numbers.py`, which CI runs, and it checks them three
ways. The 30 condition-table cells are compared BY POSITION: the cell for an
arm and a run is compared against that arm's accuracy in that run, so a right
number in a wrong cell fails. Each bold cell is compared against whether that
condition's interval actually excludes zero, through the same function
`scripts/report.py` marks `*` with. Every other figure is matched together with
enough of its own sentence to make the match mean something: a bare string is
not evidence when the value is short or common, because `0`, `150` and `1860`
appear in any plausible README and a figure that cannot fail must not be
counted among the ones that can.

What it still does not check: the intervals themselves, the paired statistics
and the token ratio, which are verified by reading `results/*.jsonl` directly.
It reports how many figures it derived, and that count is one of the figures,
so a version that quietly stopped deriving half of them cannot leave this
sentence looking clean.

The two cost figures are MODELED from token counts and published prices, not
read off a bill.

## Reproducing it

```
python3 scripts/preflight.py          # proves the harness, no model, no network
python3 -m pytest -q                  # the test suite
python3 scripts/report.py             # renders the shipped Claude results
python3 scripts/report.py results/sweep_openai.jsonl
python3 scripts/check_readme_numbers.py
python3 scripts/mutation_suite.py     # breaks the code and requires a test to notice
```

CI runs every one of them on every push.

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

Second, the replicate, AND IT IS NOT ONE RUN OF ONE CONFIGURATION.
`results/sweep.jsonl` and `results/sweep_openai.jsonl` had every ARM row
stamped at write time. `results/sweep_replicate.jsonl` is a splice of two, and
the rows say so:

- 150 `perfect` rows carry a hash written AT WRITE TIME, with no backfill
  marker, and it matches what this code produces now. They were therefore
  produced by code that already had the per-condition hash.
- the other 1,350 arm rows, and all 360 curve rows, carry
  `arm_fingerprint_backfilled` and were stamped AFTERWARD. They were produced
  by code that did not have it.

"Predates the per-condition hash entirely" and "its `perfect` rows were
stamped at write time" CANNOT BOTH BE TRUE OF ONE RUN, and the rows agree with
the second: the file is one configuration measured in two sittings, under two
revisions of this code. A backfilled hash is an ASSERTION that the assembly
did not change between them, not a measurement that it did not. The report
therefore re-checks every row against the live code before aggregating
anything, and a reader who does not accept the assertion can drop the 1,710
marked rows and lose the comparison instead of being misled by it.

No row in this file carries a `provider` field; the other two runs carry one on
every row. Nothing reads it (`report.py` and `check_readme_numbers.py` both
key on the FILE), so it costs nothing today; it is one more difference between
this file and the two runs it is compared against.

The replicate ships because a second run of the same configuration is the only
thing here that measures run-to-run variance, and hiding it would be worse than
disclosing what is weak about it.

Third, the PROMPT hash, which is the newest of the three stamps and the one
every shipped row carries as an assertion. Model, prompt and question set are
what this experiment holds constant while context varies; the question set and
the condition were hashed onto every row when it was written and the prompt was
not, so `scripts/report.py` now refuses on it too and the 5,580 rows already on
disk were stamped afterwards by `scripts/backfill_prompt_fingerprint.py`.

What that asserts is narrow: everything the template INTERPOLATES (the
question, its as-of date, its answer schema) is already inside
`questions_fingerprint`, which those rows carry from write time. What is
asserted is the wording of the template itself.

AND THE ROWS CANNOT CHECK IT, as a measurement shows. Each row records the
vendor's own input-token count, so input tokens were regressed on today's
rendered characters; residual spread is 15.9 tokens on the Claude floor arm and
28.1 across its arms. Re-rendering with 40 more characters in the system prompt
leaves that spread at exactly 1.00x, because a constant edit is absorbed by the
intercept, and re-indenting the schema block leaves it between 0.96x and 1.00x,
because a per-question edit is smaller than the tokenizer noise it would have
to clear. So the report prints how many rows carry an after-the-fact hash,
above every table, and calls it an assertion. Only a re-run replaces it with a
measurement.

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
