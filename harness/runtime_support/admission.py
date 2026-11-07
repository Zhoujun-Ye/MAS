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
    def __init__(self, fetch, currency, reserve, interval=30):
        self.fetch,self.currency,self.reserve = fetch,currency,amount(reserve)
        self.interval,self.checked,self.lock = interval,0,threading.Lock()

    def check(self):
        with self.lock:
            if time.monotonic()-self.checked < self.interval:
                return
            receipt = self.fetch()
            if balance_available(receipt,self.currency) <= self.reserve:
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
        if (row.get('event')=='finished' and row.get('upstream_attempted') is True
                and row.get('route')=='/anthropic/v1/messages' and row.get('http_status') in {401,402,403}):
            return dict(http_status=row['http_status'],request_id=row.get('request_id'),
                        source=str(path),basis='host_gateway_upstream_response')
    return None
