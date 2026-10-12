"""Interpret observations without asserting upstream availability or coverage."""

import time
from datetime import datetime, timezone

from .instruments import instrument


def new_observation():
    return dict(received_count=0, last_received_time=None, last_quote_time=None,
                last_message_quote_time=None, quote_market_hours=None, older_quote_count=0)


def record_observation(observation, msg, received_at):
    """Update under the caller's lock; arrival order is not quote-time order."""
    quoted = msg["timestamp"] / 1000
    observation["received_count"] = observation.get("received_count", 0) + 1
    observation["last_received_time"] = received_at
    observation["last_message_quote_time"] = quoted
    newest = observation.get("last_quote_time")
    if newest is None or quoted >= newest:
        observation["last_quote_time"] = quoted
        observation["quote_market_hours"] = msg.get("marketHours")
    else:
        observation["older_quote_count"] = observation.get("older_quote_count", 0) + 1


def quote_session(value):
    # Zero is also proto3's absent-field default; do not assert pre-market from it.
    return {None: "Not reported", 0: "Pre-market / unspecified", 1: "Regular (Yahoo)",
            2: "Post-market (Yahoo)", 3: "Extended (Yahoo)",
            4: "Overnight (Yahoo)"}.get(value, "Unknown Yahoo code: " + str(value))


def symbol_status(symbol, observations, storage, now=None, stale_after=30, delayed_after=60):
    now = time.time() if now is None else now
    received = observations.get("last_received_time")
    quoted = observations.get("last_quote_time")
    receipt_age = max(0, now - received) if received is not None else None
    quote_age = max(0, now - quoted) if quoted is not None else None
    info = instrument(symbol)
    current = datetime.fromtimestamp(now, timezone.utc)
    expected = info.expected_open(current)
    holiday = info.holiday(current)
    if storage.get("last_error"):
        state = "Storage write failed"
    elif receipt_age is not None and receipt_age <= stale_after:
        previous = observations.get("last_message_quote_time")
        if quoted is not None and previous is not None and previous < quoted:
            state = "Receiving older snapshots"
        else:
            state = "Receiving delayed quotes" if quote_age is not None and quote_age > delayed_after else "Receiving"
    elif holiday:
        state = "Market holiday: " + holiday
    elif expected is False:
        state = "Outside regular hours (estimated)"
    else:
        state = "Silent / support unknown"
    schedule = ("Holiday: " + holiday if holiday else
                "Within regular hours (estimated)" if expected is True else
                "Outside regular hours (estimated)" if expected is False else "Schedule unknown")
    return dict(symbol=symbol, state=state, receipt_age=receipt_age, quote_age=quote_age,
                session=quote_session(observations.get("quote_market_hours")) if quoted is not None else "Not observed",
                schedule=schedule,
                received=observations.get("received_count", 0),
                written=storage.get("written_by_symbol", {}).get(symbol, 0))
