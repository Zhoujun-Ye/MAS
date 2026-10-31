# Lite 100 Failure Audit

Read-only post-run audit of all 31 failed grade records, with targeted inspection
of assignments, hidden test patches, submitted patches and communication traces.
This is not an exhaustive review of every model turn or an execution-based causal
diagnosis. No model calls, paid retries, test reruns or score changes were made.

## Main Findings

- The original result remains 69/100 joint evaluation passes and 100/100 protocol
  completions. The other 31 are failed evaluations, not 31 demonstrated agent
  coding failures or collaboration failures.
- All failed pairs merged successfully: 30 identical-patch merges and one clean
  merge (index 42). Successful merge and matching hashes do not establish semantic
  correctness. Several failures concern lifecycle, validation and API edge cases.
- Two assignments have concrete specification/test discrepancies: index 27's
  `compress` versus `compression` keyword, and index 7's uncompressed storage
  representation. These should not be attributed to communication loss.
- Index 8 failed during test fixture startup, not a feature assertion. Index 17
  lacks a useful failing-test diagnostic. Their root causes remain unresolved.
- Index 97 provides direct evidence of a coordination decision preserving a
  known risk to retain identical submissions. This was not a runtime prohibition
  on revision, but the evaluator's diagnostic-span expectation is also absent
  from the assignment. This is a mixed case, not clean causal proof of MAS loss.

## Concrete Evidence

### Specification/Test Discrepancies

Index 27, tiktoken task0 feature9: the assignment explicitly requests a new
`compress` parameter. The submitted patch implements `compress: bool = False`
and adjacent-token deduplication. The hidden test instead invokes
`enc.encode(text, compression=True)`, causing an unexpected-keyword TypeError.
This is a direct interface discrepancy, not evidence that the worker forgot the
requested parameter. Supporting both names might pass, but that does not make
the undisclosed alternate name part of the original assignment.

Index 7, DSPy task8394 feature5: the assignment describes pickle, optional
compression, header prefix, then write; its header explicitly includes codec
0x00 for no compression. The failed test directly reads `disk_cache[cache_key]`
and requires the uncompressed value to be an object with a `message` attribute.
The submission stores header-prefixed bytes. The test's storage expectation is
in tension with the stated format; returned objects otherwise pass the nearby
round-trip assertions. Do not conflate this with the separate cleanup incident.

### Evaluation Uncertainty

Index 8, DSPy task8587 features1/4: both suites record a setup TimeoutError because
a local fixture server did not become ready within 10 seconds. Other tests pass
(14 and 20 respectively). The retained grade excerpt does not establish whether
startup failed from load, a dependency, or submitted code. Earlier admission
success does not exclude a later runtime problem. Conversely, a timeout alone
does not prove infrastructure was at fault.

Index 17, go_chi task56 feature1: the runner exits 1 with parsed counts 0 passed,
0 failed, but retained output exposes the test invocation rather than the actual
assertion. Feature5 passes. Diagnosis is blocked by missing failure detail.

Consequently, the results report's zero *run-level recorded* infrastructure errors
must not be interpreted as proof of zero evaluator-side problems. Top-level
status and nested test setup errors are different measurements.

### Coordination Lock-In: Index 97

The Typst workers adopted one shared union patch. Worker B identified that
`unknown unit` errors were located at the argument rather than the call expression,
prototyped a different implementation, then restored the old exported bytes
because worker A had already submitted. Its submission report at trace t=1006
explicitly says the risk was retained to preserve identical patches.

Worker A relayed that risk at t=1026. At t=1057, message m25, the leader accepted
the risk and instructed worker B not to edit or resubmit because a new revision
could break the byte-identical freeze. The hidden failure is precisely the error
span mismatch, not an incorrect error message or word/grapheme result.

The runtime supports reopening and resubmission, and the worker template says
writes/terminal commands reopen automatically. Both workers could have agreed
on a revised union and resubmitted; there is no requirement to keep version 1.
Thus the transcript supports a coordination/revision-management weakness rather
than a hard harness ban. However, the assignment specifies error wording, not
the source span. No counterfactual run was performed, so we do not claim that a
different organization or prompt would have passed.

## All Failed Pairs

Indices are zero-based official selection indices. A feature marked below is
the failing feature, not necessarily the only feature in the pair. Descriptions
are observed mismatches, not an exclusive or causal classification.

