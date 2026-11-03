# Scoped evidence-judge pilot: results

## Conclusion

The revised prompt substantially reduced observed time and retained-message
usage on this 24-task historical paired pilot, without changing any task's
score. It did not improve accuracy. This supports testing bounded judgment as
an efficiency intervention; it does not establish the absence of cold-start
costs, reduced anchoring, or generalization beyond this selected pilot.

Exactly 24 new solver attempts and one semantic answer judge were run, with
no retries or replacements. All 24 CLI runs exited normally, all 24 native
SubagentStart/Stop lifecycle audits passed, and all 24 pipelines passed the
separate no-network replay. No live experiment containers remain. The server
offline regression passed 177 tests before launch.

## Protocol and provenance

- Prompt: `docs/prompts/subagents-evidence-judge-v1.md`.
- Preregistered design: [pilot protocol](scoped-judge24-pilot-20261103.md).
- Selection: six domains, two easy and two hard tasks per domain, using a
  frozen SHA-256 ranking of IDs without scores or answers. 18 tasks have
  binary scores; six have continuous scores.
- Existing baseline: `outputs/current/runs/claude-code-subagents-20261102-01`.
- New run: `outputs/current/runs/claude-code-scoped-judge24-20261103-01`.
- Reports: `outputs/current/reports/scoped-judge24-20261103-01`.
- Source stage: `/tmp/mas-scoped-judge-source.EkRgPF` on the server.
- Baseline summary SHA-256:
  `08384c38e82c73499e2970e24a978fe6cf6930e0e71647bacec6243e2f308862`.
- New summary SHA-256:
  `df9cd008d840bf0bbb2a7c5dc269c268aabf1ee739c136fb84bb22f744631057`.
- Prompt SHA-256:
  `f62c009b6f0882d4a076a1c29c33397a3f977c0cb597b394ccd002d5c481ad93`.

The comparison script checked identical task instructions, scoring contract,
input hashes, image, model, effort, concurrency, timeouts, CPU/memory, tool
options, native environment and CLI binary hashes. It checked submission file
hashes against effective grades in both conditions. The default organization
prompt was not changed; the new condition uses an explicitly frozen override
at the benchmark layer, with no native adapter or scheduler changes.

Run interval: 2026-11-03 10:40:51 to 11:06:25 UTC, including initial admission,
solving, offline collection and scoring. Do not compare this batch duration
against a hypothetical historical 24-task batch: those tasks originally ran
as part of a 104-task workload.

## Paired results

| Measure | Original Subagents | Scoped judge | Change |
| --- | ---: | ---: | ---: |
| Binary correct | 12/18 (66.67%) | 12/18 (66.67%) | 0 pp |
| Continuous-score tasks | 6 | 6 | All six scores unchanged |
| Mean CLI seconds/task | 484.73 | 260.23 | -46.31% |
| Median CLI seconds/task | 401.87 | 185.92 | -53.74% |
| Retained output tokens | 2,344,535 | 881,757 | -62.39% |
| Leader output tokens | 824,415 | 677,807 | -17.78% |
| Child output tokens | 1,520,120 | 203,950 | -86.58% |
| Off-peak retained-message USD estimate | 2.047414 | 0.826695 | -59.62% |

All 24 recorded CLI times are lower; legal-easy-25 differs by only 0.21 seconds,
which should not be interpreted as a meaningful individual speed gain. Mean
time ratio is 1.86x old/new. The output-token reduction is not just a transfer
of child generation to the parent: parent output also fell in aggregate, though
individual tasks can still incur more producer work.

Binary transitions: 12 correct-to-correct, six incorrect-to-incorrect, zero
rescues, zero regressions. The six continuous scores are: three list-exact F1
scores of 1, one approximate-list F1 of 0, and two numeric-approximate scores
of 0.907692 and 1; all are unchanged. Only one of the 24 literal answers changed:
archeology-hard-5, from 36828.7165 to 36815.2633. It still scores 0 under the
unchanged reference. See `comparison.json` for all task-level pairs.

Costs are estimates from retained usage, not invoices. The new account-wide
solver balance interval decreased by CNY 5.44 and may include unrelated account
use. The single judge's displayed balance delta was CNY 0.00, not evidence
that it was free. Native Claude costUSD is not used as provider billing truth.

## Mechanism observations

| Measure | Original | Scoped judge |
| --- | ---: | ---: |
| Child transcripts / root Agent calls | 44 / 44 | 24 / 24 |
| Median child observed work seconds | 199.064 | 33.423 |
| Median tool calls per child turn | 21 | 0 |
| Total child tool calls | 1,075 | 16 |
| Median final report words | 794.5 | 169 |
| Child turns with at most 3 tool calls | 0/44 | 24/24 |
| Child turns with at most 250 report words | 0/44 | 24/24 |
| Zero-tool child turns | 0/44 | 16/24 |
| Median first-dispatch seconds from parent first message | 87.533 | 121.946 |
| Median received child prompt words | 258.5 | 977 |
| Median received child prompt characters | 1,878 | 6,900 |

