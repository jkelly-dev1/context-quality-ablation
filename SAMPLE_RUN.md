# Sample run

Captured output. Nothing here is retyped, summarized or reformatted; each block
is the literal stdout of the command above it. Where anything had been altered
this header would say so, and nothing was.

Captured: 2026-09-27T17:05:13Z
Python: 3.13.7

The paid runs are not repeated here. Their results ship in `results/`, and the
README.md figures that `scripts/check_readme_numbers.py` lists are rebuilt from
them.
NONE of the commands below needs a network, a credential or a model, and CI
runs every one of them on every push and pull request to `main`.

## Proving the harness, with no model at all

```
$ python3 scripts/preflight.py
LAYER 1 -- oracle reader, no model, no network
  PASS  every arm produces distinct, non-empty context  0 empty, 0 collisions
  PASS  every prompt carries its own question  0 missing
  PASS  every prompt states its own as-of date  0 missing
  PASS  the floor arm carries no context and no answer in its prompt  0 prompts contain their own answer (113 of 238 answer values are strings long enough to search)
  PASS  the ceiling STATES every non-derived answer  0 unreachable
  PASS  the grader accepts a correct answer
  PASS  the grader rejects a near miss
  PASS  exactly one arm bypasses the field policy  leaking: ['unpoliced']
  PASS  the fingerprint changes when any answer key changes  1dce57cbec7ae645
  PASS  the curve renders and grows with its budget  0 budgets shrank
  PASS  the curve carries no forbidden field  0 leaking prompts
  PASS  the curve budget actually bounds the context
  PASS  every arm states the agreement its questions name, except the two that cannot  22 questions name one; 0 lost across 8 arms
  PASS  no question names an agreement by the world's internal id
  PASS  every non-derived answer key appears in a source system  0 unobtainable
  PASS  contract keys, derived ones too, are what a source showed  not shown: none; disclosed: none

16/16 checks passed
Harness is sound. A paid run measures the model, not the harness.
```

This is the gate. It runs before any paid sweep and exits non-zero if a check
fails. Its oracle answers only from the assembled context, which makes it the
right instrument for the questions a paid run must never be asked to discover:
whether the floor is a floor, whether the ceiling is reachable, whether the
grader accepts a right answer and rejects a near miss, and whether the field
policy fires on exactly one condition.

## The test suite

```
$ python3 -m pytest -q
........................................................................ [ 80%]
..................                                                       [100%]
90 passed in 48.21s
```

## The README's checked figures, rebuilt from the shipped evidence

```
$ python3 scripts/check_readme_numbers.py
74 figures derived from sweep.jsonl, sweep_openai.jsonl, sweep_replicate.jsonl
  30 condition-table cells compared BY POSITION (arm and run), plus 30 emphasis verdicts
  44 figures matched IN CONTEXT, with the sentence around them
74 found in README.md, 0 missing
3 of 3 figures found in PREDICTIONS.md and GITHUB_DESCRIPTION.txt
```

It prints the count whether or not anything is missing, so a version that
silently stopped deriving half the figures is visible rather than clean, and
that count is itself one of the figures. The 30 condition-table cells are
compared BY POSITION (a right number in a wrong cell fails), and each bold
cell is compared against whether that condition's interval actually excludes
zero. The rest are matched together with enough of their own sentence to make
the match mean something. Its last line runs the same check over the few
figures PREDICTIONS.md and GITHUB_DESCRIPTION.txt state, counted apart from the
README's.

## Breaking the code one piece at a time, and requiring a test to notice

