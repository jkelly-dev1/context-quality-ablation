# Sample run

Captured output. Nothing here is retyped, summarized or reformatted; each block
is the literal stdout of the command above it. Where anything had been altered
this header would say so, and nothing was.

Captured: 2026-08-25T05:21:02Z
Python: 3.13.7

The paid runs are not repeated here. Their results ship in `results/` and every
figure in README.md is rebuilt from them by the last command below. The first
three commands need no network, no credentials and no model.

## Proving the harness, with no model at all

```
$ python3 scripts/preflight.py
LAYER 1: oracle reader, no model, no network
  PASS  every arm produces distinct, non-empty context  0 empty, 0 collisions
  PASS  every prompt carries its own question  0 missing
  PASS  the floor arm carries no context and no answer in its prompt  0 prompts contain their own answer
  PASS  the ceiling STATES every non-derived answer  0 unreachable
  PASS  the grader accepts a correct answer
  PASS  the grader rejects a near miss
  PASS  exactly one arm bypasses the field policy  leaking: ['unpoliced']
  PASS  the fingerprint changes when any answer key changes  d16da8a7f36f7564
  PASS  the curve renders and grows with its budget  0 budgets shrank
  PASS  the curve carries no forbidden field  0 leaking prompts
  PASS  the curve budget actually bounds the context
  PASS  every answer key is obtainable from a source system  0 unobtainable

12/12 checks passed
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
..........................................................               [100%]
58 passed in 10.59s
```

## Every README figure, rebuilt from the shipped evidence

```
$ python3 scripts/check_readme_numbers.py
34 figures derived from sweep.jsonl, sweep_openai.jsonl
34 found in README.md, 0 missing
```

It prints the count whether or not anything is missing, so a version that
quietly stopped deriving half the figures is visible rather than clean. It is
a substring test: it cannot tell a right number in a wrong cell.

## The Claude results

```
$ python3 scripts/report.py
1860 generations | 1500 arms + 360 curve | 150 questions | claude-sonnet-5 effort low

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

The conditions that do not separate are as interesting: dilution, prose
rendering and skipping the field policy. The last is the security result. 150
leaked prompts per run, with an accuracy signal that lands on both sides of the
baseline across runs, which is what no effect looks like.

That budget prediction is refuted on every run, and the report says so in its own
words. It does not print a peak and leave a reader to infer confirmation. The
only budgets that separate from the largest are the small ones, and they
separate downward, which is the opposite claim.
