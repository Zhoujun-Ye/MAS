# Local-Network Web Pipeline

Web GETs follow this mandatory route:

```
network-none solver -> host credential gateway -> restricted SSH Unix socket
  -> this Mac's Clash at 127.0.0.1:7897 -> public website
```

DeepSeek search, model and judge APIs remain server-direct. No provider key is
sent to Clash or a fetched site. The solver receives only an ephemeral gateway
token, not access to the proxy socket. HDR timeout remains 1800 seconds.

## Operation

On the local Mac:

```bash
python3 scripts/server/web_tunnel.py install
python3 scripts/server/web_tunnel.py status
python3 scripts/server/web_tunnel.py stop
```

`install` creates/updates the user launch agent `io.mas.web-tunnel`, starting it
at login and maintaining the SSH transport. It installs its runner under
`~/.cache/mas-web/`, because macOS background services cannot reliably read Desktop
projects. Re-run install after changing its source. No Clash profile, proxy node,
SSH key or system proxy configuration is modified. `stop` unloads the current
session; the installed agent starts again at the next login.

The Mac, Clash and its existing SSH authentication must remain available. The
service reconnects SSH only; it never retries a model, search or page request.
SSH keepalives detect dead connections. Forwarding is confined to
`/home/zhoujunye/.cache/mas-web/clash.sock`: parent mode 0700, owned socket mode
0600, no public TCP proxy port. Bootstrap removes only a refused, stale owned
socket; live listeners, foreign files and symlinks are rejected.

`web-v4` in `cpu8-infra-protocol.json` freezes the transport, socket path, accepted
fetch content types and helper timeout.
Web-enabled matrix/standalone execution checks TLS connectivity through this
route before paid admission. Missing/insecure sockets fail closed. A lost tunnel
record pauses new paid matrix dispatch while preserving other in-flight work.
There is no direct/provider-fetch fallback and no implicit `HTTPS_PROXY` handling.

## Fetch And Search

Fetch pins validated public IPs for CONNECT while preserving the original host
for HTTP Host, TLS SNI and certificate verification. Redirects are revalidated.
Private/link-local/reserved/multicast destinations, unsafe schemes/ports,
credentials and repository/dataset mirrors are denied. GitHub/GitLab content,
GitHub Pages, Hugging Face and Kaggle hosts and explicit benchmark-name queries
or URLs are blocked. This is a conservative leakage guard, not a security claim
about all third-party content or same-UID processes.

GET has a total 30-second deadline, two-MiB body cap, HTML/script/style removal
and 20,000-character text cap. `web-v4` accepts textual responses: `text/*`,
`application/json`, `application/xml` and `+json`/`+xml` types, decoded with a
declared text charset. HTML is stripped; JSON, XML, CSV, wikitext and plain text are
returned verbatim. Binary formats (PDF, images, archives, untyped octet streams)
remain unsupported. All four retained `hdr2-network` fetch failures were Wikipedia
API JSON or `action=raw` wikitext rejected by the earlier HTML/plain-text-only rule.
Failed site access is an error, not an empty successful page. The gateway answers
every failed GET with a payload-free reason code, plus the original target status
where one exists: `target_http_error`, `redirect_limit_or_missing_location`,
`unsupported_content_type`, `unsupported_content_encoding`, `body_size_limit`,
`truncated_body`, `empty_extracted_text`, `url_policy_rejected`, `non_public_address`,
`dns_resolution_failed`, `invalid_target`, `tls_certificate_error`, `tls_error`,
`proxy_unavailable`, `proxy_connect_failed`, `connection_error`, `http_protocol_error`,
`timeout`, `cancelled`, `transport_error` or `internal_error`. Each releases the success
reservation, except during gateway shutdown, when reservations are conservatively
retained; URLs, bodies and exception text are never copied into receipts. The
solver helper waits 45 seconds, longer than the host deadline, so the host reports
timeouts and an on-time result is never charged but undelivered. Helper results
are saved under `/workspace/web` whatever the caller's directory and are still
printed if saving fails.

Search requests ten results and prints compact JSON lines;
full allowed results are shared under `/workspace/web/search-N.json`. Exclusive
symlink-safe names avoid worker overwrites. Stdout stays below 24 KiB and snippets
are at most 1500 characters, shorter where byte limits require it. Fetch results
are also saved to shared files.

Each web-enabled DataClaw/HDR task defaults to 20 successful logical web calls
and at most 40 logical attempts, shared by all roles. A fetch may follow at most
five redirects within its one deadline. Confirmed failures/empty results release
success reservations; unknown completions retain them. Atomic host counters are
authoritative. There is no worker quota, solver-side accounting ledger or automatic
web retry. `--max-web-requests` is frozen equally for both conditions.

Official Search API schema and price source (checked 2026-11-07):
<https://api-docs.deepseek.com/guides/search/>. The historical Fetch route/schema
were valid; HTTP 404 can mean unavailable or unextractable content, not necessarily
a wrong endpoint. The old optional provider-fetch and unused Tavily paths are now
removed. Search's documented successful-nonempty unit estimate is USD0.00075;
host tunnel GET has no paid fetch-provider charge. Receipts retain outcome/backend,
estimate/source and uncertainty. Historical HTTP-only cost estimates stay explicitly
unverified. Empty text answers receive deterministic zero without a judge; unjudged
nonempty answers remain pending. No scoring semantics or gold access were relaxed.

## Verification And Retention

Current receipts: `/home/zhoujunye/mas-data/receipts/local-web-pipeline-20261107/`.
After cleanup, 725 server regression tests passed in 32.22 seconds without skips.
An intentional termination of the owned SSH master caused a fail-closed fetch;
the login service automatically recreated the tunnel and TLS readiness passed.
The real-image `scripts/probes/web_tools.py --execute --public-fetch` exercises
search fixtures, an actual Wikipedia GET through the complete container/gateway/
tunnel/Clash chain, a known failure and subsequent successful call. It uses no
real provider credentials or paid APIs. Standalone real host GET also verified
the SQLite Wikipedia title and bounded text through this tunnel.

Regression covers reverse-socket permissions/stale cleanup, TLS hostname identity,
no direct fallback, SSRF guards, atomic quotas, unknown charges, shutdown and
empty-answer scoring. Later cleanup removes superseded offline fixtures/logs and
offline-only stages, not paid results, their frozen sources or operational data.
Exact deleted paths/bytes and retained-output hashes are recorded in `cleanup.json`.
The tunnel may improve page availability; it does not guarantee every site works
or accelerate model generation. No new paid benchmark was authorized or launched.