```
$ python3 scripts/mutation_suite.py
48 mutations, each with its own named test

  M1 the incomplete arm drops a different number of fields than th caught
  M2 THE GENERAL GUARD: the same mutation, caught because the ship caught
  M3 the bootstrap returns an interval of zero width around the es caught
  M4 the per-arm staleness refusal is switched off while the repor caught
  M5 the prompt's first rule is rewritten to the opposite instruct caught
  M6 the same edit, caught by the fingerprint that now covers the  caught
  M7 questions go back to naming an agreement by the internal id,  caught
  M8 the default credential path stops being ignored by git, so `g caught
  M9 the figure checker keeps its own copy of the prices, so a pri caught
  M10 the batch rate is typed as a pair of literals again -- equal caught
  M11 a condition whose interval excludes zero loses its emphasis, caught
  M12 the count of derived figures is left at a stale value, which caught
  M13 the report's prompt gate is switched off, so results recorde caught
  M14 a failed pre-flight check stops refusing to certify -- the C caught
  M15 the leak detector compares only the exact stored string, so  caught
  M16 the stale arm rewinds the WHOLE context instead of the volat caught
  M17 the answer key orders by ARRIVAL instead of effective date,  caught
  M18 a contact's email stops following them to a new employer, so caught
  M30 the sibling that renders a sample before the first request s caught
  M29 the local endpoint URL stops being checked, so urllib will o caught
  M25 the question-set refusal is switched off, so results from a  caught
  M26 the arm table prints a difference with no interval beside it caught
  M27 the leak summary stops naming the arms that leak, so it can  caught
  M28 the question-set refusal fires on results that DO match, so  caught
  M23 the predicate the floor check searches with stops qualifying caught
  M24 the same edit, caught by the floor check itself going quiet  caught
  M21 the report's refusal stops setting a non-zero exit code, so  caught
  M22 the suite stops refusing an entry whose target text has left caught
  M20 the report stops saying which stamps were written after the  caught
  M19 an arm fingerprint over an EMPTY question set goes back to r caught
  M31 the output-leak figure is matched against a literal again, s caught
  M32 the curve verdict counts a budget separated on EITHER side a caught
  M33 the report's micro/paired gap goes back to a typed sentence  caught
  M34 the contract-key gate stops checking day counts, so a world- caught
  M35 the curve stops filtering CRM_B deals by start date, so unst caught
  M43 a contract key reads world truth even where no source showed caught
  M44 the sweep resumes into rows from another question set        caught
  M45 an organization's two agreements start on the same day, so a caught
  M46 a question stops naming which of two agreements it asks abou caught
  M47 a renewal key reads world truth instead of what a source sho caught
  M36 the prompt backfill overwrites a stamp written under another caught
  M37 the curve backfill overwrites a real hash of other code      caught
  M38 the leak detector stops treating slash, underscore and paren caught
  M39 pre-flight layer 2's floor-arm call leaves the try block, so caught
  M40 the unresolved arm ships every CRM_B deal of the company, st caught
  M41 the report prints the supporting verdict whatever the curve' caught
  M48 the sweep's call site ignores the stale-fingerprint result,  caught
  M49 the figure checker returns 0 when a figure is missing, so th caught

48 of 48 caught
```

The claims table's mutation-checked rows are re-run by this command. It
refuses to start if an entry's target text has left its file, if a named test
no longer collects, or if a named test does not pass on its own before anything
is patched, because each of those makes an entry score by something other than
the mutation it names.

## The Claude results

```
$ python3 scripts/report.py
1860 generations | 1500 arms + 360 curve | 150 questions | claude-sonnet-5 effort low

arm            field%  exact%  micro-d  paired-d           95% CI   in tok sig  leak   comp  look  reso  surv
none              0.0     0.0    -98.3     -97.7   [-99.7, -95.3]      500 *     0      0     0     0     0
perfect          96.2    94.0     -2.1      -2.0     [-5.3, +1.3]      564       0     88   100   100   100
resolved         98.3    97.3     +0.0      +0.0     [+0.0, +0.0]      792       0     96   100   100    97
unresolved       84.9    76.7    -13.4     -16.0    [-22.0, -9.7]    1,154 *     0     89    99    79    54
stale            93.7    90.0     -4.6      -7.0    [-12.0, -2.3]      791 *     0     97    99   100    68
incomplete       56.7    47.3    -41.6     -40.3   [-48.0, -33.0]      663 *     0     54    63    47    62
diluted          99.2    98.7     +0.8      +1.0     [-1.3, +3.3]    4,122       0     97   100   100   100
unpoliced        97.9    97.3     -0.4      -0.3     [-2.7, +2.0]      818     150     95   100   100    97
nostructure      99.2    98.7     +0.8      +1.0     [+0.0, +2.7]      812       0     97   100   100   100
governed         95.4    92.7     -2.9      -2.3     [-5.0, +0.3]      786       0     97    91   100    95

strata: computation, lookup, resolution, survivorship    * = interval excludes zero, so the difference is separated
micro-d = field% minus the baseline's field%, every FIELD weighted equally.
paired-d = mean over QUESTIONS of the per-question difference, which is what
the interval is computed on. Quote which one you mean; they are not the same
number and on this data they differ by up to 2.6 points.

TOKEN-BUDGET CURVE (ranked context cut at a budget):
  budget  field%  exact%   in tok  n
     150    68.9    61.7      633  60
     300    88.9    83.3      763  60
     600    93.3    90.0    1,055  60
    1200    93.3    90.0    1,662  60
    2400    92.2    91.7    2,890  60
    4800    92.2    88.3    5,395  60

  paired against the largest budget (4800):
    budget   150 vs 4800:  -29.2   [-41.7, -17.5] *
    budget   300 vs 4800:   -5.8    [-16.7, +5.0]  
    budget   600 vs 4800:   -0.8     [-9.2, +7.5]  
    budget  1200 vs 4800:   +2.5     [-2.5, +8.3]  
    budget  2400 vs 4800:   +2.5    [-5.0, +10.8]  

  peak at budget 600 and 1200 (93.3%); largest budget 4800 scores 92.2%
  NO BUDGET BEATS THE LARGEST BY MORE THAN NOISE, so the prediction that
  accuracy DECLINES with budget is NOT supported by this run. A star on a
  negative row means that budget is significantly WORSE than the largest, which
  is the opposite claim and is not evidence for it.
  The curve uses 60 questions drawn equally from the four strata, so its
  levels are not directly comparable with the arm table above, which uses 150.

