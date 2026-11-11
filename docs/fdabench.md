# FDABench: Local, Publicly Scoreable Tasks

## Scope

User-authorized scope (2026-11-10): integrate local tasks and infrastructure,
prepare server data and run offline tests. No paid solver, semantic judge, cloud
database account or cloud query is authorized. BigQuery/Snowflake are excluded,
including Spider2-lite instances starting with `bq` or `sf`.

Sources:

- [FDABench code](https://github.com/fdabench/FDAbench/tree/72e50a2b59798848a06ad30c5d8a39248c1228bf),
  pin `72e50a2b59798848a06ad30c5d8a39248c1228bf`.
- [Full release](https://huggingface.co/datasets/FDAbench2026/FDAbench-Full/tree/0e05e5ec2c95fbe462bed0cba1882f99989ab34e),
  pin `0e05e5ec2c95fbe462bed0cba1882f99989ab34e`.
- [Raw corpus](https://huggingface.co/datasets/FDAbench2026/FDABench-File/tree/9c88acf42f37a65c6aef8d06e1f6b6a1c24b7ca5),
  pin `9c88acf42f37a65c6aef8d06e1f6b6a1c24b7ca5`.

The pinned release has 2,007 tasks. The adapter admits **407** local tasks with
complete public scoring inputs: **101 single-choice, 201 multiple-choice, 105
reports**. In first-matching exclusion order, it excludes 761 missing choice
answers, 412 missing report rubrics, 9 incomplete report references, and 418 cloud
tasks. Counts describe the catalog, not data readiness or measured results.

Task identity is `task_id`, never the reused upstream `instance_id`. Task hashes
bind the full private source record, including references. Filtering depends only
on published inputs and database type, never a solver answer or obtained score.
There is no FDABench Validation20 set; the existing three manifests and default
matrix scope remain unchanged. Use `--benchmarks fdabench` explicitly.

## Data And Isolation

External server root: `/home/zhoujunye/mas-data/fdabench`.

```text
upstream/                         pinned evaluator/loader checkout, host-only
release/{report,single,multiple}.jsonl   host-only task and gold records
data/<database_type>/<db>/<db>.sqlite    selected file mounted read-only
data/corpus/                      raw public corpus, separate from task release
data/corpus-search.sqlite         derived local full-text index
data/corpus-receipt.json           raw file hashes, never solver-mounted
data/corpus-index-receipt.json     index/corpus binding and extraction limitations
```

Database filenames are exact, case-sensitive and family-namespaced. No fuzzy
database matching, unrelated database fallback, or silent web-only solving.
SQLite headers, symlinks, raw corpus inventory and index hashes are checked.
Missing required assets reject planning/preflight before model calls. No task
reference, rubric, gold subtask, gold SQL, explanation, frozen web/vector search
result or task-specific option evidence enters the prompt or solver mounts.

Database preparation uses the pinned HF Spider2 snapshot and pinned BIRD/Spider1
mirrors listed in `prepare.py`. The HF Spider2 snapshot is incomplete; the
[official Spider2 local pack](https://github.com/xlang-ai/Spider2/blob/cafb867313aab4e674652054198f383cf4018943/spider2-lite/README.md)
supplies four additional databases. A separately acquired `downloads/local_sqlite.zip`
is accepted only if its size and SHA256 match `SPIDER2_COMPLETE` in `prepare.py`.
Preparation fills exact-name gaps only, without replacing inputs already supplied
by the HF snapshot. The acquisition checksum freezes the downloaded official pack;
it is not a publisher-provided checksum or an independent byte-authentication claim.
There is no automatic Google Drive download or alternate-site fallback.
Receipts record provenance,
Git blob/LFS hashes, extracted archive members and resulting SHA256 values. This
does not assert independent byte verification against the original BIRD/Spider1
distribution. Unavailable databases remain explicitly missing; the adapter does
not construct the upstream custom DABstep database from reference answers.

Preparation defaults to server-direct `https://hf-mirror.com` for metadata and
asset GETs, with bounded download concurrency, TLS verification and content checks.
No Mac tunnel or environment proxy is used for these assets, and there is no
automatic fallback to the official site. `--hf-endpoint` selects an explicit
endpoint in both `prepare.py` and `prepare_all.py`. Solver web GETs still require
the existing private Mac Clash tunnel. The optional `--cdn-proxy-socket` is a
run-specific authorized exception for CDN hosts only: mirror/official root-host
requests remain server-direct, while CDN requests use the owned private Mac
socket with verified TLS and no bearer header. It is off by default; never
enable it silently. No model-provider key, embedding API,
native solver or judge is used. Existing differing
assets are not overwritten. A failed download can leave an unaccepted `.part` file.

## Retrieval Adaptation

The original raw corpus is exposed read-only. `harness/runtime_support/documents.py`
builds/searches a SQLite FTS5 index over PDF text and published text/transcripts.
Search is lexical, **not the upstream FAISS/dense-embedding pipeline**. Its receipt
reports parse failures/empty documents; no image OCR or new audio/video
transcription is performed. Raw media remains available but this does not establish
multimodal model competence. Corpus access and successful model incorporation are
different observations. These adaptations must be frozen/disclosed in future runs.

## Commands

Use the existing evaluation Python on the server. All setup commands below require
explicit `--execute`; ordinary catalog/run/score do not download or install anything.
Corpus indexing requires the optional `fdabench` dependency (`pypdf==5.6.0`,
matching the installed solver image). Installation is separate and uses the
Tsinghua PyPI mirror; no command below installs packages implicitly.

```sh
python scripts/fdabench/prepare.py --root /home/zhoujunye/mas-data/fdabench \
  --assets release databases corpus --workers 4 --execute
python scripts/fdabench/index_corpus.py \
  --data /home/zhoujunye/mas-data/fdabench/data --execute
python scripts/fdabench/catalog.py \
  --upstream /home/zhoujunye/mas-data/fdabench/upstream \
  --tasks /home/zhoujunye/mas-data/fdabench/release \
  --data /home/zhoujunye/mas-data/fdabench/data
```

`scripts/fdabench/run.py` uses the shared external-benchmark runner with `--upstream`,
`--tasks`, `--data`, explicit repeated `--task-id`, `--backend`, `--image`, and fresh
`--output`. Add `--web-search deepseek` for web-enabled tasks. The provisional
timeout is 1,800 seconds. Use a host-side `--asset-cache` outside mounted inputs to
avoid repeatedly hashing the large corpus; this is stat-validated reuse, not an
adversarial integrity guarantee. Native CLI proofs, permission policies, private
gateway accounting, no-network containers, preflight/from-plan binding, resource
limits, cleanup and no retries are inherited without changing the frozen lead prompt.

## Evaluation

`scripts/fdabench/score.py --run RUN --upstream UPSTREAM --tasks RELEASE --output NEW`
checks task/evaluator/submission hashes and scores choices without a provider.
The shared `final_answer` string must contain a JSON array of option letters.
Choice accuracy is exact set equality, with no partial multiple-choice credit;
invalid/duplicate/unknown letters and empty submissions score zero.

Nonempty reports require separate `--execute-judges --judge-limit N --judge-model MODEL`
authorization. N is exactly the number of nonempty report submissions, not all
tasks. One tool-free call uses the published four dimensions/weights and full
reference fields; SQL_ACCURACY is binary, the other dimensions are 0/0.5/1.
This is an **adapted transport/prompt**, not a claim to reproduce upstream clipped
multi-call judgments or permissive fallback parsing. Invalid/provider-error
judgments remain unknown and stop later paid calls; no retries. Empty reports
score zero without a call. Raw judge responses/accounting are retained host-side.

`metrics.json` reports separate single/multiple choice means and report rubric
means. There is no fabricated combined accuracy. DAG/tool metrics are null because
native trajectory-to-upstream-tool mapping is not validated. No paid accuracy or
generalization result is established by offline tests or data preparation.

## Background Preparation

`scripts/fdabench/prepare_all.py --root ROOT --output FRESH_RECEIPTS --execute`
runs download, index and catalog in order, with separate logs and an atomic
`status.json`. Failed stages stop the pipeline; no automatic restart, solver or
judge is dispatched. Reuse verified complete files, range chunks and partial
small files, with exact Content-Range and final pinned-hash checks.

The mirror can redirect file bytes to HF CDN hosts. Per-thread HTTPS reuse avoids
unnecessary TLS handshakes. Direct TCP connection establishment has one 20-second
address-list budget, at most two seconds per address and a short-lived preference
for a recently successful address; connected socket inactivity remains 20 seconds.
Transient asset I/O is bounded to five attempts with 2/4/8/16-second backoff.
Auth/integrity failures and all solver/judge calls are excluded from this policy.
Pending downloads are cancelled after a fatal error.

Gated FDABench-File access requires accepted access and
`--hf-credentials /home/zhoujunye/mas/.env`, a mode-0600 file containing `HF_TOKEN`.
Only its path appears in arguments. The user authorized the exact mirror host
for gated corpus authentication; public datasets and CDN redirects receive no
bearer header. Never export the token to child environments, solver containers,
logs or source provenance. The CDN-only Mac tunnel option requires separate
run-specific authorization and is off by default.

User linger is enabled for `zhoujunye`, so user services survive logout; transient
units are not a reboot-resume guarantee. A caught SIGTERM records `interrupted`.
SIGKILL/power loss can leave stale state, so inspect the live service as well.
`data/corpus-download-progress.json` counts verified completions in completion
order, including newly completed bytes and elapsed time. Its rate is not wire
throughput and excludes failed/unfinished traffic and reused complete files.

## Verified Server Readiness

On 2026-11-10, `mas-fdabench-prepare-20261110-mirror05.service` completed download,
index and catalog with four transfer slots, a two-CPU quota and 4 GiB memory limit.
That continuation used server-direct mirror/CDN access. A subsequent authorized
official-pack acquisition used the existing private Mac tunnel because Google
Drive was not reachable directly. These prepared files have no ongoing Mac
dependency. The current state remains **partial**, not fully ready:

- Corpus: all **2,097 files**, **11,462,362,473 bytes**; independent rehash found no
  missing/extra files, receipt mismatches or source-hash mismatches.
- Index: **1,536 documents**, **35,909 chunks**; SQLite quick-check, index/corpus
  hash binding and an actual read-only search passed.
- Extraction limitations: **11 parser exceptions**, **2 empty documents**, no OCR.
  These are not missing downloads. Individual paths remain in the index receipt.
- Databases: **24 of 25 required paths** passed read-only SQLite quick-check.
  **1 path remains absent**, affecting **22 of 407 tasks**; **385 inputs are ready**.

| Missing File (Relative To `data/`) | Affected Tasks | Pinned-Source Limitation |
| --- | ---: | --- |
| `dabstep/dabstep/dabstep.sqlite` | 22 | Upstream requires `merchant_data.db`, but the pinned FDABench release/repository provides neither that file nor a construction workflow; never reconstruct it from reference answers |

The complete pack supplied exact files for `California_Traffic_Collision`,
`bank_sales_trading`, `education_business` and `sqlite-sakila`, resolving 111 tasks.
Their absence from the HF snapshot was an acquisition gap, not proof of absence
from the benchmark's official sources. The original 20 databases and corpus/index
receipts/hashes were unchanged. ZIP member checks, source/archive hashes, read-only
SQLite checks and catalog validation passed; 940 server tests passed. No task
selection, scoring reference, frozen Validation20 set or paid-run scope changed.
Missing assets still reject preflight. File readiness is not retrieval quality
or solver accuracy.

Original full-preparation evidence is under
`/home/zhoujunye/mas-data/receipts/fdabench-infra-20261110/background-mirror05/`:
`status.json`, stage logs, `catalog.json`, `raw-asset-audit.json`, `final-audit.json`.
Its original 274-ready/133-missing result is preserved, not rewritten.
The current supplemental acquisition/import/catalog audit is under
`/home/zhoujunye/mas-data/receipts/fdabench-spider2-supplement-20261110/`, including
`acquisition.json`, `database-receipt-before.json`, `catalog.json`, `final-audit.json`
and full test receipts. The official archive was 456,643,204 bytes; its frozen
SHA256 and pinned guide revision have one source owner in `SPIDER2_COMPLETE`.
The data root owns `corpus-receipt.json` and `corpus-index-receipt.json` under
`data/`, plus the database/source receipts. Preserve these and the earlier failure
receipts rather than duplicating their logs in source documentation.

Earlier direct attempts saw intermittent CDN timeouts; mirror01 also stopped
with the user manager before linger was enabled. The user authorized CDN-only
Mac continuations mirror03/04, which retained completed files but suffered tunnel
disconnects. Mirror05 finished after direct access recovered and address-list
handling was repaired. The short mirror02 observation of approximately 10.1 MiB/s
net disk growth remains in `background-mirror02/transfer-observation.json`; it is
not a controlled speedup ratio or a full-run throughput claim.
