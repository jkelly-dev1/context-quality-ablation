# context-quality-ablation

[![CI](https://github.com/jkelly-dev1/context-quality-ablation/actions/workflows/ci.yml/badge.svg)](https://github.com/jkelly-dev1/context-quality-ablation/actions/workflows/ci.yml)

Every vendor asserts that the data foundation determines what an LLM answers.
This measures it: one question set, ten context conditions, two model vendors,
and an answer key that is computed rather than judged.

The claim in one line: the properties of context that matter are not the ones
the marketing talks about, and the one that matters most for security is
invisible to every quality metric you have.

A learning project. The figures from the current runs are derived from the
shipped results files by a checker that CI runs, the few quoted from the runs
they replaced are labeled as those runs' figures, and the predictions were
fixed before the runs. The one the runs did not support is still here, stated
as strongly as it was made.

What you need to run everything except the paid sweeps: `python3`, plus
`pytest` for the test suite and the mutation suite. No container, no database,
no service, no network. The pre-flight finishes in a few seconds.

## The headline finding

Bypassing a field-level privacy policy leaked on every single prompt and left
no trace a quality metric could find.

The `unpoliced` condition is the production baseline with one thing removed: the
policy that strips a value which may never enter a prompt. Nothing else differs:
strip the forbidden field's lines from it and the two contexts are
byte-identical, which is what the test asserts rather than a size band. That
makes it 26 tokens larger on the Claude run, 3.3 percent, and 24 tokens larger
on the GPT run, 5.8 percent. It leaked into 150 of 150 prompts, on both vendors
and in both Claude runs.

What its accuracy did is not a clean null. Across two Claude runs of the
identical configuration it scored 97.9 and 98.3 percent against baselines of
98.3 and 98.3. So it landed below the baseline in the first run and level with
it in the replicate. On GPT it was 97.1 against 95.8, above it.

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
| unpoliced | 97.9 | 98.3 | 97.1 | the field policy |
| diluted | 99.2 | 99.2 | 95.8 | selectivity, not content |
| nostructure | 99.2 | 99.6 | 96.6 | key/value form, same facts |
| resolved (baseline) | 98.3 | 98.3 | 95.8 | nothing |
| perfect | 96.2 | 97.1 | 96.2 | everything irrelevant |
| stale | **93.7** | **93.7** | 92.9 | 30 days on volatile fields |
| governed | 95.4 | 95.8 | 93.3 | precision, via a privacy transform |
| unresolved | **84.9** | **84.0** | **86.6** | entity resolution |
| incomplete | **56.7** | **56.3** | **55.9** | 4 of the 9 available fields, 44.4 percent |

A bold cell means one thing and is checked: that condition's 95 percent paired
interval EXCLUDES ZERO in that column's own run, which is the same set of rows
`scripts/report.py` marks with `*`. It is a claim about separation from the
baseline within a single run. It is not a claim about the size of the effect,
and it is not a claim that the separation replicates across vendors: the
`stale` cell is bold on both Claude runs and not on GPT.
`scripts/check_readme_numbers.py` derives the bold set from the shipped rows and
fails if this table disagrees with it, so the emphasis cannot drift back into decoration.

These runs use the current question set, answer key and token-budget curve
(see the section on the unresolved arm and Limits). The runs they replace are
in git history.

## The most important number here is not in that table

The same configuration run twice moves by up to 0.8 POINTS, mean 0.34 across
the 10 conditions. There is ONE generation per cell, so the bootstrap resamples
questions and captures NONE of the model's own run-to-run variance. The
intervals in `scripts/report.py` therefore understate the true uncertainty, and
this replicate is how much by. The replaced runs moved by up to 3.4 points;
one pair of runs is one measurement of the drift, not a bound on it.

Measured against that, the effects sort into three groups. EVERY FIGURE IN
THIS SECTION IS A MICRO-d: field% minus the baseline's field%, every FIELD
weighted equally. The intervals referred to are computed on the PAIRED-d,
which weights every QUESTION equally and is a different number;
`scripts/report.py` prints both side by side and its footer says to quote which
one you mean, so this section does.

  ESTABLISHED. Incompleteness (micro-d -41.6 and -42.0 across the two Claude
  runs) and unresolved entities (micro-d -13.4 and -14.3). Both are more than
  ten times the drift, both separate on all three runs, and both replicate
  across the two vendors.

  ESTABLISHED ON ONE VENDOR. Staleness (micro-d -4.6 and -4.6; paired-d -7.0
  and -7.3) separates on both Claude runs and moved 0.0 points between them,
  but its interval includes zero on GPT. Quote it as a Claude result.

  Not established. Governance (micro-d -2.9 and -2.5; paired-d -2.3 and -2.3)
  separates in no run. Dilution and prose rendering sit at or above the
  baseline in every run and separate in no run; the policy bypass lands on
  both sides of it across runs.

The ordering of the two established effects replicates across both vendors,
which is the transferable claim: incompleteness costs more than unresolved
entities, and both cost far more than presentation. That is a property of
context rather than of one model, and a single-vendor single-run study could
not have separated the two.

## The unresolved arm, measured without the identifier artifact

Every section of this document rests on one rule, stated at the top of
`cqa/assemble.py`: ONE ARM CHANGES ONE THING. The `unresolved` arm is where
that rule is easiest to break, through the way a question names an agreement.

Of the 150 question texts, 22 name one of an organization's two agreements,
because two contracts make "the renewal date" ambiguous and an ambiguous
question measures nothing. They name it by its start date ("the agreement
that started on 2026-01-01 at Northwind Health Partners"), which both source
systems carry. The world's internal id, CTRnnn, is carried by neither, and
the unresolved arm renders raw source rows, so a question naming an agreement
by that id would leave the arm unable to find it, and a correct null answer
would score as a failure to resolve entities. The pre-flight checks that
every arm except the floor and `incomplete` states the named date, and that
no question names an internal id.

On this question set the arm's micro-d is -13.4 (Claude), -14.3 (replicate)
and -9.2 (GPT). The replaced runs, whose questions named agreements by
internal id, gave -19.7, -17.6 and -13.9, which puts the identifier's share of
their effect at about a third (Claude), a fifth (replicate) and a third (GPT);
part of each difference is run-to-run drift. On the questions that name an
agreement the arm scores 71.4 against 96.4 (Claude), 64.3 against 92.9
(replicate) and 67.9 against 82.1 (GPT). The gap that remains is on questions
it can identify:
they are the organizations holding two contracts, where an unmerged view
shows each system's rows for both.

## The prediction that was not supported

Recorded before any run: that accuracy would rise, flatten, and then DECLINE
as the context budget grew, because answer-bearing facts get diluted.

IT IS NOT SUPPORTED, on either vendor or either run. The only budgets that
separate from the largest are the small ones, and they separate DOWNWARD: the
opposite claim, and not evidence for it.

Claude peaks at 600 and 1,200 tokens (tied) and drifts down slightly after;
GPT climbs to 2,400 and dips slightly at 4,800. No interval separates in the direction the
prediction needs. The honest statement is that more context stops helping and
this design cannot show it starting to hurt.

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

What this gives up: it measures factual accuracy on retrievable facts. It says
nothing about prose quality, helpfulness, or synthesis. A narrow claim that is
exactly true beats a broad one resting on an uncalibrated judge.

## Claims backed by tests

| claim | test |
|---|---|
| A question with no context carries no answer in its prompt | `tests/test_harness.py::test_the_floor_arm_carries_no_context_and_no_answer_in_its_prompt` |
| The ceiling condition states every non-derived answer it is asked for | `tests/test_harness.py::test_the_perfect_arm_contains_every_answer_value_it_can_state` |
| Every contract answer key, derived keys included, is what a source system showed on the date asked | `tests/test_harness.py::test_every_contract_key_is_what_a_source_showed` (mutation-checked: let a key read world truth that no source showed and it fails) |
| The baseline carries a supporting field for every answer it is asked for | `tests/test_harness.py::test_every_answer_key_is_supported_by_the_baseline_context_too` |
| The forbidden field reaches exactly one condition and no other | `tests/test_harness.py::test_the_forbidden_field_never_reaches_any_arm_except_the_bypass` |
| That condition leaks on every question, so the seeded failure is real | `tests/test_harness.py::test_the_bypass_arm_leaks_on_every_question_which_is_the_seeded_defect` |
| A reformatted forbidden value is still detected, so the leak count is not a formatting artifact | `tests/test_harness.py::test_a_reformatted_forbidden_value_is_still_a_leak` (mutation-checked: compare only the exact stored string and it passes a de-punctuated leak) |
| The unpoliced condition differs from the baseline in policy alone, not in size | `tests/test_harness.py::test_the_unpoliced_arm_is_the_baseline_in_size_and_differs_only_in_policy` |
| Dilution varies the amount of irrelevant material and stays governed | `tests/test_harness.py::test_the_diluted_arm_is_much_larger_and_still_governed` |
| Staleness ages volatile fields only and leaves the contact roster current | `tests/test_harness.py::test_the_stale_arm_keeps_the_contact_roster_current` (mutation-checked: rewind the whole context and it fails) |
| The answer key orders by effective date, and the arrival-ordered system disagrees inside the gap | `tests/test_harness.py::test_the_key_orders_by_effective_date_and_the_arrival_system_does_not` (mutation-checked: order the key by arrival and it fails) |
| No condition ships an agreement or deal that has not started as of the date asked | `tests/test_harness.py::test_no_arm_ships_an_agreement_or_deal_that_has_not_started` |
| The curve ships no unstarted agreement and no unstarted deal | `tests/test_harness.py::test_the_curve_ships_no_unstarted_agreement_and_no_unstarted_deal` (mutation-checked: stop filtering CRM_B deals by start date and it fails) |
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
| Every arm that renders agreements can identify the one a question names, and no question names one by the world's internal id | `tests/test_harness.py::test_every_arm_that_renders_agreements_can_identify_the_one_asked_about` (mutation-checked: name agreements by the internal id again and it fails), `::test_no_organization_holds_two_agreements_starting_the_same_day` |
| One price table, and every consumer reads it | `tests/test_harness.py::test_one_price_table_and_every_consumer_reads_it` (mutation-checked: a second copy of the price fails it) |
| The default credential path is ignored by git | `tests/test_harness.py::test_the_default_credential_path_is_ignored_by_git` (mutation-checked: drop `.env` from `.gitignore` and it fails) |
| A fingerprint over no questions is refused rather than returned | `tests/test_harness.py::test_a_fingerprint_over_no_questions_is_refused_rather_than_returned` |
| Each gate returns the verdict CI acts on | `tests/test_harness.py::test_the_figure_checker_main_returns_a_verdict_ci_can_act_on`, `tests/test_harness.py::test_the_preflight_main_returns_a_verdict_ci_can_act_on` (mutation-checked: flip either non-zero return to 0 and they fail) |

Every parenthetical above names a mutation that is recorded rather than
asserted, AND THAT YOU CAN RE-RUN. `scripts/mutation_suite.py` holds all 48
entries and applies them one at a time: it patches the real file, runs the
single test that is supposed to catch the edit, requires that test to go red,
and puts the file back. CI runs it on every push and pull request to `main`.

It refuses to start instead of reporting a green sweep it did not earn: if an
entry's target text has left its file, if a named test no longer collects, or
if a named test does not pass ON ITS OWN before anything is patched, because
each of those makes an entry score by something other than the mutation. An
interrupted run is repairable: the original is copied to
`.mutation_suite_pristine/` at the repository root, which git ignores, and its
hash recorded before the patch is written, the catchable signals restore and
re-raise, and the next run puts back what a kill left behind.

The checker, `scripts/check_readme_numbers.py`, rebuilds 74 figures in this
document from the shipped results, counting a figure that several runs derive
identically once. CI runs it, and it checks them three ways. The 30 condition-table cells are compared BY POSITION: the cell for an
arm and a run is compared against that arm's accuracy in that run, so a right
number in a wrong cell fails. Each bold cell is compared against whether that
condition's interval actually excludes zero, through the same function
`scripts/report.py` marks `*` with. Every other figure is matched together with
enough of its own sentence to make the match mean something: a bare string is
not evidence when the value is short or common, because `0`, `150` and `1860`
appear in any plausible README and a figure that cannot fail must not be
counted among the ones that can.

What it still does not check: the intervals themselves and the paired
statistics, which are verified by reading `results/*.jsonl` directly. The
replaced runs' figures are held in it as constants, so they cannot be restated
differently here, but their rows do not ship and nothing re-derives them.
It reports how many figures it derived, and that count is one of the figures,
so a version that silently stopped deriving half of them cannot leave this
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

CI runs every one of them on every push and pull request to `main`.

The paid sweeps cost $5.46 and $3.45, plus a replicate at the Claude price. They are not needed to
check anything above except the model's answers themselves, which ship in
`results/`.

Results should not outlive the code that produced them. Each row carries a hash
of the question set and of the condition that rendered it, and the report
REFUSES to aggregate rows that disagree with the current code rather than
reporting numbers for questions it no longer asks.

Every stamp is written with its row. Each of the 5,580 shipped generations
carries the question-set hash, the hash of the condition that rendered it (the
arm, or the budget for a curve row; those are 360 of a run's 1,860 rows, 19.4%)
and the hash of the prompt, all written by `scripts/sweep.py` at the moment
the row was recorded: 0 of the 5,580 generations carries a stamp written
after its row.
The runs these replaced were a splice of two sittings with backfilled stamps,
and they remain in git history. A sweep refuses to resume into a file holding
rows for another question set, because resuming skips every (question,
condition) already on file and would leave old rows standing under new
questions.

## Limits

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
  replicate measures how much that matters, up to 0.8 points on these runs and
  3.4 on the ones they replaced. Two runs bound the drift; they do not average
  it away.
- Robustness across worlds. There is one generated world, not many. Whether
  these effects survive a different one is a check this repository has not
  run.
- The curve rests on 60 questions per budget, not 150. Its ranked facts
  filter both systems' agreements by start date: 0 of the 360 curve contexts,
  on 0 of the 60 curve questions, carry an agreement or deal that had not
  started on the date asked.
- Every answer key is what a source system showed on the date asked, which is
  not always the world's own value: a correction can take effect before the
  date asked and reach the sources after it. C009 is the one question where
  they differ: the world's corrected renewal is 339 days away, and both
  systems still showed 309, which is its key. The pre-flight fails if any key
  reads a value no source showed.

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