| Index | Repository / task / failing feature | Observed failure |
| ---: | --- | --- |
| 0 | outlines / 1655 / 6 | URL regex rejects localhost and localhost with a port; 2 failures. Localhost is not explicitly named in the assignment. |
| 7 | dspy / 8394 / 5 | Uncompressed storage expected to hold an object, but contains header-prefixed bytes; specification/test discrepancy above. |
| 8 | dspy / 8587 / 1, 4 | Fixture server readiness timeout in both suites; cause unresolved. |
| 9 | dspy / 8587 / 3 | Stream statistics are not reset at stream end or allow-reuse; expected 0, observed 3/2. |
| 17 | go_chi / 56 / 1 | Nonzero test runner with missing assertion detail; unresolved. |
| 20 | huggingface_datasets / 3997 / 2 | Custom decoding requirement test expects true, receives false. |
| 23 | llama_index / 18813 / 5 | Audio resolution/progress callback case retains leading/trailing zero bytes rather than expected trimmed bytes. |
| 24 | llama_index / 18813 / 5 | Same failing audio case under a different feature pairing. |
| 27 | tiktoken / 0 / 9 | Test uses compression; assignment and implementation use compress. |
| 33 | click / 2068 / 10 | Nonexistent editing directory produces a different error message; test requires Editing failed. |
| 41 | click / 2800 / 2 | Exit callback runs during shell-completion context resolution and fails repeated-context reuse behavior. |
| 42 | click / 2800 / 3 | Resource quota remains consumed after close; reuse raises Maximum number of resources exceeded. |
| 44 | click / 2800 / 2 | Reused context invokes on-exit callback once rather than twice. |
| 45 | click / 2800 / 2 | Same context-reuse failure under another pairing. |
| 47 | click / 2956 / 1 | Argument still exposes auto_complete where test requires its removal. |
| 49 | click / 2956 / 7 | Conflicting non-flags, defaults and environment values are accepted; expected exit 2, observed 0. |
| 68 | jinja / 1621 / 4 | Invalid priority tuple reaches path conversion and raises TypeError instead of being ignored. |
| 70 | jinja / 1621 / 8 | Empty template name survives filtering. |
| 71 | jinja / 1621 / 4 | Same invalid-priority-tuple failure. |
| 72 | jinja / 1621 / 4 | Same invalid-priority-tuple failure. |
| 73 | jinja / 1621 / 4 | Same invalid-priority-tuple failure. |
| 81 | pillow / 25 / 5 | Saving once with corner marking affects a subsequent save without marking; expected original pixel, observed red. |
| 82 | pillow / 68 / 5 | Two logger tests fail: missing expected record and different orientation-message wording. |
| 83 | pillow / 290 / 2 | max_colors with a supplied palette returns 209 colors despite requested maximum 10. |
| 85 | pillow / 290 / 4 | error_threshold variant produces the same measured error as baseline, not the required improvement. |
| 86 | react_hook_form / 85 / 3 | Default-values callback receives no values where sync/async tests expect the resolved object. |
| 88 | dirty_equals / 43 / 3 | Email validator accepts user@domain.c, which the test rejects. |
| 90 | dirty_equals / 43 / 3, 7 | Same email case plus unknown hash algorithm not raising ValueError. |
| 91 | dirty_equals / 43 / 6 | Collection fails because IsCreditCard is not generic; this is API integration, not demonstrated Luhn failure. |
| 92 | dirty_equals / 43 / 7 | Unknown hash algorithm does not raise ValueError. |
| 97 | typst / 6554 / 10 | Correct unknown-unit message at the wrong source span; known risk retained to preserve identical patches. |

Repeated feature failures are not independent evidence: Jinja feature4 occurs
four times, Click task2800 feature2 three times, and the audio/email/hash cases
also recur. Pair-level 31/100 failure therefore must not become a claim of 31
different failure mechanisms.

## Interpretation and Next Diagnostic Work

The strongest implementation-level signals concern lifecycle reset, unintended
mutation, missing validation and API compatibility. They do not by themselves
identify an information-transfer mechanism. The Typst exchange shows information
was delivered and acknowledged, but the team chose not to act on it. That is
different from information being lost in transport or unavailable in isolation.

Prioritize evaluator diagnostics and separate assertion failures, collection
errors and setup errors in downstream reporting. Adjudicate specification/test
discrepancies separately while preserving the original 69/100 score. Any future
causal experiment needs a declared comparison; do not silently rerun failures,
replace samples, change hidden tests or prescribe a collaboration strategy based
on these post-hoc observations. No such follow-up was executed in this audit.

## Evidence Locations

Server root: `/home/zhoujunye/MAS-information/`.

- Indices 0..9: `outputs/cooperbench/lite100-20261030-03/<index>/`.
- Indices 10..99: `outputs/cooperbench/lite100-20261030-04/<index>/`.
- Each directory: `manifest.json`, `grade.json`, `trace.jsonl`, and frozen
  `worker_a.patch` / `worker_b.patch`. Index42 uses raw `test_output` rather than
  `output`; a diagnostic extractor must support both keys.
- Assignments/tests: `benchmarks/cooperbench/upstream/dataset/<repo>_task/task<N>/feature<F>/`
  with `feature.md` and evaluator-only `tests.patch`.
- Revision semantics: `harness/agent_team.py` domain_tool/update_task,
  `harness/pool.py` worker instructions; joint merge contract:
  `benchmarks/cooperbench/adapter.py` EVALUATION_CONTRACT.

Original outputs were not modified. Tests and paid runs were not rerun.
