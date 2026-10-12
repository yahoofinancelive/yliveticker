"""Display metadata, approximate schedules and explicitly limited holiday data.

Yahoo support, auctions and exceptional sessions are not inferred from this
registry. Unknown symbols remain usable with explicitly unknown metadata.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .market_calendars import market_holiday


@dataclass(frozen=True)
class Instrument:
    symbol: str
    country: str
    name: str
    currency: str
    timezone: str = "UTC"
    sessions: tuple = ()
    kind: str = "equity"

    @property
    def label(self):
        return self.symbol + " · " + self.country

    @property
    def region(self):
        if self.kind in ("crypto", "fx"):
            return "Global"
        if self.timezone.startswith(("Pacific/", "Australia/")) or self.timezone in (
                "Asia/Tokyo", "Asia/Hong_Kong", "Asia/Singapore", "Asia/Kolkata"):
            return "Asia-Pacific"
        if self.timezone.startswith(("Europe/", "Africa/")) or self.timezone == "Asia/Dubai":
            return "Europe / Middle East / Africa"
        if self.timezone.startswith("America/"):
            return "Americas"
        return "Unknown region"

    def holiday(self, now=None):
        local = (now or datetime.now(timezone.utc)).astimezone(ZoneInfo(self.timezone))
        return market_holiday(self.timezone, local.date(), self.kind)

    def expected_open(self, now=None):
        """Approximation only; None means no known schedule, not unsupported."""
        now = (now or datetime.now(timezone.utc)).astimezone(ZoneInfo(self.timezone))
        if self.holiday(now):
            return False
        minute = now.hour * 60 + now.minute
        day = now.weekday()
        if self.kind == "crypto":
            return True
        if self.kind in ("fx", "futures"):
            # Week opens Sunday at 17:00; Friday closes at 17:00 (FX)
            # or 16:00 (gold). Gold has a daily 16:00–17:00 maintenance break.
            close = 16 * 60 if self.kind == "futures" else 17 * 60
            if day == 5 or (day == 6 and minute < 17 * 60) or (day == 4 and minute >= close):
                return False
            return self.kind != "futures" or not 16 * 60 <= minute < 17 * 60
        if not self.sessions:
            return None
        return day < 5 and any(_minutes(start) <= minute < _minutes(end) for start, end in self.sessions)

    def utc_hours(self):
        if self.kind == "crypto":
            return "24/7; no scheduled daily closure"
        if not self.sessions:
            return "Regular hours unknown"

        def render(month):
            date = datetime(2026, month, 15, tzinfo=ZoneInfo(self.timezone))

            def convert(value):
                converted = (date + timedelta(minutes=_minutes(value))).astimezone(timezone.utc)
                offset = (converted.date() - date.date()).days
                suffix = " (previous UTC day)" if offset < 0 else " (next UTC day)" if offset > 0 else ""
                return converted.strftime("%H:%M") + suffix
            return " and ".join(convert(start) + "–" + convert(end) for start, end in self.sessions)

        january, july = render(1), render(7)
        hours = january + " UTC" if january == july else (
            january + " UTC (January offset); " + july + " UTC (July offset); DST transition dates vary")
        if self.kind == "fx":
            return "Sunday open–Friday close at " + hours
        if self.kind == "futures":
            return "Sunday–Friday trading " + hours + "; daily one-hour maintenance break"
        return "Weekday regular sessions: " + hours

    def description(self):
        extended = (" Yahoo can also send US pre-market, post-market and overnight quotes; "
                    "the table identifies the newest quote's reported session."
                    if self.timezone == "America/New_York" and self.kind == "equity" else "")
        return (self.label + " · " + self.name + " · quote currency " + self.currency + ". " +
                self.utc_hours() + "." + extended + " Indicative regular schedule only; holidays, special sessions, "
                "Yahoo delays and feed availability may differ. No data does not prove a market is closed "
                "or that Yahoo supports this symbol.")


def _minutes(value):
    hour, minute = value.split(":")
    return int(hour) * 60 + int(minute)


INSTRUMENTS = (
    Instrument("BTC-USD", "Global crypto", "Bitcoin", "USD", kind="crypto"),
    Instrument("EURUSD=X", "Global FX", "EUR/USD", "USD", "America/New_York", (("17:00", "17:00"),), "fx"),
    Instrument("GC=F", "United States", "COMEX gold futures", "USD", "America/Chicago", (("17:00", "40:00"),), "futures"),
    Instrument("FPH.NZ", "New Zealand", "Fisher & Paykel Healthcare", "NZD", "Pacific/Auckland", (("10:00", "16:45"),)),
    Instrument("BHP.AX", "Australia", "BHP", "AUD", "Australia/Sydney", (("10:00", "16:00"),)),
    Instrument("7203.T", "Japan", "Toyota", "JPY", "Asia/Tokyo", (("09:00", "11:30"), ("12:30", "15:30"))),
    Instrument("0700.HK", "Hong Kong", "Tencent", "HKD", "Asia/Hong_Kong", (("09:30", "12:00"), ("13:00", "16:00"))),
    Instrument("D05.SI", "Singapore", "DBS", "SGD", "Asia/Singapore", (("09:00", "12:00"), ("13:00", "17:00"))),
    Instrument("RELIANCE.NS", "India", "Reliance Industries", "INR", "Asia/Kolkata", (("09:15", "15:30"),)),
    Instrument("EMAAR.AE", "Dubai (UAE)", "Emaar Properties", "AED", "Asia/Dubai", (("10:00", "15:00"),)),
    Instrument("NPN.JO", "South Africa", "Naspers", "ZAc", "Africa/Johannesburg", (("09:00", "17:00"),)),
    Instrument("SAP.DE", "Germany", "SAP (Xetra)", "EUR", "Europe/Berlin", (("09:00", "17:30"),)),
    Instrument("HSBA.L", "United Kingdom", "HSBC", "GBp", "Europe/London", (("08:00", "16:30"),)),
    Instrument("AAPL", "United States", "Apple", "USD", "America/New_York", (("09:30", "16:00"),)),
    Instrument("NVDA", "United States", "NVIDIA (California issuer; US exchange hours)", "USD", "America/New_York", (("09:30", "16:00"),)),
    Instrument("SHOP.TO", "Canada", "Shopify", "CAD", "America/Toronto", (("09:30", "16:00"),)),
    Instrument("VALE3.SA", "Brazil", "Vale", "BRL", "America/Sao_Paulo", (("10:00", "17:00"),)),
)
REGISTRY = {instrument.symbol: instrument for instrument in INSTRUMENTS}
DEFAULT_SYMBOLS = tuple(REGISTRY)


def dashboard_symbols(symbols):
    """Regions east to west; preserve registry order within each region."""
    regions = ("Asia-Pacific", "Europe / Middle East / Africa", "Americas", "Global", "Unknown region")
    positions = {symbol: n for n, symbol in enumerate(DEFAULT_SYMBOLS)}
    return sorted(watchlist(symbols), key=lambda s: (
        regions.index(instrument(s).region), positions.get(s.removeprefix("SYNTH-"), len(positions))))


def instrument(symbol):
    plain = symbol.removeprefix("SYNTH-")
    info = REGISTRY.get(plain, Instrument(plain, "Unknown market", plain, "N/A"))
    if plain == symbol:
        return info
    return Instrument(symbol, "Synthetic test · " + info.country, info.name, info.currency,
                      info.timezone, info.sessions, info.kind)


def watchlist(value=None):
    symbols = value.split() if isinstance(value, str) else list(value or DEFAULT_SYMBOLS)
    if not symbols or any(not isinstance(s, str) or not s.strip() for s in symbols):
        raise ValueError("Provide at least one nonempty symbol")
    return list(dict.fromkeys(s.strip() for s in symbols))
