# Attribution from Collaboration Traces

## Scope and Causal Limit

This follow-up inspects peer-message and submission records across the current
29 failures, with deeper reads of selected exchanges, assignments and test
failures. It is a targeted trace audit, not exhaustive coding of every model
thought or tool execution. No new execution, paid judge, model call or score
change was performed. The current score remains 71/100.

An owner-local implementation defect, failure of team review to catch it, and a
coordination decision that preserves it can coexist. Failure to rescue a bug is
not proof that collaboration caused the bug. Likewise, one failed implementation
does not establish an agent's intrinsic inability to solve the task. No matched
solo counterfactual exists in this study, so a numeric split into individual
versus MAS-caused failures would be unjustified.

References below use trace event t, not line numbers. Server root is
/home/zhoujunye/MAS-information/outputs/cooperbench/. Unless noted otherwise,
index N refers to lite100-20261030-04/N/trace.jsonl. Index0 is in segment03;
current index7 is repair-20261031-01/0, not the superseded segment03 attempt.

## Direct Coordination Evidence

### 81: Known Mutation Risk Frozen to Avoid Divergence

Worker B explicitly disclosed that corner marking mutates the source image
(t=488, 507). Leader t=536 records that risk but declines a design change because
both features need the same shared bytes and a late redesign risks divergence.
Leader t=774 again records source mutation as residual risk. The actual failure
is a marked save contaminating a later unmarked save of the same image.

This supports a concrete risk-to-action failure: information reached the leader,
but revision coordination cost was a stated reason not to change the code.
The original mutation choice came from the worker, and nonmutation was not
spelled out in the short assignment. Both owner interpretation and collective
freeze policy matter; it is not an unconfounded MAS-only failure.

### 97: A Prototyped Alternative Was Abandoned

Worker B's submission t=1006 says a call-span alternative was prototyped, but the
original argument-span implementation was restored to match worker A's frozen
bytes. Worker A relays the risk at t=1026. Leader t=1057 explicitly agrees to
retain the implementation and forbids further edits/resubmission. The hidden
failure is exactly the diagnostic span mismatch.

The runtime allows reopening and coordinated resubmission. The obstacle in the
record is the team's decision, not an inability to transport the code. The
assignment specifies wording but not span, so the benchmark ambiguity remains.

### 41: Cross-Feature Behavior Tested with the Wrong Expected Outcome

The context-closing feature interacts with the on-exit hook. Worker B t=894
reports that completion invokes on_exit, calls it benign/correct, and reports
passing scratch checks. The leader requests a check on the real combined tree,
not just a mock. Worker A t=1016 confirms one callback during completion and
labels the semantic checks successful. Leader t=1044 accepts this outcome.
The hidden test expects no callback during completion.

This is not merely an absent integration test: integration was exercised and its
observed result was accepted under a shared, different expectation. A second
failure in this pair concerns context reuse and a once-per-context guard. Both
features have lifecycle assumptions. Causal contribution of combining them
still requires standalone-component replay; the transcript alone does not prove
the owner would have passed alone. Completion suppression is also not explicit
in the short on_exit assignment.

### 42: An Unresolved Interpretation Became a Team Contract

Leader t=735 asks whether closing contexts frees resource capacity. Worker B
t=894 chooses a lifetime cumulative counter and explicitly tests that close does
not free capacity. Worker A t=966 accepts that this does not affect its own
completion fix. Leader t=1014 treats it as the owner's documented design choice
and requests no further change unless the existing merged tests fail. The hidden
test fails on resource reuse after close.

The team correctly discussed the uncertainty. It did not independently establish
the expected lifecycle semantics. Agreement that another feature is unaffected
was insufficient evidence that this feature's requirement was met.

## Owner-Local Omissions and Review Limitations

- **23/24, audio:** the assignment says the callback runs after resolution and
  trimming. Reports emphasize resolved/raw byte counts and reset buffer position
  (23: t=560,590; 24: t=528,613); the grade fails on retained zero bytes. This
  looks like incomplete requirement interpretation by the owner, carried into
  team verification. There is no evidence a correct trimming implementation was
  removed by a peer. It is not proof of message loss.
