# Krama Random20: Three Independent Repeats

`scripts/studies/krama_repeats.py` repeats the existing frozen Random20 questions
in Single, Native and Structured: 20 questions x 3 conditions x 3 rounds = 180
solver attempts. It does not select new questions or replace failed attempts.
This is a repeatedly used development set, not an independent final test.

The initial `krama-random20-three-repeats-20261112-01` batch was stopped by the
user after 59 completed first-round solvers and one interrupted solver. Six judges
ran; rounds two/three were not started. The user subsequently deleted that batch's
Native/Structured result payloads, retaining its complete twenty-task Single,
frozen pre-gate source and all incurred accounting. Its observed shared-account
delta was CNY8.83 at stop, not a final invoice. Never resume the pruned batch.
Current new plans bind the
[mandatory-delegation gate](../cli-adapters.md#mandatory-delegation), not that old run's policy.

The separately authorized `krama-random20-forced-repeats-20261112-01` reuses two
complete, independently identified T=1.0 Single rounds: `krama-random20-20261112-01`
and the stopped batch's `round-01-seed-0`. It runs one missing Single round and
three fresh rounds each of Native/Structured: **140 new solvers, at most 14 judges**,
zero retries, no monetary cap, continuous monitoring. Source stage:
`20261112-krama-forced-repeats-01`. Historical Single is not contemporaneous with
the new MAS; report that limitation, rather than claiming a simultaneous comparison.
The authorized 140 new solvers and fourteen judges have completed with no retries;
the authorization is consumed. Equal-weight raw means across three rounds are
60.56% Single, 72.22% Native and 61.11% Structured. Nine MAS attempts encountered
the later-fixed async Agent-return/SubagentStart race. Corrected read-only audit
diagnostics retain nineteen shared tasks, excluding `wildfire-easy-3` everywhere
because its native background-shell exit omitted SessionEnd. Preserve raw paid
scores/audits and distinguish this batch from any future corrected-harness run.

## Settings

- Thinking disabled, temperature 1.0, effort none; no loop guard.
- Exact frozen prompts, common 3600-second task deadline, CPU8/thread4.
- Default seeds 0, 1, 2 deterministically shuffle whole task groups. They are
  **dispatch-order seeds only**, not provider sampling seeds. The pinned CLI has
  no verified model sampling seed interface. Repeats remain stochastic.
- Rounds execute sequentially; within each round 16 solvers overlap with two
  graders, sharing the existing CPU reservations. No 48-solver oversubscription.
- Each attempt has an independent workspace, native session and output directory.
  No retries, recovery, best-of-three selection, or automatic resumption.
- Semantic judges are disabled by default. `--with-judges` plans at most six
  one-call judges per round (18 total) for the two eligible frozen questions.
  Execution additionally requires explicit authorization for this scope. The
  matrix reserves each judge slot before dispatch, including uncertain failures.
- `--reuse-single FIRST_BATCH SECOND_BATCH` validates two complete, audited,
  scored twenty-task Single rounds with matching inference/resources/prompts and
  distinct native session identities. Their artifacts are hash-bound, not copied
  or regraded. New dispatch is 40/40/60 solvers across the three rounds, with
  judge caps 4/4/6. All three actual Single observations count once; retained
  costs are reported separately from new expenses. Missing or changed evidence
  blocks dispatch, and pruned results never become an automatic retry scope.

## Free Preparation

Run on the server from an isolated source stage, using current free native proofs:

```bash
PY=/home/zhoujunye/mas-data/environments/evaluation/bin/python
$PY -m scripts.studies.krama_repeats \
  --output /home/zhoujunye/mas/outputs/krama-random20-three-repeats-NEW \
  --proofs /absolute/path/to/current-proofs
```

The default command validates the frozen public task hashes and prints a plan.
It creates no output directory, reads no credentials and dispatches no model calls.
Add `--prepare` for free image/binary/environment/tool-proof checks and an immutable
source/scope plan with three protocol files. Select `--with-judges` at preparation
if separately authorized paid execution will include semantic grading.

Preparation is not authorization. The initial November 12 request covered code
and free validation only. The subsequent cleanup-and-launch request explicitly
authorizes one 180-solver run and at most 18 one-call semantic judges, zero
retries, with no monetary cap and continuous monitoring. Its output prefix is
`krama-random20-three-repeats-20261112-01`; the isolated source is
`20261112-krama-three-repeats-run-01`. Previous paid authorizations are consumed.

## Separately Authorized Execution

After obtaining run-specific authorization and a cost estimate, use the identical
prepared options with `--execute --authorized-attempts 180`, a positive total
`--estimated-cost`, and `--authorized-judges 18` if prepared with judges (otherwise
zero). This estimate plus the existing 1.5 safety factor and CNY5 account reserve
is balance admission, **not a provider-enforced spending cap**. A requested monetary
cap requires its own monitoring plan before launch.
With `--reuse-single`, authorize exactly 140 new solvers and 14 judges instead
(zero judges when disabled); the retained forty Single attempts incur no new calls.

All source, task, configuration, image, CLI and proof bindings are checked again.
Each round reuses the existing matrix admission and monitoring. Fatal provider,
balance, infrastructure or incomplete-result failures stop later rounds; no paid
work is repeated. A fully recorded model/native-audit failure remains in the data
and does not by itself prevent subsequent independent rounds. SIGINT/SIGTERM is
forwarded to the active matrix and its cleanup is awaited. An exclusive controller
lock and one-shot execution marker prohibit accidental relaunch/resume.

## Reports

`--report` reads existing artifacts without runtime checks or paid calls. Execution
also writes `repeat-report.json` and durable per-round progress/exit receipts.

The report includes each round's condition mean, the equal-weight three-round
mean and sample standard deviation, and per-question **score** consistency. Score
consistency is not answer or trajectory agreement. Missing/unknown scores never
become zero or silently leave the denominator; aggregate means stay unknown until
all required scores exist. Missing semantic grades therefore keep the corresponding
full-set means unknown when judges were disabled.

The additional paired native-audit view uses one shared task cohort across all
nine round/condition combinations: one failed or unknown audit excludes that
question everywhere. Raw results remain intact. Per-round accounting retains
known partial cost estimates, unknown request counts and account-wide deltas;
it is not presented as a complete invoice. Do not compare these repeated T=1.0
results directly with historical T=0/guarded protocols as an organization effect.

## Free Verification (November 12)

Isolated server source: `/home/zhoujunye/mas-stages/20261112-krama-three-repeats-01`.
Receipts: `/home/zhoujunye/mas-data/receipts/krama-three-repeats-20261112-01`.
The full server suite passes **1060 tests, no skips**, including pinned upstream
integration checks. Synthetic execution covers all 180 cells, zero automatic
retries, bounded per-round judge authorization, launch/incomplete-result failure,
interrupt cleanup, changed source/proofs/protocols, duplicate launch rejection,
missing scores and shared paired cohorts. Credential/network access is denied in
tests. Real server preparation additionally checks all frozen public task hashes,
the installed image/CLI and current native tool/environment proofs, without model
or judge dispatch. This does not establish real-model variance reduction; that
requires a separately authorized paid three-round run. Production is unchanged.
