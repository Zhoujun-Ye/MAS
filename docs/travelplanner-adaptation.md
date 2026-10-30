# TravelPlanner Candidate Adaptation

Retired on 2026-10-29 at the user's request. This file records historical
adaptation evidence only; source, launchers and tests are no longer active.

Prepared 2026-10-29. Status: **offline integration verified, main-study admission
pending**. The latest user requirements supersede the original PDF's retired
BCP/tau2 selection and its treatment of Full Context as a performance upper bound.
Historical P1-P4 thresholds have not been edited or applied to fixture results.

## Why This Candidate

TravelPlanner's [official two-stage setting](https://github.com/OSU-NLP-Group/TravelPlanner)
requires executable database search followed by constrained planning. It starts
with a complete request. Flights, lodging and meals/activities admit independent
work but share dates, destination, party size and budget. A worker can discover
a minimum-stay or transport-cost constraint that changes another worker's choice.

Selection is outcome-independent: all validation tasks with `days == 3` and
`visiting_city_number == 1`: **60 tasks, 20 easy / 20 medium / 20 hard**. No
5/7-day tasks, synthetic truncation or failure-selected subset. This primarily
tests constraint retention and cross-source synthesis, not stateful writes or
long dependency chains. Three travel days do not imply three agent turns.

The [original paper](https://arxiv.org/abs/2402.01622) evaluates older models.
No verified public score matches our current backbone, tool-use split and budget;
therefore **non-saturation remains unknown**, not established by historical scores.
This is a candidate preparation, not a declaration that all admission gates passed.

Other screened options: [DSBench](https://github.com/LiqiangJing/DSBench) is deferred
because multimodal/large-table/modeling tasks and evaluation adaptation make cheap
short execution less certain. [MARBLE](https://github.com/ulab-uiuc/MARBLE) is an
architecture reference, not an adopted orchestrator. WorkBench and the retired
benchmarks are not reintroduced. We do not add more adapters merely to fill three
task-category labels without verified fit and cost.

## Native Assets and Changes

- Code revision: `e52c87f4ac348a3410c46dc3553c519db5ec5e23`.
- Environment data revision: `f2183898e2b9547ed2a6f5356ae4cbc3f3431bf4`.
- Dataset revision: `8736504ecfc31b7f8b7e40122873c337e83fff7c`.
- 19 files, **312,518,961 bytes**: native source/license, validation CSV and full
  flights, lodging, restaurants, attractions, distances and background tables.
- `assets/prepared.json` records SHA-256 for every file. HF LFS SHA-256 or Git
  blob hashes are verified on download. The backend rechecks files before import.
- Server HF direct access failed and its mirror refused/rate-limited requests.
  Download completed from official pinned URLs locally, then only this candidate's
  assets/upstream were transferred to the server and verified there. No secrets,
  environments, old datasets or outputs were copied or removed.

The five exposed tools call official local APIs, not a fabricated search tool.
Pagination returns complete rows, total counts and next offsets; every page is
charged as a domain call. No LLM Planner, online maps, global notebook, hidden
reference bundle or grader is exposed to agents. All receive the complete public
query and output schema. Grading fields remain outside their contexts.

The native scorer runs in a separate process because its imports change cwd and
load data globally. Its three required pure utility functions are imported via
an AST whitelist to avoid the unused Gradio annotation UI. Native files are not
edited. The process has a clean environment without provider credentials and
Python socket connections are disabled. This is not an arbitrary-code sandbox.

Final answers must be direct JSON; no GPT-4 postprocessor is used. Record all
native commonsense/hard checks, native success and independent audit success.
The native 3-day scorer incompletely checks requested destination and flight
date; supplemental audits test those separately. These audits are not a complete
new travel feasibility verifier. Unexpected scorer/backend exceptions remain
ungraded, never silently scored as wrong. Invalid JSON/shape is an answer failure.

## Frozen Team and Treatment

Eight worker templates are available plus Leader; this candidate activates only
Researcher (transport), ConstraintAnalyst (lodging/feasibility), DataAnalyst
(meals/attractions), and Leader (coordination/final itinerary). All selected roles
have the same five read-only domain tools from the versioned search binding.
No agent is artificially deprived of the public task or a needed domain tool.
Rule selection is free and performed once. This is the fixed-team routing baseline
for this task family, not evidence of a learned task-adaptive selector.

Across forms, one TeamSpec/control digest freezes roles/prompts, assignments,
model configuration, domain schemas/permissions, all-peer graph, round-robin
scheduler and limits. The runtime rejects reuse for another public request.
Workers can directly send to peers, receive follow-ups and continue their own
append-only histories. Leader alone emits the team final answer.

Full Context delivers the complete sender snapshot; Summary and Structured use
an encoding call on a copy. Retrieval adds explicit grants to original tool
observations and real read tools. Adaptive adds recipient-aware encoding and
exact-fragment search over granted evidence. All edges, including automatic
worker-to-leader completion reports, use the same selected treatment. This is a
minimal static Adaptive baseline, not semantic retrieval or self-evolution.

Default caps: 20 shared domain calls, 32 total model calls **including encoding**,
16 messages, 8 evidence reads, 200,000 input characters. Same caps do not imply
same actual tokens. Read text appears in subsequent inputs; never count an ID as
semantic arrival. End-to-end trajectories can diverge; pure serialization/causal
claims still require a separate frozen-boundary replay experiment.

## Unpaid Verification

Server: `/home/zhoujunye/MAS-information`. Dependencies already existed; no package
installation or paid provider call was required. Optional dependencies are listed
under `.[travelplanner]` for fresh environments. Tests use scripted clients or
HTTP MockTransport and reject Python socket connections.

`scripts/travelplanner/offline.py` creates a new immutable output directory with
the selected task IDs, frozen TeamSpec, source/data hashes, five full traces,
grades and a summary. It uses real native tools and a deterministic known-plan
fixture, **not real-model reasoning**. Synthetic usage is explicitly labeled and
semantic loss is unknown. The test also checks a zero-budget negative fixture.

First completed smoke: `outputs/travelplanner/offline-team-20261029-01`.
All five forms completed and passed trace integrity with one control digest.
Each used five native domain calls. Full Context made 13 scripted calls; the
other forms made 18, including encoding. Total tool-result text was 15,498 chars
for the first three forms and 20,669 for retrieval/adaptive due to actual reads.
These numbers describe the fixture, not expected model efficiency or accuracy.

Final verification after implementation changes: **60 tests passed in 14.88s**
on the server; exit status 0. The second immutable smoke directory is
`outputs/travelplanner/offline-team-20261029-02`, also exit status 0, with the same
five completed forms and control digest `60ce5e600e7bbdc7`. It additionally saves
the full frozen control record and Python/dependency/fixture-client provenance.
Native positive and negative scoring fixtures passed. Paid calls: **0**.

Before any paid pilot: approve a monetary/call scope, freeze the model identity
and prompt versions, independently review task decomposition, define ceiling/
floor and cost admission criteria, and reserve disjoint pilot/main task IDs.
Current-model headroom, causal loss, cache benefit and the need for RSI are open.
