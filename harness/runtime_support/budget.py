"""Opt-in conservative admission accounting; does not alter provider requests."""

from decimal import Decimal
import threading


class RequestBudget:
    # Frozen peak USD/M token rates, verified 2026-11-05 against official docs.
    INPUT = Decimal('0.3') / 1_000_000
    OUTPUT = Decimal('1.2') / 1_000_000
    CONTEXT = 1_048_576

    def __init__(self, dollars):
        self.limit = Decimal(str(dollars))
        if not self.limit.is_finite() or self.limit <= 0:
            raise ValueError('Positive finite budget required')
        self.lock = threading.Lock()
        self.reservations = {}
        self.settled = set()
        self.denied = 0

    def reserve(self, identity, payload, path):
        maximum = payload.get('max_tokens')
        if (path != '/anthropic/v1/messages' or type(maximum) is not int
                or not 1 <= maximum <= 8192 or
                any(t.get('type', '').startswith(('web_', 'computer_')) for t in payload.get('tools', []))):
            raise ValueError('Budget policy rejects unsupported route/output/server tool')
        amount = self.CONTEXT * self.INPUT + maximum * self.OUTPUT
        with self.lock:
            if identity in self.reservations:
                raise ValueError('Duplicate reservation')
            if sum(self.reservations.values()) + amount > self.limit:
                self.denied += 1
                raise ValueError('Run budget exhausted; no upstream dispatch permitted')
            self.reservations[identity] = amount

    def settle(self, row):
        identity, usage = row['request_id'], row.get('usage') or {}
        fields = ('input_tokens', 'output_tokens')
        if row.get('outcome') != 'response_complete' or any(type(usage.get(k)) is not int for k in fields):
            return  # Unknown/failed calls retain their entire reservation.
        tokens = [usage.get(k, 0) for k in ('input_tokens', 'cache_creation_input_tokens', 'cache_read_input_tokens')]
        if any(type(v) is not int or v < 0 for v in tokens) or usage['output_tokens'] < 0:
            return
        actual = sum(tokens) * self.INPUT + usage['output_tokens'] * self.OUTPUT
        with self.lock:
            if identity in self.reservations and identity not in self.settled:
                # Retain the upper bound on inconsistent provider usage.
                if actual <= self.reservations[identity]:
                    self.reservations[identity] = actual
                    self.settled.add(identity)

    def summary(self):
        with self.lock:
            return dict(limit_usd=str(self.limit), reserved_or_peak_estimated_usd=str(sum(self.reservations.values())),
                        admitted=len(self.reservations), settled=len(self.settled), denied=self.denied,
                        unknown=len(self.reservations)-len(self.settled),
                        basis='Peak rates; full context reserved per in-flight request; not an invoice')
