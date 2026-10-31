# Current Lite 100 Failure Analysis

Scope: the 29 failures in the current 71/100 scoreboard. All failure records were
reviewed, with targeted assignment/code/test/trace inspection; this is not an
exhaustive semantic review of every turn. No paid judge was used.

## Common Patterns

These are descriptive, mutually exclusive primary symptom groups, not causal
labels. Several cases also involve ambiguous or overly specific test contracts.

| Primary symptom | Pairs | Indices |
| --- | ---: | --- |
| State, lifecycle and repeated-use behavior | 7 | 7, 9, 41, 42, 44, 45, 81 |
| Validation and boundary handling | 10 | 0, 49, 68, 70, 71, 72, 73, 88, 90, 92 |
| API, framework and observable-output compatibility | 7 | 17, 20, 33, 47, 82, 86, 91 |
| Transformation and numerical behavior | 4 | 23, 24, 83, 85 |
| Known diagnostic-span risk retained during coordination | 1 | 97 |
| Total | 29 | |

1. **Single-operation success is not lifecycle correctness.** Stream statistics,
   context callbacks and resource counters fail on reuse/close/reset paths.
   Saving a marked image changes a later supposedly unmarked save. These cases
   call for transition and repeated-operation checks, not just a happy-path demo.
2. **Boundary semantics dominate many failures.** Malformed tuples, empty names,
   defaults/environment inputs and unsupported algorithm names expose missing
   validation. Four Jinja pairs repeat the same invalid-priority-tuple symptom.
3. **Local implementations must honor framework contracts.** A function can
   appear to work yet have the wrong callback arguments, generic class interface,
   inherited attribute, logger message or error wrapper.
4. **Integration agreement is not semantic verification.** All 29 failed pairs
   merged successfully (28 identical patches, one clean merge). Matching hashes
   shows agreement on bytes, not correctness of behavior.
5. **These are not 29 independent mechanisms.** Jinja priority handling repeats
   four times, Click context reuse three times, and audio/email/hash cases recur.
   Frequency across pairs must not be treated as independent causal evidence.

## All Current Failures

Indices are zero-based. Test mismatches below describe what happened, not proof
that the assignment unambiguously specified every asserted detail.

| Index | Repository / task / feature | Current failure |
| ---: | --- | --- |
| 0 | outlines / 1655 / 6 | URL regex rejects localhost and localhost with port; assignment does not explicitly name localhost. |
| 7 | dspy / 8394 / 4 | Replacement attempt: prediction-integrated cache statistics expect one miss, observe zero. Compression feature5 now passes. |
| 9 | dspy / 8587 / 3 | Stream statistics fail to reset at stream end / allow-reuse. |
| 17 | go_chi / 56 / 1 | Diagnostic replay identifies TestMethodNotAllowed/Unregistered_Method and TestSetAllowHeader/Unregistered_Method failures. No model retry. |
| 20 | huggingface_datasets / 3997 / 2 | Custom decoding requirement expects true, receives false. |
| 23 | llama_index / 18813 / 5 | Audio/progress-callback case retains leading/trailing zero bytes. |
| 24 | llama_index / 18813 / 5 | Same audio symptom under another pairing. |
| 33 | click / 2068 / 10 | Nonexistent edit directory returns an error message different from the expected Editing failed wrapper. |
| 41 | click / 2800 / 2 | Exit callback runs during completion resolution and fails context-reuse behavior. |
| 42 | click / 2800 / 3 | Resource quota remains consumed after close. |
| 44 | click / 2800 / 2 | Context reuse invokes exit callback once rather than twice. |
| 45 | click / 2800 / 2 | Same context-reuse symptom. |
| 47 | click / 2956 / 1 | Argument still exposes auto_complete. |
| 49 | click / 2956 / 7 | Conflicting non-flags, defaults and environment values are accepted. |
| 68 | jinja / 1621 / 4 | Invalid priority tuple raises path-conversion TypeError instead of being ignored. |
| 70 | jinja / 1621 / 8 | Empty template name survives filtering. |
| 71 | jinja / 1621 / 4 | Same invalid-priority-tuple symptom. |
| 72 | jinja / 1621 / 4 | Same invalid-priority-tuple symptom. |
| 73 | jinja / 1621 / 4 | Same invalid-priority-tuple symptom. |
| 81 | pillow / 25 / 5 | Corner marking persists into a subsequent unmarked save. |
| 82 | pillow / 68 / 5 | Expected logger record missing and orientation-message wording differs. |
| 83 | pillow / 290 / 2 | Supplied-palette quantization yields 209 colors for maximum 10. |
| 85 | pillow / 290 / 4 | Error-threshold variant does not improve measured quantization error. |
| 86 | react_hook_form / 85 / 3 | Default-values callback receives no resolved object in sync/async cases. |
| 88 | dirty_equals / 43 / 3 | Email validator accepts user@domain.c, rejected by the test. |
| 90 | dirty_equals / 43 / 3, 7 | Same email case plus unknown hash algorithm not raising ValueError. |
| 91 | dirty_equals / 43 / 6 | Collection fails because IsCreditCard is not generic; not demonstrated Luhn failure. |
| 92 | dirty_equals / 43 / 7 | Unknown hash algorithm does not raise ValueError. |
| 97 | typst / 6554 / 10 | Correct unknown-unit message located at argument rather than whole-call span. |