GOVERNANCE:
  unpoliced     prompt  150/150  output    0  inferred    0
  arms with any prompt leak: unpoliced
  all other arms and budgets: 0 prompt leaks across 1710 generations
```

## The GPT results

```
$ python3 scripts/report.py results/sweep_openai.jsonl
1860 generations | 1500 arms + 360 curve | 150 questions | gpt-5.6-terra effort low

arm            field%  exact%  micro-d  paired-d           95% CI   in tok sig  leak   comp  look  reso  surv
none              0.0     0.0    -95.8     -94.7   [-97.7, -91.0]      213 *     0      0     0     0     0
perfect          96.2    94.0     +0.4      +1.3     [-1.7, +4.7]      260       0     88   100   100   100
resolved         95.8    93.3     +0.0      +0.0     [+0.0, +0.0]      419       0     87   100   100   100
unresolved       86.6    78.7     -9.2      -9.7    [-15.0, -4.0]      680 *     0     84    99    81    73
stale            92.9    88.7     -2.9      -4.3    [-10.0, +1.0]      418       0     93    99   100    70
incomplete       55.9    48.0    -39.9     -37.7   [-44.7, -30.3]      328 *     0     54    63    40    65
diluted          95.8    93.3     +0.0      +0.7     [-1.0, +3.0]    2,782       0     87   100   100   100
unpoliced        97.1    95.3     +1.3      +1.7     [-1.0, +4.7]      443     150     91   100   100   100
nostructure      96.6    94.7     +0.8      +2.0     [-1.3, +5.3]      427       0     89   100   100   100
governed         93.3    89.3     -2.5      -1.7     [-4.3, +1.3]      418       0     88    91   100   100

strata: computation, lookup, resolution, survivorship    * = interval excludes zero, so the difference is separated
micro-d = field% minus the baseline's field%, every FIELD weighted equally.
paired-d = mean over QUESTIONS of the per-question difference, which is what
the interval is computed on. Quote which one you mean; they are not the same
number and on this data they differ by up to 2.2 points.

TOKEN-BUDGET CURVE (ranked context cut at a budget):
  budget  field%  exact%   in tok  n
     150    68.9    61.7      301  60
     300    87.8    81.7      394  60
     600    92.2    88.3      589  60
    1200    97.8    96.7      985  60
    2400    98.9    98.3    1,739  60
    4800    97.8    96.7    3,513  60

  paired against the largest budget (4800):
    budget   150 vs 4800:  -35.0   [-46.7, -23.3] *
    budget   300 vs 4800:  -13.3    [-23.3, -4.2] *
    budget   600 vs 4800:   -8.3    [-15.0, -1.7] *
    budget  1200 vs 4800:   +0.0     [-6.7, +6.7]  
    budget  2400 vs 4800:   +1.7     [-3.3, +6.7]  

  peak at budget 2400 (98.9%); largest budget 4800 scores 97.8%
  NO BUDGET BEATS THE LARGEST BY MORE THAN NOISE, so the prediction that
  accuracy DECLINES with budget is NOT supported by this run. A star on a
  negative row means that budget is significantly WORSE than the largest, which
  is the opposite claim and is not evidence for it.
  The curve uses 60 questions drawn equally from the four strata, so its
  levels are not directly comparable with the arm table above, which uses 150.

GOVERNANCE:
  unpoliced     prompt  150/150  output    0  inferred    0
  arms with any prompt leak: unpoliced
  all other arms and budgets: 0 prompt leaks across 1710 generations
```

## Reading these together

Two effects separate on every run, by far more than the between-run drift
measured by the replicate, and replicate across both vendors: incompleteness
and unresolved entities. Staleness separates on the Claude run above and on
its replicate but not on the GPT run, so README.md reports it as a Claude
result. Governance separates on neither run above.

The `unresolved` row measures entity resolution with no identifier artifact
in it. The 22 questions that must pick one of an organization's two
agreements name it by its start date, which both source systems carry, and
not by the world's internal id, which neither does. `scripts/preflight.py`
gates that property in the first block above: "every arm states the agreement
its questions name, except the two that cannot" and "no question names an
agreement by the world's internal id". README.md gives the figures this row
replaced.

Dilution, prose rendering and skipping the field policy (`unpoliced`) do not
separate on either run above. The policy bypass is the security result: 150
leaked prompts per run, with an accuracy difference that lands on both sides
of the baseline across runs, which is what no effect looks like.

The token-budget prediction is NOT SUPPORTED on either run, and the report says so in
its own words. It does not print a peak and leave a reader to infer
confirmation. The only budgets that separate from the largest are the small
ones, and they separate downward, which is the opposite claim. Not supported is
not the same as refuted and `PREDICTIONS.md` says why; all three documents use
the weaker word because it is the one this design can support.
