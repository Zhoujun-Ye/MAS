# Web And DNS Transport

## Active Route

```
network-none solver -> host credential gateway -> private SSH Unix sockets
  GET -> this Mac's Clash mixed proxy -> public website
  DNS -> restricted local DNS bridge -> Clash DNS Unix API
```

This is web-v5. Model, search and judge APIs remain server-direct. Provider keys
stay host-side; the solver receives an ephemeral gateway token, not either proxy
socket or the Clash control API. Same-UID processes are not authenticated by that
token. Task timeouts remain owned by `benchmarks/policy.py`.

## Local Service

On the Mac:

```sh
python3 scripts/server/web_tunnel.py install
python3 scripts/server/web_tunnel.py status
python3 scripts/server/web_tunnel.py stop
```

The existing `io.mas.web-tunnel` launch agent installs its runner, VPN connector
and standalone DNS bridge under `~/.cache/mas-web/`, outside Desktop access
restrictions. Reinstall after changing their source, only when experiments are
quiescent. Installation waits for its known old registration to unload before
bootstrap; genuine failures are not silently accepted.

The campus SSH helper binds the selected active VPN interface and source address;
it does not trust a route potentially overridden by Clash TUN. Missing/ambiguous
interfaces fail closed. No route, SSH key, system DNS or Clash profile is changed.
The SSH session receives a heartbeat every 15 seconds and expires after 60 seconds
without one or on EOF. Each heartbeat now requires a remote acknowledgment:
20 seconds for startup, 10 thereafter. A multiplexing master can stay alive after
its primary session exits while sibling sessions remain; process liveness alone
previously missed that state. Missing/closed acknowledgment stops only the owned
SSH child, with bounded termination, so launchd can reconnect instead of leaving
a misleadingly live master. Lifecycle events have UTC timestamps in `stdout.log`.
Service reconnects never retry a model/search/page request.
A loaded service or live master alone does not establish public-site connectivity.

The November 11 audit found an owned but refused local SSH control socket after
an earlier disconnect. OpenSSH continued without multiplexing, so `status` falsely
reported no master while the acknowledged tunnel still carried traffic. Startup
now checks this socket under the owner lock and removes only a stale owned socket;
live endpoints, symlinks and non-sockets fail closed. This repairs reconnect/status
behavior, not intermittent downstream TLS EOF. Reinstall only after paid jobs are
quiescent; frozen paid source remains unchanged.

Server endpoints are `~/.cache/mas-web/clash.sock` and `dns.sock`, in an owned
mode-0700 directory with mode-0600 sockets. Only refused stale owned sockets may
be removed; live listeners, foreign files and symlinks are rejected. There is no
public TCP listener or solver-container networking. Keep the installed service,
private helpers, control directory and live sockets.

## DNS And Target Validation

The separate bridge accepts only bounded hostname requests and A/AAAA resolution
through Clash's fixed `/dns/query` Unix API. It does not forward arbitrary paths,
HTTP destinations or controller access. Request/reply sizes, address counts,
deadlines and concurrent handlers are bounded. Hostnames and echoed questions
are checked; private, loopback, multicast, reserved and fake-IP answers fail closed.
There is no server-resolver, public-DoH or direct-network fallback.

The host validates every returned address, pins a selected public IP for CONNECT
and verifies the original hostname with TLS SNI/certificate checks. Redirects are
revalidated. Unsafe schemes/ports, credentials in URLs, private targets, dataset
mirrors and explicit benchmark-name URLs/queries are denied. GitHub/GitLab,
GitHub Pages, Hugging Face and Kaggle content are excluded. This is a conservative
leakage guard, not proof against all third-party leakage or same-UID mutation.

