"""Pair host model dispatches with terminal receipts; ambiguous calls stay unknown."""

from collections import Counter, defaultdict


def model_receipts(records):
    sent = [r for r in records if r.get('route') == '/anthropic/v1/messages' and r.get('event') == 'dispatched']
    done = [r for r in records if r.get('route') == '/anthropic/v1/messages'
            and r.get('event') in {'finished', 'shutdown'} and r.get('upstream_attempted') is True]
    counts = Counter(r.get('request_id') for r in sent)
    terminal = defaultdict(list)
    for row in done:
        terminal[row.get('request_id')].append(row)
    observed = []
    for identity, count in counts.items():
        candidates = terminal[identity]
        if identity is None or count != 1 or len(candidates) != 1:
            continue
        row = candidates[0]
        if (row.get('event') == 'finished' and row.get('outcome') == 'response_complete'
                and row.get('usage_status') == 'observed' and row.get('http_status') == 200):
            observed.append(row)
    complete = bool(sent) and len(observed) == len(sent) == len(done)
    return dict(dispatched=sent, terminal=done, observed=observed, complete=complete,
                outcomes=dict(Counter(r.get('outcome', 'unknown') for r in done)))


def gateway_tokens(records):
    receipt = model_receipts(records)
    complete = receipt['complete']
    result = dict(input_tokens=None, cache_hit_tokens=None, uncached_input_tokens=None, output_tokens=None)
    values = []
    for row in receipt['observed']:
        usage = row.get('usage') or {}
        fields = ('input_tokens', 'cache_creation_input_tokens', 'cache_read_input_tokens', 'output_tokens')
        if not all(type(usage.get(k)) is int and usage[k] >= 0 for k in fields):
            complete = False
            continue
        miss = usage['input_tokens'] + usage['cache_creation_input_tokens']
        hit = usage['cache_read_input_tokens']
        values.append(dict(input_tokens=miss + hit, cache_hit_tokens=hit,
                           uncached_input_tokens=miss, output_tokens=usage['output_tokens']))
    if complete:
        result = {k: sum(v[k] for v in values) for k in result}
    known = {k: sum(v[k] for v in values) for k in result} if values else None
    return dict(result, complete=complete, known_request_subtotal=known,
                requests_with_known_tokens=len(values),
                requests_with_unknown_tokens=(max(len(receipt['dispatched']),len(receipt['terminal']))-len(values)
                    if receipt['dispatched'] or receipt['terminal'] else None),
                model_requests=len(receipt['dispatched']), model_completions=len(receipt['terminal']),
                request_outcomes=receipt['outcomes'])