Every new task used one child; no follow-up turn was observed. The 16 actual
tool calls were inspected: they comprise targeted workbook metadata/header
reads, a variable dictionary, data-directory listings, and documentation
lookups. These are not complete alternate solution pipelines. This does not
prove that every missing hypothesis or necessary source was checked.

Child work time is the interval from its first retained ordinary message to
its last assistant text. It excludes time before the first message, so it
cannot measure or rule out cold-start overhead. Report words are whitespace
tokens, not model tokens. The old and new child medians concern different
numbers and types of child tasks, not matched identical workers.

In 22 cases an explicit parent Write to submission.json is observable; all
22 child final texts precede it. The other two are unknown by this detector.
Writing a submission is not necessarily the first answer computation or the
moment of psychological commitment. No earlier-arrival or anchoring claim is
made from this proxy alone.

The received prompts are LONGER than the old child prompts: a compact evidence
packet is not equivalent to fewer prompt tokens. The intended reduction was
relative to forwarding the full producer trajectory, which was not a baseline
condition. Native contexts are not hard-isolated by this study.

Common task instructions: 936 characters in both conditions. Organization
instruction: 375 old vs 5,845 new characters. Token-weighted cache reuse:

| Role | Old input/cache-hit tokens | Old reuse | New input/cache-hit tokens | New reuse |
| --- | ---: | ---: | ---: | ---: |
| Leader | 41,149,249 / 39,875,968 | 96.91% | 32,753,919 / 31,669,504 | 96.69% |
| Child | 33,385,244 / 31,821,184 | 95.32% | 463,782 / 201,344 | 43.41% |

Low child cache reuse now accompanies far fewer calls and tokens. A high cache
hit rate alone was not a useful efficiency objective. Retained accounting
exists for all 24 tasks per condition, but native helper/failed-request usage
can still be missing.

## Why this does not yet establish better judgment

The children returned 18 candidate selections, five UNRESOLVED verdicts, and
one REJECT_ALL. These are local decisions, not final task correctness labels.

1. **Candidate coverage can retain the producer's framing.** In
   environment-hard-16 the packet compares Community+Beach Name (75),
   Beach Name alone (74), and treating n/a as unsafe (74). It does not include
   the physical-beach-versus-`@`-sampling-station consolidation investigated
   by the old run. The new child uses zero tools and endorses 75. Removing
   historical narrative does not remove dependence on which alternatives and
   observations the parent chose to provide. The old consolidation candidates
   are not asserted to be uniquely correct or to resolve the reference.
2. **Final adjudication still resides with the parent.** In biomedical-hard-8
   the child returns REJECT_ALL because genes are not sites and an available
   contrast is not endometrioid-restricted. The parent checks these claims,
   performs the requested restricted recomputation, then explicitly rejects
   the child's final recommendation and submits CDK12/SMARCA4, matching the
   reference. This is not a proven parent error, but it means the experiment
   did not transfer final decision authority to an independent judge.
3. **A local semantic repair need not change benchmark score.** In
   archeology-hard-5 the child returns UNRESOLVED while confirming the BP
   direction. The parent explicitly selects the chronologically later, smaller
   BP value, correcting the earlier direction choice but not the entire
   discrepancy with the reference answer. Do not label this a benchmark rescue
   or infer it was caused by the report without a checkpoint intervention.
4. **Short reports can still have long reasoning intervals.** The final
   biomedical child took 267.082 observed seconds for one tool call and a
   140-word report. Its parent dispatched at 751.404 seconds; that task still
   took 1270.95 seconds overall. Prompt brevity does not cap internal reasoning
   or producer exploration.

The strongest present claim is reduced computation at unchanged observed
scores. A next experiment should separate bounded scope from the change in
agent count, test missing-candidate discovery, and define how unresolved or
contradictory judgments are handled. Equal-protocol Single and randomized,
repeated runs remain necessary before an architectural or causal paper claim.

## Evidence files

- `comparison.json`: matched configuration checks, hashes, all 24 scores/times.
- `mechanism.json`: full received child prompts, final reports, tool inputs,
  physical source line anchors and transcript hashes for both conditions.
- `outcome-transcripts.jsonl`: observable parent/child records for the three
  detailed cases, excluding thinking blocks, with submission hash checks.
- `selection.json`: frozen selection rule, task IDs and baseline hash.
- `mechanism-interim.json`: retained incomplete snapshot, NOT final evidence.

Analysis utilities: `scripts/kramabench/scoped_subagents_pilot.py` and
`analysis/scoped_judge_audit.py`. The first ran from the frozen server stage;
the second was executed read-only over server artifacts after the run. No
post-run prompt tuning, reference modifications, dropped attempts or extra
solver/judge calls were performed.
