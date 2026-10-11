from collections import deque
import threading

try:
    import pandas as pd
except ImportError:
    pd = None


class YTimeSeries:
    def __init__(self, max_points=100000):
        if pd is None:
            raise ImportError(
                "pandas is required for YTimeSeries. "
                "Install it with 'pip install yliveticker[pandas]'"
            )
        if max_points is not None and (isinstance(max_points, bool) or
                                      not isinstance(max_points, int) or max_points < 1):
            raise ValueError("max_points must be a positive integer or None")
        self.data = deque(maxlen=max_points)
        self.evicted_points = 0
        self._lock = threading.Lock()

    def on_ticker(self, ws, msg):
        """
        Callback function to be passed to YLiveTicker.
        Collect a snapshot in a bounded buffer (100,000 points by default).
        """
        with self._lock:
            if self.data.maxlen is not None and len(self.data) == self.data.maxlen:
                self.evicted_points += 1
            self.data.append(dict(msg))

    def get_dataframe(self):
        """
        Converts collected data into a pandas DataFrame.
        """
        with self._lock:
            data = list(self.data)
        if not data:
            return pd.DataFrame()

        df = pd.DataFrame(data)
        if 'timestamp' in df.columns:
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms', utc=True)
            df.set_index('timestamp', inplace=True)
        return df

    def get_ohlcv(self, interval='1Min'):
        """
        Resample prices and the last observed cumulative session volume.

        ``session_volume`` is NOT interval traded volume. Yahoo does not supply
        a reliable session baseline/reset marker for every instrument, so we
        do not invent interval volume from incomplete or delayed observations.

        :param interval: pandas resample interval (e.g., '1Min', '5Min', '1H')
        :return: A dictionary of DataFrames, one per symbol (id)
        """
        df = self.get_dataframe()
        if df.empty:
            return {}

        results = {}
        for symbol, group in df.groupby('id'):
            group = group.sort_index(kind='stable')
            resampled = group['price'].resample(interval).ohlc()

            if 'dayVolume' in group.columns:
                volume = pd.to_numeric(group['dayVolume'], errors='coerce')
                resampled['session_volume'] = volume.where(volume > 0).resample(interval).last()

            results[symbol] = resampled

        return results
