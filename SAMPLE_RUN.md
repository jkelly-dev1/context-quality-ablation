# Sample run

Captured output. Nothing here is retyped, summarized or reformatted; each block
is the literal stdout of the command above it. Where anything had been altered
this header would say so, and nothing was.

Captured: 2026-09-19T06:17:23Z
Python: 3.13.7

The paid runs are not repeated here. Their results ship in `results/` and every
figure in README.md is rebuilt from them by `scripts/check_readme_numbers.py`.
NONE of the commands below needs a network, a credential or a model, and CI
runs every one of them on every push.

## Proving the harness, with no model at all

```
$ python3 scripts/preflight.py
LAYER 1 -- oracle reader, no model, no network
  PASS  every arm produces distinct, non-empty context  0 empty, 0 collisions
  PASS  every prompt carries its own question  0 missing
  PASS  every prompt states its own as-of date  0 missing
  PASS  the floor arm carries no context and no answer in its prompt  0 prompts contain their own answer
  PASS  the ceiling STATES every non-derived answer  0 unreachable
  PASS  the grader accepts a correct answer
  PASS  the grader rejects a near miss
  PASS  exactly one arm bypasses the field policy  leaking: ['unpoliced']
  PASS  the fingerprint changes when any answer key changes  d16da8a7f36f7564
  PASS  the curve renders and grows with its budget  0 budgets shrank
  PASS  the curve carries no forbidden field  0 leaking prompts
  PASS  the curve budget actually bounds the context
  PASS  every arm states the identifiers its questions name, except the three that cannot  0 lost across 7 arms
  PASS  the unresolved arm loses every named identifier, not some  22 questions name one, 0 still identifiable
  PASS  every answer key is obtainable from a source system  0 unobtainable

15/15 checks passed
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
........................................................................ [ 90%]
........                                                                 [100%]
80 passed in 33.33s
```

## Every README figure, rebuilt from the shipped evidence

```
$ python3 scripts/check_readme_numbers.py
63 figures derived from sweep.jsonl, sweep_openai.jsonl, sweep_replicate.jsonl
  30 condition-table cells compared BY POSITION (arm and run), plus 30 emphasis verdicts
  33 figures matched IN CONTEXT, with the sentence around them
63 found in README.md, 0 missing
```

It prints the count whether or not anything is missing, so a version that
quietly stopped deriving half the figures is visible rather than clean, and
that count is itself one of the figures. The 30 condition-table cells are
compared BY POSITION (a right number in a wrong cell fails), and each bold
cell is compared against whether that condition's interval actually excludes
zero. The rest are matched together with enough of their own sentence to make
the match mean something.

## Breaking the code one piece at a time, and requiring a test to notice

