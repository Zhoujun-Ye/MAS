# Evidence MAS Implementation and Offline Verification

Date: 2026-11-05. Scope authorized by the user: implement observation/ledger
components, test offline on the server, and relocate reusable harness code out
of scripts. No paid calls, production deployment, environment installation or
remote source cleanup was performed.

## Ownership

- `harness/evidence_mas/`: our MAS observation store, analytical ledger,
  native-event collector, stdio MCP interface and pure configuration builder.
- `harness/runtime_support/`: relocated SQL/web tools, credential gateway,
  container byte bridge and native-runtime proof validation. Imports and source
  mounts updated; container-facing names and tool logic preserved.
- `scripts/`: benchmark, experiment and operational entrypoints. The existing
  mixed benchmark container/environment composition remains in common/runtime.py;
  frozen baseline prompts remain at their original paths and are unchanged.

No Independent Framer, automatic decision maker, executor or custom scheduler.

## Server Results

Live CPU/process ownership was inspected before testing. Existing evaluation
Python was used; no local tests were run. All source syncs used scripts/server/sync.sh
without --delete, targeting separate source stages, not the production project.

Final stage:
`/home/zhoujunye/MAS-information-stages/20261105-evidence-harness-offline-02`.

```sh
KRAMABENCH_UPSTREAM=/home/zhoujunye/MAS-information-data/kramabench/upstream \
  /home/zhoujunye/MAS-information-data/environments/evaluation/bin/python \
  -m pytest -q --junitxml=evidence-offline-tests.xml
```

Final result: **436 passed in 12.76 seconds**, zero failures, errors or skips.
37 tests cover the new evidence components directly; a new ownership test guards
against moving implementations back into scripts. The suite runs serially except
bounded four-client concurrency checks. No provider requests or Claude process
were needed. Existing fake-CLI tests remain part of the full suite.

JUnit receipt: `evidence-offline-tests.xml` in the final stage. An earlier
pre-relocation stage is preserved at
`/home/zhoujunye/MAS-information-stages/20261105-evidence-components-offline-01`;
its 435-test result is superseded by the fresh-stage migration verification.

Coverage includes event replay, incomplete and failed/cancelled observations,
blob integrity, bounded reads, run binding, execution/outcome correspondence,
evidence spans, unknown dependencies, recursive stale propagation, cycle rejection,
selection withdrawal, version conflicts, result reuse confirmation, version
history, concurrent writers and separate stdio processes sharing the same store.
Absolute entrypoints were exercised outside the repository cwd under Python -I.
Hook failures remain permission-neutral and emit a degraded receipt when possible.

Local `git diff --check` passed. Frozen adapters and prompt source are unchanged.

## Remaining Limits

The components run independently, but do not yet form an enabled production MAS
condition. Existing run_print rebuilds hooks and isolated CLI arguments specify an
empty MCP config. Native integration therefore needs an explicit merge path and
Claude 2.1.286 validation of worker tool visibility and per-role server binding.
Configuration fragments alone are not proof of that integration.

Stale status is derived recursively inside a transaction snapshot, so views after
a selection change immediately reflect invalidated dependencies without asynchronous
cache updates. Only declared dependencies are covered. Execution snapshots are
explicitly registered, not inferred completely from arbitrary shell commands.

Actor and role are interface metadata, not authenticated same-UID isolation.
Evidence validation proves reference/shape consistency, not semantic support.
No candidate coverage gain, selection improvement or end-to-end benchmark gain
has been measured. No native probe, solver run or grading run was launched.
