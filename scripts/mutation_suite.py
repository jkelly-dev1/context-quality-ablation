#!/usr/bin/env python3
"""Break one thing at a time and prove a named test notices.

    python3 scripts/mutation_suite.py

A test that has never failed is a guess. README.md makes claims of the form
"(mutation-checked: <edit> and it fails)", and this file lets a reader re-run
each of them instead of taking the sentence on trust: every entry patches one
piece of real code, runs the single test that is supposed to catch it, and
requires that test to go red.

What it refuses to do, each because the alternative is a green sweep that
proved nothing:

  An entry whose `find` text is no longer in its file would patch nothing and
  score by whatever the test did anyway. Every anchor is checked to occur
  EXACTLY ONCE before anything is written.

  A named test that no longer collects (renamed, moved, deleted) makes
  pytest exit non-zero for a reason that has nothing to do with the mutation.
  Every named test is collected first.

  A named test that is red already, or that only passes when something else
  has run before it, scores as caught whatever the mutation does. Every named
  test is run alone, on the unmutated tree, and must pass.

What it does to keep the tree intact. The original text is copied to
.mutation_suite_pristine/ at the repository root, which git ignores, and its
sha256 recorded in a sentinel BEFORE the patch is written, so an interrupted
run is repairable; SIGTERM, SIGINT and SIGHUP restore and re-raise; the next
run repairs what a SIGKILL left. After every entry the file's sha256 must match
what it was, and the sweep stops if it does not. __pycache__ is purged between
entries: CPython decides a .pyc is still current from the source's mtime
truncated to whole seconds and its size in bytes, so a mutate-run-restore cycle
that changes neither can leave the interpreter running bytecode compiled from
the mutated file after the file on disk is clean again.

Exit status is 0 when every entry was caught and non-zero otherwise, so CI can
gate on it. It is not a coverage measure: each entry is one specific claim,
and the code the entries do not touch is not thereby proven.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SENTINEL = ROOT / ".mutation_suite_state.json"
PRISTINE = ROOT / ".mutation_suite_pristine"

MUTATIONS = [
    {
        "name": 'M1 the incomplete arm drops a different number of fields than the constant, the label and README.md all state',
        "file": 'cqa/assemble.py',
        "find": 'DROPPED_FIELDS = 4',
        "replace": 'DROPPED_FIELDS = 5',
        "test": 'tests/test_harness.py::test_the_incomplete_arm_drops_the_count_it_advertises_on_every_question',
    },
    {
        "name": 'M2 THE GENERAL GUARD: the same mutation, caught because the shipped 5,580 generations no longer describe what the code renders',
        "file": 'cqa/assemble.py',
        "find": 'DROPPED_FIELDS = 4',
        "replace": 'DROPPED_FIELDS = 5',
        "test": 'tests/test_harness.py::test_the_shipped_results_still_describe_the_code_that_renders_them',
    },
    {
        "name": 'M3 the bootstrap returns an interval of zero width around the estimate, which stars every arm and FLIPS the curve verdict',
        "file": 'scripts/report.py',
        "find": '    boots.sort()\n    return point, boots[int(0.025 * len(boots))], boots[int(0.975 * len(boots))]',
        "replace": '    boots.sort()\n    return point, point, point',
        "test": 'tests/test_harness.py::test_the_interval_is_computed_and_not_merely_printed',
    },
    {
        "name": 'M4 the per-arm staleness refusal is switched off while the report goes on printing its numbers',
        "file": 'scripts/report.py',
        "find": '    if stale_arms:',
        "replace": '    if False:',
        "test": 'tests/test_harness.py::test_the_report_refuses_an_arm_whose_assembly_no_longer_matches',
    },
    {
        "name": "M5 the prompt's first rule is rewritten to the opposite instruction -- the edit that changes what the floor arm MEANS",
        "file": 'cqa/prompt.py',
        "find": '    "- Answer strictly from the context. Do not use outside knowledge about "\n    "any organization or person named.\\n"',
        "replace": '    "- Use outside knowledge freely.\\n"',
        "test": 'tests/test_harness.py::test_the_shipped_results_still_describe_the_code_that_renders_them',
    },
    {
        "name": 'M6 the same edit, caught by the fingerprint that now covers the prompt rather than by the results',
        "file": 'cqa/prompt.py',
        "find": '    "- Answer strictly from the context. Do not use outside knowledge about "\n    "any organization or person named.\\n"',
        "replace": '    "- Use outside knowledge freely.\\n"',
        "test": 'tests/test_harness.py::test_the_prompt_fingerprint_moves_with_the_instruction_and_not_the_context',
    },
    {
        "name": "M7 questions go back to naming an agreement by the internal id, which no source carries and the unresolved arm cannot see",
        "file": 'cqa/questions.py',
        "find": '        return f"the agreement that started on {_iso(k[\'start_date\'])} at {name}"',
        "replace": '        return f"the agreement {k[\'contract_id\']} at {name}"',
        "test": 'tests/test_harness.py::test_every_arm_that_renders_agreements_can_identify_the_one_asked_about',
    },
    {
        "name": 'M8 the default credential path stops being ignored by git, so `git add -A` would stage a key file',
        "file": '.gitignore',
        "find": '\n.env\n.env.*\n',
        "replace": '\n.env.local\n',
        "test": 'tests/test_harness.py::test_the_default_credential_path_is_ignored_by_git',
    },
    {
        "name": 'M9 the figure checker keeps its own copy of the prices, so a price change leaves it certifying a cost figure derived from the old one',
        "file": 'scripts/check_readme_numbers.py',
        "find": '            rate = sweep.PROVIDERS[provider]\n            cost = tin / 1e6 * rate["in"] + tout / 1e6 * rate["out"]',
        "replace": '            rate_out = 12.00 if provider == "openai" else 10.00\n            cost = tin / 1e6 * 2.00 + tout / 1e6 * rate_out',
        "test": 'tests/test_harness.py::test_one_price_table_and_every_consumer_reads_it',
    },
    {
        "name": 'M10 the batch rate is typed as a pair of literals again -- equal to half the standard rate TODAY, and not a rule about it',
        "file": 'scripts/offline.py',
        "find": '    "sonnet-5 batch": (_STD[0] / 2, _STD[1] / 2),',
        "replace": '    "sonnet-5 batch": (1.00, 5.00),',
        "test": 'tests/test_harness.py::test_one_price_table_and_every_consumer_reads_it',
    },
    {
        "name": 'M11 a condition whose interval excludes zero loses its emphasis, so bold stops meaning the one thing README.md says it means',
        "file": 'README.md',
        "find": '| stale | **93.7** | **93.7** | 92.9 |',
        "replace": '| stale | 93.7 | **93.7** | 92.9 |',
        "test": 'tests/test_harness.py::test_the_figure_checker_main_returns_a_verdict_ci_can_act_on',
    },
    {
        "name": 'M12 the count of derived figures is left at a stale value, which is the sentence README.md offers as its tamper-evidence',
        "file": 'README.md',
        "find": 'rebuilds 74 figures in this',
        "replace": 'rebuilds 34 figures in this',
        "test": 'tests/test_harness.py::test_the_figure_checker_main_returns_a_verdict_ci_can_act_on',
    },
    {
        "name": "M13 the report's prompt gate is switched off, so results recorded under a different instruction aggregate silently",
        "file": 'scripts/report.py',
        "find": '    if prompts != {live_prompt}:',
        "replace": '    if False:',
        "test": 'tests/test_harness.py::test_the_report_refuses_results_recorded_under_a_different_prompt',
    },
    {
        "name": 'M14 a failed pre-flight check stops refusing to certify -- the CI step then passes while the tool prints its own failure',
        "file": 'scripts/preflight.py',
        "find": '        for n in failed:\n            print(f"  - {n}")\n        return 1',
        "replace": '        for n in failed:\n            print(f"  - {n}")\n        return 0',
        "test": 'tests/test_harness.py::test_the_preflight_main_returns_a_verdict_ci_can_act_on',
    },
    {
        "name": 'M15 the leak detector compares only the exact stored string, so a de-punctuated forbidden value stops being a leak (README.md:216)',
        "file": 'cqa/leak.py',
        "find": '    exact = sorted(v for v in values\n                   if v in text or (len(v) > 6 and _digits(v) in stripped))\n    shaped = sorted(set(SHAPE.findall(text)))',
        "replace": '    exact = sorted(v for v in values if v in text)\n    shaped = []',
        "test": 'tests/test_harness.py::test_a_reformatted_forbidden_value_is_still_a_leak',
    },
    {
        "name": 'M16 the stale arm rewinds the WHOLE context instead of the volatile fields, which ages the contact roster too (README.md:219)',
        "file": 'cqa/assemble.py',
        "find": '        fresh = _resolve(w, q, as_of)\n        old = _resolve(w, q, as_of - timedelta(days=STALE_DAYS))',
        "replace": '        fresh = _resolve(w, q, as_of - timedelta(days=STALE_DAYS))\n        old = _resolve(w, q, as_of - timedelta(days=STALE_DAYS))',
        "test": 'tests/test_harness.py::test_the_stale_arm_keeps_the_contact_roster_current',
    },
    {
        "name": 'M17 the answer key orders by ARRIVAL instead of effective date, which is the decision survivorship turns on (README.md:220)',
        "file": 'cqa/world.py',
        "find": '                    and ch.field == fname and ch.effective <= as_of):',
        "replace": '                    and ch.field == fname and ch.recorded <= as_of):',
        "test": 'tests/test_harness.py::test_the_key_orders_by_effective_date_and_the_arrival_system_does_not',
    },
    {
        "name": "M18 a contact's email stops following them to a new employer, so a context names one employer on the org line and another in the address (README.md:222)",
        "file": 'cqa/sources.py',
        "find": '        stamp = ch.recorded if use_recorded else ch.effective\n        if stamp <= when:\n            value = ch.value',
        "replace": '        stamp = ch.recorded if use_recorded else ch.effective\n        if stamp <= when and ch.field != "email":\n            value = ch.value',
        "test": 'tests/test_harness.py::test_a_contact_email_follows_them_to_their_new_employer',
    },
    {
        "name": "M30 the sibling that renders a sample before the first "
                "request stops checking the scheme its twin checks",
        "file": "scripts/preflight.py",
        "find": "    if not base_url.startswith(_LOCAL_SCHEMES):\n        raise ValueError(\n            f\"--local must be an http:// or https:// URL, not {base_url!r}.\")",
        "replace": "    if False:\n        raise ValueError(\n            f\"--local must be an http:// or https:// URL, not {base_url!r}.\")",
        "test": "tests/test_harness.py::test_the_local_endpoint_url_must_be_http",
    },
    {
        "name": "M29 the local endpoint URL stops being checked, so urllib "
                "will open file:// when it was told to call a model",
        "file": "scripts/preflight.py",
        "find": "    if not base_url.startswith(_LOCAL_SCHEMES):\n        raise ValueError(\n            f\"--local must be an http:// or https:// URL, not {base_url!r}. \"",
        "replace": "    if False:\n        raise ValueError(\n            f\"--local must be an http:// or https:// URL, not {base_url!r}. \"",
        "test": "tests/test_harness.py::test_the_local_endpoint_url_must_be_http",
    },
    {
        "name": "M25 the question-set refusal is switched off, so results "
                "from a different generator aggregate under this code",
        "file": "scripts/report.py",
        "find": "    if stamps != {live}:",
        "replace": "    if False:",
        "test": "tests/test_harness.py::test_the_report_refuses_results_that_do_not_match_the_code",
    },
    {
        "name": "M26 the arm table prints a difference with no interval "
                "beside it, which is a ranking of six noisy numbers",
        "file": "scripts/report.py",
        "find": "f\"{micro:>+8.1f} {pt:>+9.1f} {f'[{lo:+.1f}, {hi:+.1f}]':>16} \"",
        "replace": "f\"{micro:>+8.1f} {pt:>+9.1f} {'':>16} \"",
        "test": "tests/test_harness.py::test_the_report_never_prints_a_difference_without_an_interval",
    },
    {
        "name": "M27 the leak summary stops naming the arms that leak, so it "
                "can deny a leak shown two lines above it",
        "file": "scripts/report.py",
        "find": '    leaky = sorted({r["arm"] for r in rows if r["governance"]["prompt_leak"]})',
        "replace": "    leaky = []",
        "test": "tests/test_harness.py::test_the_report_names_the_arms_that_leak_rather_than_asserting_the_rest",
    },
    {
        "name": "M28 the question-set refusal fires on results that DO match, "
                "so a correct run is reported as unreportable",
        "file": "scripts/report.py",
        "find": "    if stamps != {live}:",
        "replace": "    if True:",
        "test": "tests/test_harness.py::test_the_report_renders_a_stamped_results_file",
    },
    {
        "name": "M23 the predicate the floor check searches with stops "
                "qualifying anything, so it searches for nothing at all",
        "file": "cqa/questions.py",
        "find": "MIN_DISTINCTIVE = 5",
        "replace": "MIN_DISTINCTIVE = 40",
        "test": "tests/test_harness.py::test_a_value_is_distinctive_at_five_characters_and_not_at_four",
    },
    {
        "name": "M24 the same edit, caught by the floor check itself going "
                "quiet rather than by the predicate's own test",
        "file": "cqa/questions.py",
        "find": "MIN_DISTINCTIVE = 5",
        "replace": "MIN_DISTINCTIVE = 40",
        "test": "tests/test_harness.py::test_the_floor_arm_carries_no_context_and_no_answer_in_its_prompt",
    },
    {
        "name": "M21 the report's refusal stops setting a non-zero "
                "exit code, so the CI step passes while it prints REFUSING",
        "file": "scripts/report.py",
        "find": "              f\"the code revision that produced them.\")\n        return 2",
        "replace": "              f\"the code revision that produced them.\")\n        return 0",
        "test": "tests/test_harness.py::test_the_report_main_returns_a_verdict_ci_can_act_on",
    },
    {
        "name": "M22 the suite stops refusing an entry whose target "
                "text has left its file, and scores it by whatever the test did",
        "file": "scripts/mutation_suite.py",
        "find": "    if problems:\n        print(\"REFUSING TO START. An entry that cannot fire",
        "replace": "    if False:\n        print(\"REFUSING TO START. An entry that cannot fire",
        "test": "tests/test_harness.py::test_the_mutation_suite_main_returns_a_verdict_ci_can_act_on",
    },
    {
        "name": "M20 the report stops saying which stamps were written "
                "after the run, so an assertion reads as a measurement",
        "file": "scripts/report.py",
        "find": "    if any(asserted.values()):",
        "replace": "    if False:",
        "test": "tests/test_harness.py::test_the_report_says_which_stamps_were_written_after_the_run",
    },
    {
        "name": 'M19 an arm fingerprint over an EMPTY question set goes back to returning the hash of the empty string -- a plausible stamp for a condition nothing rendered',
        "file": 'cqa/assemble.py',
        "find": '        raise ValueError("no questions: an arm fingerprint over an empty "\n                         "question set describes nothing")',
        "replace": '        return hashlib.sha256(b"").hexdigest()[:16]',
        "test": 'tests/test_harness.py::test_a_fingerprint_over_no_questions_is_refused_rather_than_returned',
    },    {
        "name": "M31 the output-leak figure is matched against a literal again, so five leaking rows leave README.md's 'OUTPUT 0 times' green",
        "file": "scripts/check_readme_numbers.py",
        "find": "rf\"OUTPUT {n_out} times\"",
        "replace": "r\"OUTPUT 0 times\"",
        "test": "tests/test_harness.py::test_the_leak_figures_are_matched_against_the_derived_count",
    },
    {
        "name": "M32 the curve verdict counts a budget separated on EITHER side as support, so a losing budget reads as the prediction holding",
        "file": "scripts/report.py",
        "find": "    return any(lo is not None and lo > 0 for _, lo, _ in pairs)",
        "replace": "    return any(lo is not None and (lo > 0 or hi < 0) for _, lo, hi in pairs)",
        "test": "tests/test_harness.py::test_the_curve_verdict_requires_the_difference_to_point_the_right_way",
    },
    {
        "name": "M33 the report's micro/paired gap goes back to a typed sentence",
        "file": "scripts/report.py",
        "find": "f\"differ by up to {gap:.1f} points.\")",
        "replace": "\"differ by up to about seven points.\")",
        "test": "tests/test_harness.py::test_the_micro_and_paired_gap_is_measured_not_typed",
    },
    {
        "name": "M34 the contract-key gate stops checking day counts, so a world-truth key would pass unnamed",
        "file": "scripts/preflight.py",
        "find": "            if \"days_until_renewal\" in keys:\n                ok &= any(",
        "replace": "            if False:\n                ok &= any(",
        "test": "tests/test_harness.py::test_every_contract_key_is_what_a_source_showed",
    },
    {
        "name": "M35 the curve stops filtering CRM_B deals by start date, so unstarted deals reach it again",
        "file": 'cqa/assemble.py',
        "find": '    deals = [r for r in b["deals"]\n             if r["company_id"] != 5000 + idx or r["deal_id"] in live]',
        "replace": '    deals = list(b["deals"])',
        "test": "tests/test_harness.py::test_the_curve_ships_no_unstarted_agreement_and_no_unstarted_deal",
    },
    {
        "name": "M43 a contract key reads world truth even where no source showed it",
        "file": 'cqa/questions.py',
        "find": '    if truth in (a, b):\n        return truth',
        "replace": '    if True:\n        return truth',
        "test": "tests/test_harness.py::test_every_contract_key_is_what_a_source_showed",
    },
    {
        "name": "M44 the sweep resumes into rows from another question set",
        "file": 'scripts/sweep.py',
        "find": '            if got and got != fp:\n                out.add(got)',
        "replace": '            if False:\n                out.add(got)',
        "test": "tests/test_harness.py::test_a_sweep_will_not_resume_into_rows_from_another_question_set",
    },
    {
        "name": "M45 an organization's two agreements start on the same day, so a start date names neither",
        "file": 'cqa/world.py',
        "find": '            start = EPOCH + timedelta(days=30 * ((i + k) % 11))',
        "replace": '            start = EPOCH + timedelta(days=30 * (i % 11))',
        "test": "tests/test_harness.py::test_no_organization_holds_two_agreements_starting_the_same_day",
    },
    {
        "name": "M46 a question stops naming which of two agreements it asks about",
        "file": 'cqa/questions.py',
        "find": "        return f\"the agreement that started on {_iso(k['start_date'])} at {name}\"",
        "replace": "        return name",
        "test": "tests/test_harness.py::test_no_question_asks_for_a_single_agreement_field_ambiguously",
    },
    {
        "name": "M47 a renewal key reads world truth instead of what a source showed",
        "file": 'cqa/questions.py',
        "find": '        return shown_contract_value(w, cid, "renewal_date", as_of)',
        "replace": '        return w.value_as_of("contract", cid, "renewal_date", as_of)',
        "test": "tests/test_harness.py::test_every_contract_key_is_what_a_source_showed",
    },
    {
        "name": "M36 the prompt backfill overwrites a stamp written under another prompt, erasing what the report refuses on",
        "file": "scripts/backfill_prompt_fingerprint.py",
        "find": "            if stamp is not None:\n",
        "replace": "            if False:\n",
        "test": "tests/test_harness.py::test_the_backfills_stamp_only_rows_that_carry_no_hash",
    },
    {
        "name": "M37 the curve backfill overwrites a real hash of other code",
        "file": "scripts/backfill_curve_fingerprint.py",
        "find": "            if stamp not in (None, \"curve\"):\n",
        "replace": "            if False:\n",
        "test": "tests/test_harness.py::test_the_backfills_stamp_only_rows_that_carry_no_hash",
    },
    {
        "name": "M38 the leak detector stops treating slash, underscore and parentheses as separators",
        "file": "cqa/leak.py",
        "find": "SEPARATORS = re.compile(r\"[\\s./_()-]\")",
        "replace": "SEPARATORS = re.compile(r\"[\\s.-]\")",
        "test": "tests/test_harness.py::test_a_reformatted_forbidden_value_is_still_a_leak",
    },
    {
        "name": "M39 pre-flight layer 2's floor-arm call leaves the try block, so an endpoint error there is a traceback",
        "file": "scripts/preflight.py",
        "find": "            none_ans, _ = ask_local(base_url, model, q,\n                                    assemble.context_for(w, q, \"none\"))\n        except (urllib.error.URLError, OSError, KeyError) as exc:\n            check(r, \"local endpoint reachable\", False, str(exc)[:60])\n            return r\n        parsed += isinstance(ans, dict) and set(ans) >= set(q.answer)",
        "replace": "        except (urllib.error.URLError, OSError, KeyError) as exc:\n            check(r, \"local endpoint reachable\", False, str(exc)[:60])\n            return r\n        parsed += isinstance(ans, dict) and set(ans) >= set(q.answer)\n        none_ans, _ = ask_local(base_url, model, q,\n                                assemble.context_for(w, q, \"none\"))",
        "test": "tests/test_harness.py::test_a_local_endpoint_that_fails_on_the_floor_call_is_a_fail_line",
    },    {
        "name": "M40 the unresolved arm ships every CRM_B deal of the company, started or not",
        "file": "cqa/assemble.py",
        "find": "                  if r[\"company_id\"] in cids and r[\"deal_id\"] in live]",
        "replace": "                  if r[\"company_id\"] in cids]",
        "test": "tests/test_harness.py::test_no_arm_ships_an_agreement_or_deal_that_has_not_started",
    },
    {
        "name": "M41 the report prints the supporting verdict whatever the curve's intervals say",
        "file": "scripts/report.py",
        "find": "        sep_any = curve_supports_prediction(pairs)",
        "replace": "        sep_any = True",
        "test": "tests/test_harness.py::test_the_shipped_curve_verdict_is_the_one_the_readme_reports",
    },
    {
        "name": "M48 the sweep's call site ignores the stale-fingerprint result, so main() resumes into another question set",
        "file": "scripts/sweep.py",
        "find": "    stale = stale_fingerprints(results, fp)\n    if stale:\n",
        "replace": "    stale = stale_fingerprints(results, fp)\n    if False:\n",
        "test": "tests/test_harness.py::test_the_sweep_main_refuses_to_resume_into_another_question_set",
    },
    {
        "name": "M49 the figure checker returns 0 when a figure is missing, so the CI step passes while it prints its own failure",
        "file": "scripts/check_readme_numbers.py",
        "find": "        return 1\n    return 0\n",
        "replace": "        return 0\n    return 0\n",
        "test": "tests/test_harness.py::test_the_figure_checker_main_returns_a_verdict_ci_can_act_on",
    },
]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# Caches under these are not the repository's code, and a local virtualenv
# kept in the tree would otherwise lose its own bytecode before every entry.
_NOT_OURS = {".venv", "venv", "envs", ".git"}


def purge_bytecode() -> None:
    for cache in ROOT.rglob("__pycache__"):
        if _NOT_OURS.isdisjoint(cache.relative_to(ROOT).parts):
            shutil.rmtree(cache, ignore_errors=True)


def _pristine_path(rel: str) -> Path:
    return PRISTINE / rel.replace("/", "__")


def repair_interrupted_sweep() -> str:
    """Put back whatever a killed run left patched. Returns what it did."""
    if not SENTINEL.is_file():
        return ""
    state = json.loads(SENTINEL.read_text(encoding="utf-8"))
    rel = state["file"]
    target, keep = ROOT / rel, _pristine_path(rel)
    if not keep.is_file():
        raise SystemExit(
            f"REFUSING TO START. {SENTINEL.name} says {rel} was patched by a "
            f"run that did not finish, and the pristine copy at {keep} is "
            f"gone. Restore {rel} from git before running this again.")
    target.write_text(keep.read_text(encoding="utf-8"), encoding="utf-8")
    if sha(target) != state["sha_before"]:
        raise SystemExit(
            f"REFUSING TO START. {rel} was put back from {keep} and its "
            f"sha256 still does not match what the interrupted run recorded.")
    keep.unlink()
    SENTINEL.unlink()
    purge_bytecode()
    return (f"repaired: {rel} was left patched by an interrupted run and has "
            f"been restored from {keep.name}")


def refuse_unless_ready() -> None:
    """Both halves of every entry, before anything is written."""
    problems = []
    for m in MUTATIONS:
        path = ROOT / m["file"]
        if not path.is_file():
            problems.append(f"{m['name']}: {m['file']} does not exist")
            continue
        n = path.read_text(encoding="utf-8").count(m["find"])
        if n != 1:
            problems.append(
                f"{m['name']}: its target text occurs {n} times in "
                f"{m['file']}, not once, so this entry would patch "
                f"{'nothing' if n == 0 else 'more than it names'}")
    for test in sorted({m["test"] for m in MUTATIONS}):
        r = subprocess.run(
            [sys.executable, "-m", "pytest", "--collect-only", "-q", test],
            cwd=ROOT, capture_output=True, text=True,
            env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
        if r.returncode != 0:
            problems.append(f"{test} no longer collects")
    if problems:
        print("REFUSING TO START. An entry that cannot fire is worse than no "
              "entry: it scores by whatever the test did anyway.")
        for p in problems:
            print(f"  {p}")
        raise SystemExit(2)


def named_tests_pass_alone() -> list:
    """Each named test, by itself, on the unmutated tree.

    An entry is scored by its test going red, so a test that is red already,
    or one that only passes after something else in the suite has run, would
    score as caught whatever the mutation did. One process per test, because
    that is what alone means.
    """
    bad = []
    for test in sorted({m["test"] for m in MUTATIONS}):
        r = subprocess.run(
            [sys.executable, "-m", "pytest", test, "-q", "--tb=no"],
            cwd=ROOT, capture_output=True, text=True,
            env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
        if r.returncode != 0:
            last = (r.stdout.strip().splitlines() or ["no output"])[-1]
            bad.append(f"{test}\n      {last}")
    return bad


def _restoring_handler(target: Path, original: str):
    def handler(signum, frame):
        target.write_text(original, encoding="utf-8")
        _clear_sentinel(target)
        purge_bytecode()
        signal.signal(signum, signal.SIG_DFL)
        os.kill(os.getpid(), signum)
    return handler


def _write_sentinel(m: dict, original: str, before: str) -> None:
    PRISTINE.mkdir(exist_ok=True)
    _pristine_path(m["file"]).write_text(original, encoding="utf-8")
    SENTINEL.write_text(json.dumps(
        {"file": m["file"], "name": m["name"], "sha_before": before,
         "undo": f"copy {_pristine_path(m['file'])} back over {m['file']}"},
        indent=2), encoding="utf-8")


def _clear_sentinel(target: Path) -> None:
    keep = _pristine_path(str(target.relative_to(ROOT)))
    if keep.is_file():
        keep.unlink()
    if SENTINEL.is_file():
        SENTINEL.unlink()
    if PRISTINE.is_dir() and not any(PRISTINE.iterdir()):
        PRISTINE.rmdir()


def run_one(m: dict) -> bool:
    target = ROOT / m["file"]
    original = target.read_text(encoding="utf-8")
    before = sha(target)

    previous = {}
    handler = _restoring_handler(target, original)
    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        try:
            previous[sig] = signal.signal(sig, handler)
        except (ValueError, OSError):
            pass
    _write_sentinel(m, original, before)
    try:
        target.write_text(original.replace(m["find"], m["replace"], 1),
                          encoding="utf-8")
        purge_bytecode()
        r = subprocess.run(
            [sys.executable, "-m", "pytest", m["test"], "-q", "--tb=no"],
            cwd=ROOT, capture_output=True, text=True,
            env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
        # A catch is a test that failed, which is pytest's word for an
        # assertion that did not hold. It is not an error (a fixture that blew
        # up before the test body ran asserted nothing), and it is not a
        # usage error, an empty collection or an interrupted run, all of which
        # also exit non-zero.
        caught = (r.returncode == 1
                  and re.search(r"\d+ failed", r.stdout) is not None)
        if r.returncode != 0 and not caught:
            print("      (not scored: %s)"
                  % (r.stdout.strip().splitlines() or ["no output"])[-1])
    finally:
        for sig, prev in previous.items():
            signal.signal(sig, prev)
        target.write_text(original, encoding="utf-8")
        _clear_sentinel(target)
        purge_bytecode()
    if sha(target) != before:
        raise SystemExit(f"RESTORE FAILED for {m['file']}; the tree is dirty")
    return caught


def main() -> int:
    repaired = repair_interrupted_sweep()
    if repaired:
        print(repaired)
    refuse_unless_ready()
    alone = named_tests_pass_alone()
    if alone:
        print("REFUSING TO START. These tests do not pass on their own, so "
              "their entries would score as caught whatever the mutation did:")
        for line in alone:
            print(f"  {line}")
        return 2

    print(f"{len(MUTATIONS)} mutations, each with its own named test\n")
    missed = []
    for m in MUTATIONS:
        caught = run_one(m)
        print(f"  {m['name'][:64]:<64} {'caught' if caught else 'NOT CAUGHT'}")
        if not caught:
            missed.append(m["name"])
    print(f"\n{len(MUTATIONS) - len(missed)} of {len(MUTATIONS)} caught")
    if missed:
        print("A claim that a test catches an edit is a claim about THIS run.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