## What Is Actually a Collaboration Problem?

Index97 provides direct transcript evidence of a coordination decision. Worker B
identified the span risk, prototyped an alternative, and then restored the old
export because worker A had submitted. Its submission at t=1006 explicitly
prioritizes identical patches. Worker A relayed the risk at t=1026; leader message
m25 at t=1057 acknowledged it and instructed no edits/resubmissions.

This was not failed message delivery. Information arrived and was understood,
but the team treated maintaining the current shared revision as more important
than revisiting the risk. The runtime permits both workers to synchronize a new
union and resubmit; it does not require keeping version1. This is evidence of
revision-management/decision weakness, not a hard collaboration restriction.

However, the assignment specifies error wording, not source span. Thus index97
also contains benchmark ambiguity. No counterfactual establishes that a different
team structure would pass. The remaining 28 observations do not by themselves
separate ordinary coding limitations from coordination-induced errors.

## Repairs No Longer Counted as Current Failures

- Index8: unchanged submitted code passes a new offline evaluation. Original
  fixture readiness timeout did not recur; its precise cause is unresolved.
- Index27: clarified-v1 resolves compress/compression naming and the new model
  attempt passes.
- Index7: the uncompressed-storage contradiction was clarified and feature5
  passes; the current failure is a different cache-statistics assertion.
- Index17: swallowed Go output was an engineering observability defect, now
  repaired. The revealed feature failure remains in the denominator.

The repaired cases do not establish that all remaining test contracts are sound.
Do not convert these symptom groups into an information-loss or MAS-causality
claim, and do not add prescribed coordination roles/strategies based only on this
post-hoc sample.

## Evidence

Canonical server scoreboard:
outputs/cooperbench/lite100-current/summary.json, under
/home/zhoujunye/MAS-information/. Each row identifies the effective frozen grade
and historical receipt. The new index7 attempt is repair-20261031-01/0; index27
is repair-20261031-01/1. Index17 diagnostic output is
lite100-20261030-04/17/diagnostic-grade-v9.json. Index97 trace is
lite100-20261030-04/97/trace.jsonl. Paths in this paragraph are relative to
outputs/cooperbench/.

Assignments and evaluator-only test patches remain in the pinned upstream
dataset. See [repair history](evaluation-repairs-20261030.md) for deviations,
costs, authorization and source digests. Historical audit wording remains in Git
history; the current documents no longer mix superseded and current failures.
