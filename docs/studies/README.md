# Current Protocols

The Structured lead prompt remains frozen in
`scripts/common/prompts/structured_subagents.py`. Its UTF-8 SHA-256 without the
trailing newline is
`31ff6e4176a25d961866f644adb4d7b97cb4b00228e696c0e4e38a52b9485a95`.
The lead receives organization instructions; worker-visible rules contain shared
task limits, not Structured lead organization. Tests pin the exact baseline.

- [Active Single/Structured infrastructure](evidence-infra.md)
- [Prepared Krama Single/Native/Structured random20 study](krama-random20-20261111.md)
- [FDABench Single/Structured four-question smoke](fdabench-smoke4-20261110.md)
- [FDABench CPU8 matched rerun](fdabench-cpu8-rerun-20261110.md)
- [Three-benchmark infra check](threebench-infra-20261111.md)
- [Full manifests, crash recovery and resource admission](fullscale-infra.md)
- [Web transport, shared successful-call budget and empty-answer scoring](web-infra.md)
- [Retained Krama CPU8 results, trajectory diagnosis and paired speed checks](krama-history.md)
- [Three-benchmark engineering smoke](threebench2-engineering.md)
- [Single/Structured/FULL smoke and deterministic regrade](threebench2-20261109.md)
- [Historical FULL capture, DNS and read-interface audit](full-infra-20261110.md)
- [Frozen validation questions](validation20.md)
- [Retention and deletion boundaries](../archive.md)

FULL and OBS are retired; their documents above describe retained history only.
Defaults remain strict Single and the unchanged Structured prompt. The explicit
Krama `native` study adds only the approved minimal delegation prompt, not a
retired runtime. Its random20 selection does not replace frozen Validation20.
No document or offline proof authorizes paid execution.
