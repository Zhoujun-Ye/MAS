# Decision-Centered FULL

Historical decision-v1 design/receipt. Superseded by decision-v2; current Native
prompt composition, intermediate extraction and shadow grading are documented in
`docs/studies/intermediate-full.md`. Original replay conclusions below remain historical.

User-authorized design change, 2026-11-05. Replaces the active FULL tool interface,
not historical evidence. Frozen Structured remains the unchanged baseline.
Explicit FULL and OBS studies now use native organization plus tool contracts,
without the Structured orchestration prompt. Tool contracts describe serialization
and enforced API rules; they are not a new solver strategy or specialist roster.

## Enforced Mechanism

1. Capture successful, complete Bash observations. Parse standalone JSON objects
   with exactly `answer` or `final_answer`, matching the original submission type.
   Never mine all numbers from tables, reasoning or messages and call them answers.
   Reads, writes, messages, interrupted and failed outputs cannot create candidates.
2. Deduplicate equal typed answers and expose anonymous run-randomized IDs. Ordering
   is stable within a run, independent of agent identity and proposal frequency.
   Raw provenance stays private. The model may still recognize its own values;
   this is display blinding, not epistemic independence.
3. Lead selects from the current candidate snapshot. The API checks a verbatim task
   quote, a declared criterion and a comparison for each alternative. Missing or
   changed snapshots fail. The system does not grade the semantic validity of
   the criterion or comparisons and does not pretend to know the correct option.
4. PreToolUse checks complete Write submissions and rejects uncheckable partial
   Edit operations. Bash writes cannot be reliably policed by this hook. The host
   independently revalidates the final artifact after execution and before normal
   answer acceptance/grading, so bypassing the Write hook is not sufficient.
   Missing selection, pending execution, new candidate provenance, degraded capture
   or answer mismatch produce an incomplete protocol result, not an automatic fix.

Four lead tools: `decision_view`, `decision_read`, `decision_select`,
`decision_check`. Workers receive only view/read. Candidates are computed from
captured outputs; there is no model-written candidate value or ledger ceremony.
The old API remains available for historical fixtures, not advertised in active FULL.

## Important Boundaries

- `answer` means a producer-declared whole-task answer. This convention does not
  prove that two outputs estimate the same quantity. Units, population and method
  are not inferred by string matching. The original task and execution can be
  inspected, but source relevance remains a semantic judgment.
- There is deliberately no fallback that treats unparsed numbers as valid candidates.
  This can reduce coverage and reject otherwise correct submissions; measure it.
- The gate also requires a selection for a singleton. It blocks an unobserved final
  result, but cannot repair a consistently chosen wrong result. It does not implement
  multiverse execution, independent semantic adjudication or HDR budget allocation.
- No same-UID tamper-proof guarantee. A process that rewrites the store can subvert
  interface controls. Host verification protects normal artifact consistency, not
  adversarial OS-level provenance. No secrets or gold are mounted into this protocol.
- OBS now shares native organization, not the old Structured prompt. Old results
  are not matched controls for this changed protocol. Record new configuration
  hashes, repeat runs only with fresh authorization, and distinguish organization
  compliance, protocol compliance, coverage and accuracy.

## Replay Interpretation

`scripts/probes/replay_decisions.py` reads existing observer logs and reports without
opening their databases or executing captured commands. It emits aggregate counts
only, hashes source summaries, separates source batches (including Structured and
Native), and reads gold only after extraction for evaluation. Exact JSON matching
is narrower than the supplied review's heuristic numeric matching.

Historical runs have no decision-v1 selection receipt. Calling every run blocked
would be vacuous. Replay therefore measures parser coverage, conflicting candidates,
conflicts among recorded-correct runs, and submitted-value coverage. These are not
corrected accuracy or an actual counterfactual false-positive rate. Missing grades,
partial scores and absent submissions remain separate.

Source stage: `/home/zhoujunye/mas-stages/20261105-decision-full`.
No active deployment or paid experiment is authorized by this implementation.

First replay receipt:
`/home/zhoujunye/mas-data/receipts/decision-full-replay-20261105/by-condition.json`.
Three summaries contain 300 slots, including six interrupted DataClaw evidence
attempts. Krama contains 100 runs: the in-run reports label 65 correct, 24 incorrect,
and 11 ungraded/partial. These are not the supplied review's 30-error matched set;
no later grade reconciliation or approximate numeric matcher was applied.

The strict parser found candidates in 99/100 Krama runs. There were 9 conflicts:
8 in recorded-incorrect runs and 1 in recorded-correct runs. Critically, it found
the exact grade target in **0/24 recorded-incorrect runs**, and only one of those
24 submissions was absent from its candidates. Thus strict final-answer extraction
does not recover the intermediate alternatives identified by the broader review.
These data support neither accuracy gains nor a claim that the gate fixes those
errors. Richer, semantically typed intermediate result capture must be validated
before spending budget on this mechanism. Candidate coverage is not gold coverage.

## Verification

Final server pytest: **512 passed, 2 skipped in 13.69 seconds**; `git diff --check`
passed. Real pinned Claude Code with a strictly fake provider passed FULL and
OBS probes (12 and 14 synthetic requests, condition concurrency 2); both owned
containers were removed. Native lifecycle and four-tool decision wiring are verified,
not model quality. Final native receipt directory:
`/home/zhoujunye/mas-data/receipts/decision-full-native-20261105-precision`.
The native probe checks consistency/mismatch through the decision API; Write-hook
denial and host acceptance are covered by offline tests, not adversarial isolation tests.
