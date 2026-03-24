try:
    import pandas as pd
except ImportError:
    pd = None


class YTimeSeries:
    def __init__(self):
        if pd is None:
            raise ImportError(
                "pandas is required for YTimeSeries. "
                "Install it with 'pip install yliveticker[pandas]'"
            )
        self.data = []

    def on_ticker(self, ws, msg):
        """
        Callback function to be passed to YLiveTicker.
        It collects messages into an internal list.
        """
        self.data.append(msg)

    def get_dataframe(self):
        """
        Converts collected data into a pandas DataFrame.
        """
        if not self.data:
            return pd.DataFrame()

        df = pd.DataFrame(self.data)
        if 'timestamp' in df.columns:
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('timestamp', inplace=True)
        return df

    def get_ohlcv(self, interval='1Min'):
        """
        Resamples collected data into OHLCV format.

        :param interval: pandas resample interval (e.g., '1Min', '5Min', '1H')
        :return: A dictionary of DataFrames, one per symbol (id)
        """
        df = self.get_dataframe()
        if df.empty:
            return {}

        results = {}
        for symbol, group in df.groupby('id'):
            resampled = group['price'].resample(interval).ohlc()

            # Volume might not be always present or might need summation
            if 'dayVolume' in group.columns:
                # dayVolume is usually cumulative for the day in Yahoo Finance
                # For true interval volume, we'd need to calculate differences
                resampled['volume'] = group['dayVolume'].resample(interval).last()

            results[symbol] = resampled

        return results
