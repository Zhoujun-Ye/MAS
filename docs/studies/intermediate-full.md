# Executed Evidence and Decisions

## Active Contract

FULL uses decision-v4. It adds evidence tools to the existing Native organization,
not the frozen Structured prompt, fixed roles or a custom scheduler. OBS keeps
observation access and bounded delta delivery without decision tools. The retained
CPU8 results used decision-v3 and must not be relabeled as v4 results.

Bash computations can print an `answer`/`final_answer` JSON object, or explicit
measurement records produced by `harness.evidence_mas.measurements.measurement`:

```json
{"measurement":{"target":{"quantity":"distance","statistic":"sum","population":"routes","period":"not_applicable","unit":"m","dataset":"input-v1"},"value":12,"variant":{"missing":"drop"},"answer_target":false}}
```

Emit actual computed results, not an echo of the chosen answer. All six target
dimensions must be explicit; never fill unknown semantics with invented labels.
Use `variant` for analysis choices and `answer_target=true` only when the result
estimates the requested final target. Missing/invalid target contracts and weak
numeric hints are diagnostics, not automatically selectable answers.

Only successful, complete Bash observations contribute final candidates. Read,
Write, failed/truncated execution and incidental numeric occurrences are not
final-answer evidence. All declared final answers compete across interpretations;
duplicate executions are not votes.

## Sharing

Native SessionStart/SubagentStart and terminal tool hooks can emit bounded
cross-context deltas: up to three observations and 1800 characters per update
(6000 including initial guidance). Exact repeated execution payloads are delivered
once per recipient; originals remain accessible, without voting by execution count.
Recipients never receive their own outputs again. Per-recipient transactional
cursors prevent duplicate emissions and preserve overflow for later hooks.
Previews include executed structured-result summaries where available; full
input/output remains accessible through bounded observation reads.
No extra model calls, scheduler, polling loop or automatic recomputation is added.

Native Bash overflow previews are `pointer`, never `complete`. The raw hook result
is preserved separately from a bounded snapshot of its native tool-results file.
`obs_read(field="persisted_output")` pages that snapshot, including its tail;
summaries and deltas expose availability. Only regular, nonsymlink `.txt` files
under this run profile's `claude/projects/*/tool-results/` tree are eligible, with
an exact native byte-size check and a 4-MiB limit. Unavailable, unsafe, changing or
oversized artifacts remain pointers with a reason, not invented complete output.
The native file can contain combined streams, so it is not reconstructed stdout
and does not automatically create final candidates or satisfy complete-execution
review. Same-UID mutation remains outside an adversarial security boundary.
Nested native interruption/truncation flags also exclude incomplete results.
Observation reads accept either `start/end` or `start/limit` (1..16000
characters), not both `end` and `limit`. This preserves the original absolute-span
API while matching the count-based pagination used by decision reads. It does
not change which accesses qualify for decision review.

The data is explicitly untrusted. Hook emission is recorded separately from
model access and does not prove receipt, understanding or causal reliance.
If a native context lacks workspace MCP tools, its normal native result can
return executed findings and references; the harness does not invent tools.

## Four Decision Tools

- `decision_view`: anonymous final candidates, explicit intermediate contrasts,
  current snapshot and pagination. No frequency-based vote.
- `decision_read`: task, candidate execution or explicit intermediate group;
  text and source pagination are explicit. Lead candidate accesses are recorded
  with actor, candidate review token, snapshot and exact observation revision.
  Complete reads of unchanged candidates survive unrelated snapshot changes;
  changed interpretations require fresh access. View/read expose exact `next_read`
  arguments. `next_start` pages text; additional source executions are optional
  after one complete execution has been accessed. Final selection remains bound
  to the global current snapshot.
- `decision_select`: lead only. Access each conflicting candidate's execution
  first, then supply a verbatim task quote, criterion and comparison for every
  alternative. Worker reads or previews do not satisfy this access check.
- `decision_check`: compare the exact submission to the current selection.
  New candidate values, target interpretations or analysis variants stale the
  old selection; identical duplicate results do not. Pending executions block
  live completion. The host rechecks after owned-container teardown.

Singletons still need no selection ceremony. Missing candidate coverage remains
unknown, not a correctness pass. Empty answers are incomplete. A task-grounded
explanation and evidence access are not a semantic correctness proof; wrong
choices can still be consistent. Failed gates do not suppress independent shadow
grading. No semantic chooser or submission repair runs automatically.

Current protocol/configuration hashes are bound to fresh native offline proofs.
Older proofs cannot admit the repaired implementation. Original v3 artifacts are
read-only, never migrated or rewritten.
