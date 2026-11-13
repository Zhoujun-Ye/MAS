# Native vs Single Causal Probes

This directory contains only the opt-in mechanism study. Structured is excluded.
The baseline organization prompts, normal adapters and recorded paid results are
unchanged. After review the user authorized fixing the bugs and launching thirty
questions, three rounds, with the additional prompt-only brief control.

## What The Traces Establish

The three retained Native/Single rounds have raw means 72.22% / 60.56%. The
task-cluster bootstrap 95% interval for their difference is [-5.56, 28.33]
percentage points, with exact task sign-flip p=0.2461. This is an exploratory
phenomenon, not an established population effect. There are twenty task clusters,
not sixty independent questions. Two Single rounds are reused, not contemporaneous.
Five Native attempts encountered the old async-delegation gate race.

`audit.py` reads only Native and Single. It preserves all raw scores and provides
a separate whole-task sensitivity view for audit/race/infrastructure issues.
Of sixty Native first workers, 56 have a recorded terminal report; eight reports
mention lead answer artifacts. These are review flags, not automated proof of
contamination. Manual checks confirm that reports can include computed candidate
answers and can refer to an already written lead submission. Historical reports
are therefore not clean independent reconnaissance donors.

## Frozen Design

Each of thirty frozen questions is attempted once per arm per round. The existing
twenty remain; ten are sampled from the remaining pinned public workload without
replacement, seed 20261112, without consulting scores or selecting discordant tasks.
Seeds 0, 1, 2 determine dispatch order only, not provider sampling. Every round
has 180 solvers and thirty independent recon sessions; total 540 + 90 sessions.
The judge cap is the actual eligible question count x six arms x three rounds,
frozen before launch, with one call per cell and no retry.
The completed November 12 study used thinking disabled, temperature 1.0,
CPU8/thread4, task deadline 3600s and zero retries. Fresh plans bind the current
fixed default (now T=1.0), never rewrite those historical settings, and require
new paid authorization. Failed attempts, donor failures, partial costs and raw scores are retained.

| Arm | Intervention | Identifiable Contrast |
| --- | --- | --- |
| `single` | Current strict Single | Contemporaneous control |
| `native` | Current Native prompt and corrected mandatory-delegation gate | Contemporaneous control |
| `null_worker` | Every Agent/Task request is redirected to a native no-tool worker given only a fixed empty-report instruction | Total Native ablation after removing task-specific worker information, not a unique mediation decomposition |
| `recon_transplant` | Single receives its same-task/same-round independent frozen recon receipt | Availability of this report and its delivery context; donor compute is additional |
| `self_brief` | Single must use Write to create `brief.md` before Bash, with nonempty Task/Qualifiers/Sources sections | Brief instruction plus enforcement as a package, not the gate-only effect |
| `brief_prompt` | The exact same brief instruction, with no Bash gate | `self_brief - brief_prompt` isolates incremental enforcement; `brief_prompt - single` measures instruction |

Null-worker uses the unmodified native Agent definition and runtime, not a simulated
Agent result or a custom agent description. Native tool definitions remain visible
to the worker, but every worker tool execution is denied by the read-only hook.
It receives neither the original delegation prompt nor
its description/resume context; follow-up SendMessage contents are also replaced
by the same empty-report request. All worker terminal reports must equal
`<empty_report/>`; deviations are recorded, never automatically repaired or
retried. Free proofs require byte-identical initial lead requests (except native
session/device metadata) in Native and null-worker. Timing and returned content
still change, so
similar scores are not proof that only the lead's process explains Native gains.
An equivalence claim needs a prespecified margin and sufficient precision.

Independent recon has a fresh isolated Single workspace, the same read-only
input lake, no lead artifacts, no reference answers and no networking. Its report
schema contains task qualifiers, candidate source paths/columns/units/relevance,
and uncertainties. Physical paths/schema are validated, not semantic truth or
absence of implicit derived answers. The full independent report is frozen before
E2 starts. Only status and report content enter the prompt: task IDs, donor session
IDs and accounting metadata remain host-only. An invalid report blocks native Stop
with the same validator used host-side, so recon may repair it within that one
session. A failed donor is injected as an explicit unavailable receipt, and E2
still counts in intention-to-treat analysis. No historical or best-scoring donor
is selected. Direct model-generated solution content must remain an audit
limitation, not be silently filtered using gold answers.

The brief gate validates file structure only, not reasoning quality. Both brief
arms receive identical instructions, including literal headings without colons
and the 16384-byte limit; only the enforced arm denies premature Bash.

## Execution And Safety

- `runtime.py` and `hooks.py` contain study-only adapter customization. Hooks,
  policy and shared recon validator are read-only container mounts, not writable
  observer files. This provides integrity, not adversarial arm blinding: a
  shell-capable solver may inspect mounted files. Normal
  Krama execution calls the original adapter unless an explicit factory is supplied.
- `trial.py` owns one isolated session and its native teardown. It cannot dispatch
  without a matching parent journal claim and reviewed execution marker.
- `run.py` defaults to a no-call plan. `--prepare` checks source, task, image,
  binary, input hashes and a source-bound free proof for all six roles.
