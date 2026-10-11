"""Interpret observations without asserting upstream availability or coverage."""

import time
from datetime import datetime, timezone

from .instruments import instrument


def symbol_status(symbol, observations, storage, now=None, stale_after=30, delayed_after=60):
    now = time.time() if now is None else now
    received = observations.get("last_received_time")
    quoted = observations.get("last_quote_time")
    receipt_age = max(0, now - received) if received is not None else None
    quote_age = max(0, now - quoted) if quoted is not None else None
    expected = instrument(symbol).expected_open(datetime.fromtimestamp(now, timezone.utc))
    if storage.get("last_error"):
        state = "Storage write failed"
    elif receipt_age is not None and receipt_age <= stale_after:
        state = "Receiving delayed quotes" if quote_age is not None and quote_age > delayed_after else "Receiving"
    elif expected is False:
        state = "Outside regular hours (estimated)"
    else:
        state = "Silent / support unknown"
    return dict(symbol=symbol, state=state, receipt_age=receipt_age, quote_age=quote_age,
                received=observations.get("received_count", 0),
                written=storage.get("written_by_symbol", {}).get(symbol, 0))