The prior web-v4 path resolved names on the server even though GETs used the Mac.
A paid SEC fetch failed with `EAI_NODATA`; both the server stub and campus upstream
returned empty A/AAAA answers with a `user.rpz` SOA. Clash resolved the same domain.
This matches [RPZ response-policy rewriting](https://bind9.readthedocs.io/en/stable/reference.html#response-policy-zone-rpz-rewriting),
not a fabricated domain. The [November 10 audit](full-infra-20261110.md) separates
that defect from TLS failures associated with the user's Clash node/config change.
After repair SEC resolved and completed TLS, but returned HTTP403: site refusal
is not a DNS failure or permission to bypass site policy.

## Fetch And Search

GET has one absolute 30-second deadline across DNS/CONNECT/TLS/headers/body,
a two-MiB body cap and 20,000-character result cap. Accepted types are `text/*`,
JSON/XML and `+json`/`+xml`; HTML scripts/styles are stripped, other text is
returned verbatim using its declared charset where valid. PDF/images/archives
and untyped binary bodies remain unsupported. Truncated bodies are errors.

The helper waits 45 seconds so the host can report a timeout. Results save under
`/workspace/web` regardless of working directory and are printed even if saving
fails. Search returns ten results with bounded snippets, keeps stdout below
24 KiB, and writes complete allowed results to uniquely named shared files.

Failures expose payload-free reason codes and original target HTTP status when
known, never raw URL/query/body/exception text in accounting. DNS, proxy, target
HTTP, TLS certificate/handshake, timeout, cancellation, framing, body/type/encoding
and policy failures remain distinct. A denied/failed fetch is not empty success.
The optional allowlisted `fetch_failure_stage` distinguishes DNS socket checks,
bridge connect/reply, Clash DNS connect/HTTP/decode and GET socket/connect failures.
DNS socket timeouts are `dns_timeout` even when the deadline timer has not fired;
malformed controller JSON/HTTP is `dns_response_invalid`, not proxy unavailability.
Neither classification change introduces fallback, answer caching or retries.

## Shared Budget And Accounting

Each web-enabled task defaults to 20 successful logical calls and at most 40
attempts, shared across every role/process. A fetch may follow five redirects
within its one deadline. Known failures/empty results release success reservations;
unknown completions retain them. Host counters are authoritative. No per-worker
quota, automatic retry, response cache or provider-fetch fallback is added.

Search's recorded successful-nonempty estimate is USD0.00075 from the
[provider schema/price reference](https://api-docs.deepseek.com/guides/search/),
checked November 7; it is not a current tariff guarantee or invoice.
Host GETs have no paid fetch-provider charge. Unknown accounting is not zero.

## Verification

`scripts/probes/web_tools.py --execute --public-fetch` uses synthetic search,
real network-none containers, dummy keys and public Wikipedia HTML/JSON through
the complete route. It verifies failure accounting and shared files outside the
workspace, with no paid API. DNS bridge tests cover framing, bounds, public-address
checks, concurrency, deadlines and no fallback.

Current receipts are in `mas-data/receipts/maintenance-20261110/`; the preceding
deployed DNS/web evidence is in `clash-dns-20261110-01/`. Preserve summaries and
latest native proofs; superseded synthetic workspaces are not paid evidence.
Historical manifests retain their recorded web-v4 settings. Generate future
profiles/manifests from current web-v5 source without rerolling frozen task IDs.
Mac/VPN/Clash availability and individual site restrictions remain dependencies.

The November 10 recovery repair has separate receipts in
`mas-data/receipts/tunnel-recovery-20261110/`. All 914 server tests passed.
A controlled fault terminated only the owned remote heartbeat session while a
multiplexed sibling remained; the service detected it, stopped its old master
and regained acknowledged connectivity in 18.82 seconds. This is one recovery
measurement, not an availability guarantee. Earlier logs contained socket-live
reconnect rejections and VPN source-address errors, but lacked timestamps; the
06:58 local-time historical fetch failure cannot be attributed to either with
certainty from its generic `proxy_unavailable` record alone.

The later continuous check must not be reported as uniformly passing: all 24 DNS
requests passed, but four of six Wikipedia TLS checks ended with `SSLEOFError`
while the acknowledged SSH session stayed healthy. A separate Mac-only check
also saw TLS EOF both with an IP-pinned CONNECT and with a hostname CONNECT,
without using the server/tunnel. The user confirmed no node/config switch during
this check. A subsequent six-connection route trace passed and used the same
Clash selector/VLESS chain for both targets, so routing differences are not
established. This isolates a residual intermittent failure downstream of the
SSH path; it does not uniquely identify the proxy node versus its target path.
Keep these failed checks alongside successes. Do not hide them with automatic
retries, weaken TLS/public-address validation or declare the network fixed.

The user then authorized one temporary existing-node switch and six free checks,
followed by restoration. Using the [documented selection API](https://wiki.metacubex.one/en/api/),
the alternate node passed all six server-side TLS checks; the original selection
was restored and verified. This was not an interleaved randomized comparison:
the original route had also recovered in six later Mac curl checks and the
six-connection trace above. The evidence therefore supports intermittent
downstream connectivity, not a uniquely proven bad node or a permanent fix by
switching. No subscription, system DNS, TLS/public-IP policy or retry policy was
changed. Raw failed checks and the authorized comparison remain in the receipt
root; private node names are not published.
