"""Host balance admission and authoritative fatal-provider evidence; no retries."""

from decimal import Decimal, InvalidOperation
import json
import threading
import time


def amount(value):
    try:
        result = Decimal(str(value))
    except InvalidOperation:
        raise ValueError('Expected a finite nonnegative amount') from None
    if not result.is_finite() or result < 0:
        raise ValueError('Expected a finite nonnegative amount')
    return result


def balance_available(receipt, currency):
    if not receipt or not receipt.get('response',{}).get('is_available'):
        raise ValueError('Balance unavailable; no new paid dispatch allowed')
    rows = [r for r in receipt['response'].get('balance_infos',[]) if r['currency']==currency]
    if len(rows)!=1:
        raise ValueError('Requested balance currency unavailable or ambiguous')
    return amount(rows[0]['total_balance'])


def admit_balance(receipt, currency, estimate, factor, reserve):
    estimate, factor, reserve = amount(estimate), amount(factor), amount(reserve)
    if estimate <= 0 or factor < 1:
        raise ValueError('Explicit positive estimated total cost and safety factor >= 1 required')
    available = balance_available(receipt,currency)
    required = estimate*factor+reserve
    if available < required:
        raise ValueError('Insufficient balance for the explicit estimated scope and reserve')
    return dict(currency=currency,estimated_cost=str(estimate),safety_factor=str(factor),
                reserve=str(reserve),required=str(required),observed_balance=str(available),
                scope='Estimate-based admission, not a hard billing cap or attribution guarantee')


class BalanceWatch:
    def __init__(self, fetch, currency, reserve, interval=30, initial=None, max_failures=3):
        self.fetch,self.currency,self.reserve = fetch,currency,amount(reserve)
        self.interval,self.checked,self.lock = interval,0,threading.Lock()
        self.verified = initial is not None
        if self.verified:
            balance_available(initial,currency)
        self.failures,self.max_failures = 0,max_failures

    def check(self):
        with self.lock:
            if time.monotonic()-self.checked < self.interval:
                return
            try:
                available = balance_available(self.fetch(),self.currency)
            except Exception:
                self.failures += 1
                self.checked = time.monotonic()
                if not self.verified or self.failures >= self.max_failures:
                    raise ValueError('Balance lookup repeatedly unavailable; pause new dispatch') from None
                return
            self.failures = 0
            self.verified = True
            if available <= self.reserve:
                raise ValueError('Balance reserve reached; stop new dispatch, preserve in-flight work')
            self.checked = time.monotonic()


def fatal_provider_record(path):
    if not path.exists():
        return None
    try:
        lines=path.read_text().splitlines()
    except FileNotFoundError:
        return None
    for line in lines:
        try:
            row=json.loads(line)
        except ValueError:
            continue  # A concurrently appended final line can be incomplete.
        model_fatal=row.get('route')=='/anthropic/v1/messages' and row.get('http_status') in {401,402,403}
        web_fatal=(row.get('web_backend')=='deepseek' and row.get('route') in {'/v1/tools/search','/v1/tools/fetch'}
                   and row.get('http_status') in {401,402})
        if row.get('event')=='finished' and row.get('upstream_attempted') is True and (model_fatal or web_fatal):
            return dict(http_status=row['http_status'],request_id=row.get('request_id'),
                        source=str(path),basis='host_gateway_upstream_response')
    return None


def unavailable_web_proxy(path):
    if not path.exists():return False
    for line in path.read_text().splitlines():
        try:row=json.loads(line)
        except ValueError:continue
        if isinstance(row,dict) and row.get('event')=='finished' and row.get('web_proxy_unavailable') is True:
            return True
    return False


def infrastructure_health(path):
    """Keep upstream failures orthogonal to solver lifecycle and answer scores."""
    try:
        lines = path.read_text().splitlines()
    except FileNotFoundError:
        return dict(infra_degraded=None, upstream_5xx=[], transport_failures=[], ledger_status='missing')
    failures, transport = {}, {}
    malformed = False
    for line in lines:
        try:
            row = json.loads(line)
        except ValueError:
            malformed = True
            continue
        if not isinstance(row, dict):
            malformed = True
            continue
        status = row.get('http_status')
        if (row.get('event') == 'finished' and row.get('upstream_attempted') is True
                and row.get('outcome') == 'upstream_rejected'
                and type(status) is int and 500 <= status <= 599):
            identity = row.get('request_id')
            failures[identity] = dict(request_id=identity, http_status=status, route=row.get('route'))
        if (row.get('event') == 'finished' and row.get('upstream_attempted') is True
                and row.get('outcome') in {'transport_error', 'transport_interrupted'}):
            transport[row.get('request_id')] = dict(request_id=row.get('request_id'), route=row.get('route'),
                outcome=row['outcome'], error_type=row.get('error_type'),
                transport_error_class=row.get('transport_error_class'), completion='unknown')
    return dict(infra_degraded=True if failures or transport else None if malformed else False,
                upstream_5xx=list(failures.values()), transport_failures=list(transport.values()),
                ledger_status='malformed' if malformed else 'read',
                basis='host_gateway_upstream_response_or_transport', retries_authorized=False)
