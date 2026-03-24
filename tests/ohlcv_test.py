import pandas as pd
from yliveticker import YTimeSeries


def test_get_ohlcv_real_pandas():
    yt = YTimeSeries()

    # Create some mock data for a single minute
    base_time = 1600000000000  # Some timestamp
    data = [
        {"id": "AAPL", "price": 100, "dayVolume": 1000, "timestamp": base_time},
        {"id": "AAPL", "price": 105, "dayVolume": 1100, "timestamp": base_time + 10000},  # +10s
        {"id": "AAPL", "price": 95, "dayVolume": 1200, "timestamp": base_time + 20000},  # +20s
        {"id": "AAPL", "price": 102, "dayVolume": 1300, "timestamp": base_time + 30000},  # +30s
    ]

    for msg in data:
        yt.on_ticker(None, msg)

    ohlcv = yt.get_ohlcv(interval='1s')

    assert "AAPL" in ohlcv
    df = ohlcv["AAPL"]

    # We expect one row per unique second in our data
    assert not df.empty
    # The first row at base_time should have price 100
    row0 = df.loc[pd.to_datetime(base_time, unit='ms')]
    assert row0['open'] == 100
    assert row0['high'] == 100
    assert row0['low'] == 100
    assert row0['close'] == 100
    assert row0['volume'] == 1000
