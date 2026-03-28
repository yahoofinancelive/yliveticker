import yliveticker
from yliveticker.sinks.influxdb import InfluxDBSink
import signal
import sys
import time

# Configuration for InfluxDB (matches docker-compose.yml)
URL = "http://localhost:8086"
TOKEN = "my-super-secret-auth-token"
ORG = "yliveticker"
BUCKET = "ticker_data"

def main():
    # Initialize the sink
    sink = InfluxDBSink(url=URL, token=TOKEN, org=ORG, bucket=BUCKET)

    def signal_handler(sig, frame):
        print("\nStopping ticker and flushing records...")
        sink.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)

    print("Starting yliveticker with InfluxDB sink...")
    print("Subscribing to AAPL and BTC-USD. Press Ctrl+C to stop.")

    # Start the ticker and pass the sink's on_ticker method
    yliveticker.YLiveTicker(
        on_ticker=sink.on_ticker,
        ticker_names=["AAPL", "BTC-USD"]
    )

if __name__ == "__main__":
    main()