- Rounds are work-conserving across seeds. Up to sixteen solver/recon/replay sessions
  and two grader threads overlap, sharing sixteen CPU reservation slots. Task and
  arm order are seeded/interleaved. Each E2 enters the ready queue immediately
  when its own recon finishes; no all-recon phase barrier or per-arm serialization.
- Judge claims are reserved before dispatch and never refunded on uncertain
  failure. No retry/resume or best-of-N path exists. An exclusive controller lock,
  SQLite journal and one-shot marker protect irreversible work.
- The completed T=1.0 run's one-time host-controller handoff is historical only.
  Its implementation and amendment remain in frozen provenance
  `20261112-causal-dispatch-overlap-01`; active code no longer offers handoff,
  process adoption or continuation flags. E4 paired lead replay is a separate
  prespecified intervention, not controller recovery.
- Nonfatal HTTP5xx/transport errors and model deviations are recorded but do not
  truncate the assignment. No response, solver or judge is retried. Integrity,
  key/balance, unknown execution and cleanup failures stop new dispatch. Fatal
  credentials/operator termination stop owned children. In-flight cost can remain
  unknown; account monitoring is not a provider hard monetary cap.

Free commands (existing server evaluation Python, no real provider calls):

```bash
PY=/home/zhoujunye/mas-data/environments/evaluation/bin/python
$PY -m scripts.studies.causal_experiments.audit --run /path/to/retained-run --output /fresh/trace-audit.json
$PY -m scripts.studies.causal_experiments.free_probe --output /fresh/free --execute
$PY -m scripts.studies.causal_experiments.run --output /fresh/study --proof /fresh/free/proof.json --prepare
```

Paid execution requires `--review-confirmed`, the exact
`--reviewed-plan-sha256`, exact 540/90/eligible-judge authorization and a positive total
cost estimate. Any source/proof/input change invalidates preparation. Existing
baseline admission proofs cannot stand in for the new study proof, and the
synthetic study proof cannot admit ordinary baseline launches.

## Preregistered Analysis

`plan.json` freezes null-worker minus Native as the primary contrast, alpha .05,
using thirty task clusters (three rounds averaged within task), exact two-sided
task sign-flip and a task-cluster bootstrap 95% interval. Native-Single,
recon-Single, brief-gate versus prompt-only and prompt-only versus Single are
secondary, with Holm-adjusted p-values. Raw intention-to-treat means include
every assigned task; unknown execution/judge outcomes remain unknown, not zero.
Protocol-filtered results are secondary and use the same tasks in every arm.

No equivalence conclusion follows from a nonsignificant result. Thirty tasks
improve coverage but do not guarantee adequate power to decompose an 11.7-point
difference. The experiment is exploratory mechanism evidence, not unique causal
mediation. Packet availability, non-submission rate, delegation count and observed
report-to-submission timing are secondary outcomes. Bash-based write timing and
unobserved incorporation remain unknown.

## E4 Premise Replay

The authorized T=0.7 study adds ten targeted tasks, three brief variants and three
repeats: ninety worker-role sessions and ninety paired lead continuations. These
are separate from the six-arm ITT, for 810 new sessions in total and at most 72
one-call judges (six-arm eligible tasks only). Each E4 session has 900 seconds.

`e4_prepare.py` freezes one historical first-delegation prefix per task, eight
suspect/hedged hypotheses and two correct-premise controls. A verbatim brief,
exact-span open-question rewrite and original-task-only prompt share a JSON
reporting footer. Fresh native main sessions select the recorded built-in role
and tool restrictions; they regenerate a primary-session system prompt rather
than claiming bit-for-bit reproduction of the original subagent request.

Each entire returned report goes to its own resumed lead at the identical first
Agent/Task boundary. This fixes immediate delivery, not historical asynchronous
timing. No final workspace, pipeline, submission or later transcript is copied.
Prefixes with earlier successful command/file/planner mutations are rejected.
Only unchanged original task guidance is restored. Unavailable/malformed reports
remain in the assignment without repair, report selection or retries.

Native fake-provider proofs cover both worker role surfaces and all ten resumed
lead prefixes before paid admission (`--e4-manifest`, `--e4-proof`, and an explicit
`--authorized-e4-sessions 180`). Historical delegation outside the continuation's
hook window is not a missing-delegation error; the baseline audit is retained but
marked inapplicable to this intervention. Verification, premise stance and answer
correctness are separate measurements. Stance/evidence need trace coding, not
keyword labels; correct-report/wrong-final alone does not establish uptake loss.

Worker `strict_candidate_score` measures final-answer formatting/matching, not
semantic report correctness; `score` remains unknown until evidence-backed coding.
`e4_semantic.py --run RUN --output FRESH_PACK` exports all ninety reports and
trace references. With `--pack PACK --coding CODING --output FRESH_ANALYSIS`, it
validates complete, quoted coding and writes a separate semantic overlay. Original
grades/traces are hash-checked before and after, never rewritten. Partial answers,
abstentions, ambiguity and unavailable reports remain separate from incorrectness.
This workflow makes no provider, judge or pipeline calls.
