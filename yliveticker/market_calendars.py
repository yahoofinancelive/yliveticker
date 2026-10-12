"""Verified full-day closures; missing coverage must remain an estimate.

JPX 2026 cash-market calendar, checked 2026-10-12:
https://www.jpx.co.jp/english/corporate/about-jpx/calendar/index.html
These dates do not describe the separate derivatives holiday-trading calendar.
"""

JPX_2026 = {
    "01-01": "New Year's Day", "01-02": "Market holiday",
    "01-03": "Market holiday", "01-12": "Coming of Age Day",
    "02-11": "National Foundation Day", "02-23": "Emperor's Birthday",
    "03-20": "Vernal Equinox", "04-29": "Showa Day",
    "05-03": "Constitution Memorial Day", "05-04": "Greenery Day",
    "05-05": "Children's Day", "05-06": "Constitution Memorial Day (observed)",
    "07-20": "Marine Day", "08-11": "Mountain Day",
    "09-21": "Respect for the Aged Day", "09-22": "National holiday",
    "09-23": "Autumnal Equinox", "10-12": "Sports Day",
    "11-03": "Culture Day", "11-23": "Labor Thanksgiving Day",
    "12-31": "Market holiday",
}


def market_holiday(timezone_name, local_date, kind):
    if timezone_name == "Asia/Tokyo" and kind == "equity" and local_date.year == 2026:
        return JPX_2026.get(local_date.strftime("%m-%d"))
    return None
