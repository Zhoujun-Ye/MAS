# Codex CLI Adapters

Version pin: **0.159.3**. Claude Code remains available at **2.1.286**.

- `harness/codex_single_agent/`: native multi-agent features disabled; the mounted
  Single model catalog also clears `multi_agent_version`.
- `harness/codex_subagents/`: native multi-agent features enabled; Codex owns delegation.
- `harness/_codex_cli.py`: shared arguments and raw JSONL transport.

The server binary comes from the official npm platform package, checked against
registry SHA-512 integrity. The full platform directory is mounted read-only:

```text
/home/zhoujunye/MAS-information-data/environments/codex-0.159.3/package/vendor/x86_64-unknown-linux-musl/bin/codex
```

DataClaw/HDR use native Responses via the host credential gateway. The container's
`DEEPSEEK_API_KEY` is an ephemeral run token, not a provider key. Real credentials
remain host-side in the protected `.env` and gateway memory. Fixed upstream routes,
no redirects and no gateway retries preserve the native protocol boundary.

Each run has an isolated profile and raw CLI logs. User config/rules are ignored;
built-in web search and auto-updates are disabled. Requested provider retries are
zero. Default sandbox remains workspace-write. The explicitly authorized
`--codex-docker-isolated` option disables only the inner Codex sandbox, and the
adapter rejects that option outside a Docker command prefix. Outer Docker remains
non-root with resource limits, cap-drop ALL and no-new-privileges.

## Verification Boundaries

The pinned CLI's offline native probes in `receipts/codex-159-offline-01` verified
Single spawn-tool absence, Subagents native child completion, and shell execution.
`analysis/codex_evidence.py` checks per-session lifecycle and retains usage. Root
usage is not a reconciled whole-team cost, and completion is not semantic correctness.

The separate credential-isolation Docker canary is described in
[server preparation](server-preparation.md). It verifies host-to-container gateway
transport using a mocked provider, not real-provider end-to-end success. After the
credential incident, recent smoke results were deleted by user authorization;
there is no post-fix paid result to report. Execution still requires `--execute`,
offline admission proof, exact authorized attempt count and run-specific approval.
