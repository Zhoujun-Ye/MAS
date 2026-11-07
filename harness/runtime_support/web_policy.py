"""Frozen, condition-neutral web transport and successful-call limits."""

import urllib.parse
from pathlib import Path

DEFAULT_WEB_LIMIT = 20
SEARCH_RESULTS = 10
SEARCH_SNIPPET_CHARS = 1500
FETCH_CHARS = 20000
FETCH_TIMEOUT_SECONDS = 30
# The solver helper must outlast the host deadline so the host, not curl, reports
# timeouts and an on-time result is never charged but undelivered.
CLIENT_TIMEOUT_SECONDS = 45
WEB_PRICE_USD = 0.00075
PRICE_SOURCE = 'https://api-docs.deepseek.com/guides/search/'
PROXY_SOCKET = Path.home()/'.cache/mas-web/clash.sock'


def configuration(limit=DEFAULT_WEB_LIMIT):
    return dict(protocol='web-v4',successful_call_limit=limit,attempt_limit=limit*2,
        fetch_backend='local-clash-unix',fetch_proxy_socket=str(PROXY_SOCKET),
        fetch_proxy_failure='fail closed; no direct fallback',
        fetch_timeout_seconds=FETCH_TIMEOUT_SECONDS,fetch_character_limit=FETCH_CHARS,
        fetch_content_types='text/*, application/json|xml and +json|+xml; HTML stripped, other text verbatim',
        fetch_failure_reporting='payload-free reason code and original target HTTP status',
        client_timeout_seconds=CLIENT_TIMEOUT_SECONDS,
        search_results=SEARCH_RESULTS,search_snippet_characters=SEARCH_SNIPPET_CHARS,
        failed_call_policy='known failures release success reservation; no automatic retries',
        cost_policy='successful nonempty provider responses only; unknown completion stays unknown',
        provider_unit_price_usd=WEB_PRICE_USD,price_source=PRICE_SOURCE)


def allowed_url(value):
    try:
        parsed=urllib.parse.urlsplit(value)
        host=(parsed.hostname or '').rstrip('.').lower()
        if any(name in urllib.parse.unquote(value).casefold() for name in ('dataclaw','hybriddeepresearch','kramabench')):
            return False
        if (len(value)>8192 or parsed.scheme not in {'http','https'} or not host
                or parsed.username or parsed.password or parsed.port not in {None,80,443}
                or any(ord(c)<33 for c in value)):
            return False
        # Repository/dataset mirrors are not task evidence. Block at the host
        # boundary and filter search results too, without reading any gold fields.
        blocked=('github.com','githubusercontent.com','github.io','huggingface.co',
                 'hf.co','gitlab.com','kaggle.com')
        return not any(host==name or host.endswith('.'+name) for name in blocked)
    except (ValueError,TypeError):
        return False
