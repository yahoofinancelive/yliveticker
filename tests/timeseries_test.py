from unittest import mock
import pytest
from yliveticker import YTimeSeries


def test_timeseries_initialization_no_pandas():
    # If pandas is not installed, it should raise ImportError on initialization
    with mock.patch("yliveticker.timeseries.pd", None):
        with pytest.raises(ImportError) as excinfo:
            YTimeSeries()
        assert "pandas is required" in str(excinfo.value)


def test_timeseries_collection():
    # Mocking pandas to avoid actual dependency in unit tests
    with mock.patch("yliveticker.timeseries.pd"):
        yt = YTimeSeries()
        msg1 = {"id": "AAPL", "price": 150, "timestamp": 1600000000000}
        msg2 = {"id": "AAPL", "price": 151, "timestamp": 1600000060000}

        yt.on_ticker(None, msg1)
        yt.on_ticker(None, msg2)

        assert len(yt.data) == 2
        assert yt.data[0] == msg1
        assert yt.data[1] == msg2


def test_get_dataframe_empty():
    with mock.patch("yliveticker.timeseries.pd") as mock_pd:
        yt = YTimeSeries()
        yt.get_dataframe()
        mock_pd.DataFrame.assert_called_once_with()