- **83, max_colors:** worker A explicitly reports leaving the palette branch
  untouched (t=1713). Worker B reports the max_colors code was imported verbatim
  (t=1659). The failing case supplies a palette. This points toward an owner-local
  branch-coverage omission that cross-review missed, rather than merge damage.
- **47, auto_complete:** the owner reports implementing it on Parameter
  (t=1652), while the assignment is about Option. The peer independently verifies
  the feature (t=1660), but the hidden failure is Argument inheriting the
  attribute. Again, independent execution did not independently validate scope.
- **7, cache statistics:** worker A's final evidence includes direct cache
  counter checks (t=987); worker B explicitly distinguishes its own checks from
  the owner's reported suites (t=900). The hidden failure is prediction-integrated
  miss accounting, not compression or merge. This suggests a verification gap;
  the inspected records do not establish its introduction by collaboration.
- **91, credit card:** the team debates Luhn length restrictions (t=954,1026),
  but the actual grade fails during collection because the class is not generic.
  Do not mistake a salient disagreement for the cause of the observed failure.

These are candidates for owner-local error, not measured solo-agent limitations.

## Shared Assumptions and Remaining Ambiguities

The following exchanges give evidence about the team's expectations, but not a
clean individual-versus-team causal split:

| Indices | Trace evidence and attribution limit |
| --- | --- |
| 0 | Owner submission t=1268 explicitly rejects localhost; leader t=1314 accepts it as an assumption. Assignment does not explicitly name localhost. |
| 9 | Owner t=1466 and peer t=1474 both claim/reset-test statistics; grade disagrees. Need reconstruct the exact test path, not infer loss from the failure. |
| 17 | Owner t=1213 discloses unknown-method Allow-header limits; peer t=1221 checks PUT on a GET route. Specific unsupported-method handling was not established by that check. |
| 20 | Owner t=1461 reports permissive criterion dispatch; peer t=1351 calls APIs a reasoned superset. Custom-criteria failure needs call-contract reconstruction. |
| 33 | Owner t=816 explicitly chooses the missing-directory error wording; test expects the Editing failed wrapper. No evidence peer integration changed it. |
| 44,45 | Owners t=1104 / t=1446 choose once-per-context behavior; peer checks reinforce it. Reentering a reusable context is a distinct lifecycle case. |
| 49 | Owner t=887 explicitly excludes defaults/envvars from conflicts. Peer history tracking includes these sources (t=864), but that does not establish conflict semantics. |
| 68,71,72,73 | Same priority-feature failure across partners. At 72 t=1089 and 73 t=816, TypeError for malformed tuples is explicitly tested as expected. The spec's gracefully/treat-as-path wording and the hidden ignore expectation need adjudication. |
| 70 | Owner t=847 reports filter semantics; empty-name handling fails. No inspected message identifies a peer-induced change causing it. |
| 82 | Peer t=1323 reports passing logger checks. Assignment does not specify the exact orientation string asserted by hidden tests. Do not classify that solely as coding incompetence. |
| 85 | Peer t=1268 reports combined threshold/lightness checks; the actual threshold test finds no improvement. No trace-backed causal attribution yet. |
| 86 | Both workers explicitly use Noop/no-argument callback semantics (t=1138,1205). Assignment specifies callback timing but not its payload; hidden tests require resolved values. This is a remaining benchmark ambiguity. |
| 88,90 | Email-format assumptions are explicit (88 t=256; 90 submission t=975). One-letter TLD expectations are not independently justified by the inspected specification. |
| 90,92 | Hash error timing differs from hidden expectations; at 92 t=762,771 the owner intentionally chooses no constructor raise and tests False comparisons. Unknown-name constructor behavior is not explicit in the assignment. |

This table plus the preceding cases covers all 29 current failures. None is
assigned a definitive causal percentage. Remaining ambiguity is a research
confound; it does not silently change the operational 71/100 scoreboard.

## Counterexample: Collaboration Also Corrected Errors

Index83 contains a useful within-trace positive case. Leader t=1079 identifies
that a brightness check cannot distinguish RGB sum from luminance, rejects the
current patch, and requests discriminating primary-color examples. Worker A
t=1230 acknowledges the earlier assertion allowed RGB ordering OR brightness
ordering and replaces it with a discriminating test. At t=1235 it also spots an
editable-install issue that could make a baseline/modified comparison import
the same code. Leader t=1294 requests a real baseline recheck.

