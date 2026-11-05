# Current Lead Prompt

Only the current orchestrator-worker lead prompt in `scripts/common/prompts/structured_subagents.py`
is used for Subagents. The user froze its text on 2026-11-04 and requested
removing superseded lead prompt files and version labels.

UTF-8 SHA-256 without trailing newline:
`31ff6e4176a25d961866f644adb4d7b97cb4b00228e696c0e4e38a52b9485a95`.
The exact text is pinned by `tests/test_baseline_prompt.py`.

The lead receives organization instructions; Single does not. Shared task rules
and limits remain identical across conditions. Native Agent delegation is used,
not Agent Teams. Lifecycle accounting does not prove substantive contribution.

The fixed questions remain in `validation20-v1-manifest.json`; the dataset version
is not a prompt version. Current settings are in `validation20-final-protocol.json`.
Neither condition sets a project output token cap. See [run record](validation20-final.md),
[lifecycle fix](lifecycle-fix-20261104.md) and [current results](../current-results.md).
Historical raw run names and frozen manifests are not renamed or rewritten.