```
$ python3 scripts/mutation_suite.py
30 mutations, each with its own named test

  M1 the incomplete arm drops a different number of fields than th caught
  M2 THE GENERAL GUARD: the same mutation, caught because the ship caught
  M3 the bootstrap returns an interval of zero width around the es caught
  M4 the per-arm staleness refusal is switched off while the repor caught
  M5 the prompt's first rule is rewritten to the opposite instruct caught
  M6 the same edit, caught by the fingerprint that now covers the  caught
  M7 the unresolved arm starts stating the internal id, which REMO caught
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

30 of 30 caught
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
PROVENANCE: arm 360, prompt 1,860 of 1,860 rows carry a hash written AFTER the run
            (an assertion that the code did not change, not a measurement that it did not);
            the rest were stamped at write time.

arm            field%  exact%  micro-d  paired-d           95% CI   in tok sig  leak   comp  look  reso  surv
none              0.0     0.0    -97.5     -96.7   [-99.0, -93.7]      499 *     0      0     0     0     0
perfect          97.1    95.3     -0.4      +0.3     [-2.3, +3.3]      563       0     91   100   100   100
resolved         97.5    96.0     +0.0      +0.0     [+0.0, +0.0]      791       0     95   100   100    95
unresolved       77.7    68.7    -19.7     -23.7   [-31.3, -16.3]    1,153 *     0     84    86    81    43
stale            94.1    90.7     -3.4      -5.3    [-10.7, -0.3]      790 *     0     97    99   100    70
incomplete       57.6    48.7    -39.9     -38.3   [-46.0, -30.7]      662 *     0     55    63    47    65
diluted          98.7    98.0     +1.3      +1.7     [-0.7, +4.3]    4,121       0     96   100   100   100
unpoliced        99.6    99.3     +2.1      +3.0     [+0.7, +6.0]      817 *   150     99   100   100   100
nostructure      98.3    98.0     +0.8      +1.3     [-1.0, +4.0]      811       0     97    97   100   100
governed         93.3    90.0     -4.2      -3.7     [-6.7, -1.0]      785 *     0     93    88   100    95

strata: computation, lookup, resolution, survivorship    * = interval excludes zero, so the difference is separated
micro-d = field% minus the baseline's field%, every FIELD weighted equally.
paired-d = mean over QUESTIONS of the per-question difference, which is what
the interval is computed on. Quote which one you mean; they are not the same
number and on this data they differ by up to about seven points.

TOKEN-BUDGET CURVE (ranked context cut at a budget):
  budget  field%  exact%   in tok  n
     150    68.9    61.7      632  60
     300    87.8    81.7      762  60
     600    93.3    91.7    1,055  60
    1200    93.3    91.7    1,659  60
    2400    92.2    88.3    2,889  60
    4800    92.2    88.3    5,395  60

  paired against the largest budget (4800):
    budget   150 vs 4800:  -29.2   [-42.5, -17.5] *
    budget   300 vs 4800:   -7.5    [-18.3, +3.3]  
    budget   600 vs 4800:   +0.8     [-4.2, +6.7]  
    budget  1200 vs 4800:   +2.5    [-4.2, +10.0]  
    budget  2400 vs 4800:   +1.7     [-5.0, +8.3]  

  peak at budget 600 (93.3%); largest budget 4800 scores 92.2%
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
PROVENANCE: arm 360, prompt 1,860 of 1,860 rows carry a hash written AFTER the run
            (an assertion that the code did not change, not a measurement that it did not);
            the rest were stamped at write time.

arm            field%  exact%  micro-d  paired-d           95% CI   in tok sig  leak   comp  look  reso  surv
none              0.0     0.0    -97.9     -98.0   [-99.7, -96.0]      212 *     0      0     0     0     0
perfect          97.1    95.3     -0.8      -0.7     [-1.7, +0.0]      259       0     91   100   100   100
resolved         97.9    96.7     +0.0      +0.0     [+0.0, +0.0]      418       0     93   100   100   100
unresolved       84.0    76.7    -13.9     -15.7   [-21.0, -10.3]      679 *     0     83    92    81    73
stale            92.0    87.3     -5.9      -8.7    [-13.7, -4.0]      417 *     0     91    99   100    70
incomplete       56.3    48.7    -41.6     -40.3   [-47.7, -33.0]      327 *     0     55    63    40    65
diluted          95.8    93.3     -2.1      -2.0     [-4.7, +0.7]    2,781       0     87   100   100   100
unpoliced        97.1    95.3     -0.8      -1.3     [-4.0, +1.3]      442     150     91   100   100   100
nostructure      97.5    96.0     -0.4      -0.3     [-1.0, +0.0]      425       0     92   100   100   100
governed         94.5    91.3     -3.4      -2.7     [-5.3, -0.3]      416 *     0     92    91   100   100

strata: computation, lookup, resolution, survivorship    * = interval excludes zero, so the difference is separated
micro-d = field% minus the baseline's field%, every FIELD weighted equally.
paired-d = mean over QUESTIONS of the per-question difference, which is what
the interval is computed on. Quote which one you mean; they are not the same
number and on this data they differ by up to about seven points.

TOKEN-BUDGET CURVE (ranked context cut at a budget):
  budget  field%  exact%   in tok  n
     150    68.9    61.7      300  60
     300    90.0    85.0      393  60
     600    94.4    91.7      589  60
    1200    96.7    95.0      987  60
    2400    98.9    98.3    1,741  60
    4800    98.9    98.3    3,516  60

  paired against the largest budget (4800):
    budget   150 vs 4800:  -36.7   [-48.3, -25.0] *
    budget   300 vs 4800:  -11.7    [-20.0, -4.2] *
    budget   600 vs 4800:   -6.7    [-15.0, +0.0]  
    budget  1200 vs 4800:   -3.3    [-10.0, +3.3]  
    budget  2400 vs 4800:   +0.0     [-5.0, +5.0]  

  peak at budget 2400 (98.9%); largest budget 4800 scores 98.9%
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

Two effects are far larger than the between-run drift measured by the
replicate and replicate across both vendors: incompleteness and unresolved
entities. Two more separate WITHIN a run and are the same size as that drift,
so they are reported as suggestive rather than established.

The `unresolved` row above is an UPPER BOUND and not a measurement of entity
resolution alone: 22 of the 150 questions name an agreement by an identifier
only the resolved view carries, so that arm cannot identify what it is asked
about and correctly answers null. Excluding those 22 the effect is roughly -11
rather than -19.7. README.md derives the corrected figures from these same
rows and `scripts/preflight.py` gates the property; the two checks added for
it are the last two PASS lines in the first block above.

The conditions that do not separate are as interesting: dilution, prose
rendering and skipping the field policy. The last is the security result. 150
leaked prompts per run, with an accuracy signal that lands on both sides of the
baseline across runs, which is what no effect looks like.

That budget prediction is NOT SUPPORTED on either run, and the report says so in
its own words. It does not print a peak and leave a reader to infer
confirmation. The only budgets that separate from the largest are the small
ones, and they separate downward, which is the opposite claim. Not supported is
not the same as refuted and `PREDICTIONS.md` says why; all three documents use
the weaker word because it is the one this design can support.