The pair ultimately fails on max_colors, but its collaboration successfully
detects and corrects other verification problems. Thus pair failure alone would
hide beneficial collaboration. This is a reason to study decision episodes,
not just whole-task success labels.

## Research Directions

### 1. Acting on Known Risk Under Shared-Revision Constraints

Mechanism hypothesis: once a shared artifact is synchronized/submitted, teams
discount a recognized semantic risk because changing it requires coordinated
revision and revalidation. Direct examples are 81/97; 42 illustrates accepting
an unsettled interpretation rather than resolving it. This is not a transport
loss hypothesis.

Candidate mechanism to study: link an explicitly raised risk to its supporting
evidence, chosen disposition, artifact version and revalidation obligations.
This need not prescribe who solves/reviews or force every risk to trigger edits.
Compare against the unchanged team and an equal-budget generic review reminder.
Measure detected-risk-to-discriminating-test rate, correct disposition, avoidable
rework, regression introduction, tokens and latency. Falsifier: risks are mostly
unfounded, or a neutral reminder performs equally well, or any benefit disappears
under matched review effort. Do not claim the ledger is novel by itself.

### 2. Independent Verification Criteria, Not Repeated Verification

Mechanism hypothesis: peers rerun code in separate workspaces but inherit the
author's expected answers, so multiple successful checks provide correlated
evidence. Cases41/42/72/73/92 show consciously accepted expectations differing
from the evaluator; 83 shows how a discriminating test can improve review.

Compare a peer deriving behavioral expectations from the same authorized task
text before seeing the proposed solution against deriving tests after seeing it.
Keep accessible information, model, pool, permissions and total budget matched;
the varied mechanism is the ordering/provenance of verification, not a new role
roster. Include equal-budget single-agent self-review. Measure bug detection,
mutation-test discrimination, expectation overlap, false alarms and final passes.
Falsifier: independent derivation does not improve discrimination or only helps
when given extra task information. Ambiguous tests must be independently
adjudicated before treating agreement with the evaluator as ground truth.

### 3. Semantic Composition Across Lifecycles

Case41 suggests testing behavior across two features' event ordering, not just
union of their isolated happy-path tests. The first diagnostic is an offline
replay of owner-only and integrated artifacts at the same base with the same
tests; this can separate introduced interactions from pre-existing defects, but
not establish a solo model's ability. Follow with controlled task variants only
if an interaction is actually identified. A generic instruction to test more
is an essential baseline. No such replay or new study was executed here.

## Prior Work and Novelty Boundary

[CooperBench](https://arxiv.org/abs/2601.13295) already discusses communication,
commitment and expectations about teammates. Our provisional focus is narrower:
observable risk dispositions and the independence of verification criteria,
including cases where messages are delivered accurately and commitments kept.
This is a possible angle, not an established gap.

[Demystifying Multi-Agent Debate](https://arxiv.org/abs/2601.19921) studies initial
viewpoint diversity and calibrated confidence. Merely proposing diversity or
more debate is not a sufficient distinction; code artifacts, test discrimination
and revision-bound evidence would need to add measurable value.

[More Debate, Same Evidence](https://arxiv.org/abs/2608.00243) is adjacent work on
homogeneous verification panels. Its abstract also explicitly notes model
differences prevent isolating a causal debate effect. These are preliminary
nearest-work checks, not a systematic novelty review.

## Smallest Credible Next Study

First freeze decision-point annotations and adjudicate ambiguous specifications
without exposing evaluator-only material to solution agents. Reconstruct
intermediate owner/union artifacts where available for offline diagnosis. Then,
under separately authorized paid scope, compare the unchanged team, an
equal-total-budget single agent handling both features, and one narrowly varied
verification/revision mechanism. Keep successful matched controls, multiple
seeds, unsuccessful attempts and costs. Split by repository/task/feature group,
not by pair, to avoid repeated-feature leakage. These already inspected 100
pairs are exploratory material, not untouched confirmation data.
