# Harness Engineering Notes

Historical measurements and reusable engineering lessons. Benchmark-specific
commands/paths below refer to retired adapters, not an approved current study.
The current target and remaining implementation gaps are in `leader-led-team.md`.

How the harness keeps runs comparable, cheap and auditable, and what was
measured. Sources: DeepSeek context caching
(https://api-docs.deepseek.com/guides/kv_cache/), pricing
(https://api-docs.deepseek.com/quick_start/pricing), both read 2026-10-29, and
the agent-team project's `docs/harness-cache-lessons.md`.

## Prompt cache

DeepSeek caches prompt prefixes on disk. Each request persists two prefix
units, at the end of the prompt and at the end of the model output; common
prefixes seen across requests and fixed-length chunks of long inputs become
units too. A later request hits only units it matches completely. Hits cost
$0.003 per million tokens against $0.15 for misses (Flash, off-peak), so reuse
dominates input cost.

What the harness does for it:

- Every agent context is append-only: system prompt, inputs, the provider's
  assistant messages verbatim (`reasoning_content`, `content`, `tool_calls`
  with the original argument strings) and tool results. The next prompt is
  therefore exactly the previous prompt plus the previous output plus new tool
  results, which matches the output-end unit.
- Stable text comes first: one `BASE` prompt shared by every role, then the
  role and relay text, then task input. Tool schemas are sorted by name. No
  timestamps, trace ids or random values appear in model-visible text (C3
  tool logs number their entries; C4 artifact ids are deterministic per run).
- Nothing is trimmed, reordered or padded to improve hit rates.

How it is measured (`analysis/cache.py`, reported by `scripts/analyze.py`):

- Token-weighted hit rate (hit tokens / prompt tokens) per condition, role
  (single, lead, worker) and call position (an agent's first call vs later).
- Every pair of consecutive calls of one agent is classified by what the next
  hit covered: `prompt+output` (verbatim passback reused), `prompt` (output
  not reused), `partial` (e.g. only the shared system prefix) or `miss`.
- The raw provider `usage` object is kept on every `llm_call` event.

## Cost

- `configs/base.yaml` holds the official price table. Weekday peak hours
  (01:00-04:00 and 06:00-10:00 UTC, i.e. 09:00-12:00 and 14:00-18:00 Beijing)
  cost twice the off-peak rate; `harness/accounting.py` applies this per call
  from its UTC timestamp. Large runs should start off-peak.
- Each batch appends the account balance before and after to `balance.jsonl`;
  the difference is the actual charge (other use of the same key in that
  window would be included).

## Errors

| Case | Handling |
| --- | --- |
| HTTP 400 (e.g. missing `reasoning_content`), malformed or interrupted response | run `error`, rerun by the next invocation, never scored |
| 429, 5xx, transport failure | up to 3 retries with backoff inside the client, then `error` |
| 400 for context length | run `incomplete` (`reason: context_length`): rerunning cannot help |
| 401, 402, 403 (key, balance, permission) | run `error` and the batch stops |
| `finish_reason: length` | cut-off tool calls answered "not executed"; one recovery reply (tools disabled, low effort) asks for the final answer or report; status `salvaged`, or `length` if it runs away again |
| turn limit | one forced reply with `tool_choice: none` |
| judge output unparseable | grade stays ungraded and is re-parsed or re-requested by the next grading run |

`harness.trace.validate` checks every trace: message indices without gaps,
each LLM call sent only logged messages, every tool call answered, every
assistant turn carries `reasoning_content`, every downward boundary message
answered, and a `final` event for completed runs.

## Retrieval throughput

All agents of all concurrent runs share one BM25 searcher behind a lock,
because concurrent Lucene access through the JVM is unstable. Documents are
long (median 110K characters, maximum 1.36M over the first 24 queries' top
hits), and tokenizing whole documents for the 512-token snippet dominated
search time (median 0.63 s). The snippet cut now encodes only a
16K-character prefix: byte-level BPE encodes pieces independently, so the
first 512 tokens are identical (200 real hits, 0 mismatches). Median search
plus truncation dropped to about 0.06 s. JSON parsing happens outside the lock.

`get_document` returns full documents, as the official clients do. A single
fetch averages roughly 27K tokens, so contexts grow quickly; requests beyond
the 1M-token context end a run as `incomplete`.

## Phase 0 measurements (BrowseComp-Plus, 2026-10-29)

`outputs/browsecomp_plus/phase0-20261029` on the server: 5 sampled questions
(`--sample 5 --seed 0`) x C0-C5, 30 runs, `deepseek-flash` with thinking at
high effort, BM25, budget 50. Run 05:58-06:31 UTC, mostly in peak hours.
Five questions test the pipeline; they say nothing about P1-P4.

Integrity: 27 completed, 1 incomplete (see output limit below), 0 provider
errors (no HTTP 400, so reasoning passback held), 0 trace-integrity problems.

Prompt cache, token-weighted:

| | C0 | C1 | C2 | C3 | C4 | C5 |
| --- | --- | --- | --- | --- | --- | --- |
| all calls | 88.2% | 83.6% | 83.1% | 66.2% | 84.2% | 94.2% |
| mean prompt tokens per run | 0.67M | 1.10M | 0.93M | 0.90M | 1.25M | 1.76M |

- Of 795 consecutive-call steps, 777 hit the previous prompt and output and 18
  only the previous prompt; none fell below it. Hits are rounded down to
  64-token blocks (e.g. prompt 13,396 + output 217 -> hit 13,568). Verbatim
  passback reuses the output-end unit as documented.
- Misses are new information: tool results, reports, briefs. An agent's first
  call hits about half its prompt (the shared system prefix, once seen). C3 is
  lowest because its lead reads full tool logs once (later calls 4.1%) and its
  workers' first calls carry the lead's notes (3.6%).
- Nothing in the harness breaks the cache; the remaining lever is how much new
  text a condition moves, which is the experimental variable itself.

Cost and time per run (estimates at the rates in force):

| | C0 | C1 | C2 | C3 | C4 | C5 |
| --- | --- | --- | --- | --- | --- | --- |
| USD | 0.040 | 0.160 | 0.108 | 0.172 | 0.136 | 0.074 |
| output tokens | 12K | 89K | 47K | 64K | 58K | 28K |
| wall seconds | 88 | 350 | 161 | 248 | 241 | 187 |

- Estimated $3.44 for agents and $0.12 for the judge; the balance fell by
  CNY 23.78 (about $3.3). Billing posts a few minutes late, so check the
  balance again after a batch. Estimates ran about 7% high.
- Team runs spend most output on the lead's reasoning (single calls of up to
  32K tokens and 190 s). Off-peak scheduling halves every number above.

Engineering problems found and fixed:

| Problem | Fix |
| --- | --- |
| Three calls (two C3 workers, one C3 lead) spent the full 32,768-token output on reasoning; the lead returned no answer and the workers empty reports | One recovery reply per cut-off call: cut-off tool calls answered "not executed", then a request for the final reply with tools disabled and low reasoning effort (`Agent.call_or_salvage`); a second cut-off stays `length`/incomplete |
| The judge sometimes answers as JSON (`"correct": "yes"`), which the official regexes miss (3 of 30) | JSON read first, official patterns after; stored judgements are re-parsed without new judge calls |
| Tool counts included calls refused after the budget ran out | Counted apart as `refused_over_budget` |
| Snippet truncation tokenized whole documents | Prefix encoding, identical output, about 10x faster |

Findings that need a design decision (not changed):

- Budget race: the shared budget ran out in 5/5 C1, 5/5 C2, 4/5 C3, 4/5 C4
  runs, against 2/5 C0 and 1/5 C5. Parallel search agents cannot see what the
  others spend; a follow-up dispatch then gets no calls. Options: show the
  remaining budget in every tool result (all conditions), or let the lead
  give each dispatch an allowance. Analysis now marks failures in runs whose
  budget ran out.
- Arrival criterion: search agents cite every relevant docid they saw, so the
  guide's "report cites the docid" rule makes R_arrive equal R_sys and L = 0
  in every team run. Measuring loss needs the stricter judge check of whether
  the key facts reached the lead.
