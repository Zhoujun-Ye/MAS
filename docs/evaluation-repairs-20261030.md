# Evaluation Repairs After Lite 100

These changes are post-study engineering changes. They do not revise the original
69/100 result or justify attributing all failed evaluations to agent behavior.
The initial audit made no model calls. The user subsequently explicitly authorized
rerunning failures caused by engineering/benchmark problems and replacing their
effective results. Original evidence is retained rather than overwritten.

## Diagnostics

Grades now include additive, versioned diagnostics distinguishing test failures,
collection errors, fixture errors, evaluator errors and unresolved failures.
Both upstream output keys (`output` and `test_output`) are supported. Test phase
does not establish cause: a fixture error is not automatically an infrastructure
failure, and a collection error can be caused by submitted code.

The Go runner uses `set -e` and captures failing `go test` output into a variable;
the shell exits before printing it. The Docker backend now traces only the Go
runner invocation, including the invocation inside upstream's merged evaluation.
It preserves the runner's exit status and does not edit tests, patches or the
pinned checkout. The backend version is now isolated-docker-cli-v9, invalidating
old admission caches for future runs. Admission must be repeated before any new
paid study. Extra diagnostic output is subject to the existing capture limit.

## Explicit Benchmark Errata

The original assignment profile remains `official`. A separate `clarified-v1`
profile fixes two confirmed interface/storage contradictions in task text:

- tiktoken task0 feature9: require `compression` and retain `compress` as an alias.
- DSPy task8394 feature5: default uncompressed writes retain original objects;
  compressed writes use the header format; legacy/header decoding remains required.

This profile is selectable explicitly via `scripts/cooperbench/run.py
--benchmark-profile clarified-v1`. The manifest records the profile and per-worker
input hashes, and the grade carries that receipt. It is a modified benchmark
variant, not an untouched official score. Hidden tests and gold patches remain
unchanged and evaluator-only. No per-task collaboration strategy is added.

The existing lite batch mode still uses official assignments. The separate
`--authorized-repair-paid-pairs` mode requires an original failed run for each
selected pair, registered errata, immutable snapshot validation and hashed
original evidence. It uses clarified-v1 and cannot mix with continuation/reuse.
The selected pairs must pass fresh isolation, baseline, gold and joint-merge
gates on their actual images. The profile is not a claim that every remaining
benchmark ambiguity has been resolved.

## Verification

Server scripted regressions: 203 passed. Coverage includes diagnostic extraction,
raw verdict preservation, shell failure capture with unchanged exit status,
opt-in errata, unaffected partner inputs and input digest changes. No real-model
effectiveness claim follows from these tests.

The original grade files stay unchanged. Any Docker diagnostic re-evaluation uses
a new `diagnostic-grade-v9.json` file, never replacing a study score. It tests the
already-frozen artifact without requesting a new agent solution.

## Authorized Repair Scope

- Original index 8: one offline re-evaluation of the exact submitted patches
  passed both features. No solution or test was changed. Original fixture
  timeout root cause remains unresolved; the new observation supports a
  non-stable evaluation failure, not a proven dependency fix.
- Original index 17: diagnostic re-evaluation still fails. Captured output names
  TestMethodNotAllowed/Unregistered_Method and
  TestSetAllowHeader/Unregistered_Method. No paid rerun is planned.
- Original indices 7 and 27: one newly authorized model attempt each with
  clarified-v1, after offline gates. Selection is frozen in
  configs/cooperbench-repair-20261031.json. No automatic retry or paid judge.
- New setup evidence: outputs/setup/repair-20261031-01/.
- Completed paid repair output: outputs/cooperbench/repair-20261031-01/.

The effective summary includes both authorized paid replacements regardless of
outcome. The current result is 71/100; the original 69/100 is retained only in
this history and audit receipts, not as a parallel current scoreboard. Added
calls/cost remain accounted for. Indices other than 7, 8 and 27 are unchanged.

Completed outcome: index27 passed; index7's compression feature passed but its
cache-statistics feature failed with an expected miss count of one versus zero.
No second paid retry was attempted. The replacement scoreboard records 71/100,
100 protocol completions, original 69/100, and all evidence hashes. Generate it
with scripts/cooperbench/repair_report.py, which rejects overlapping/missing
original indices, duplicate replacements, mismatched pairs and unbound grades,
and refuses to overwrite an existing summary. Original study results and this
mixed-profile revision must remain distinguishable.
