from yliveticker.sinks.base import BaseTSDBSink
import influxdb_client
from influxdb_client import WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS
from datetime import datetime, timezone
import time

class InfluxDBSink(BaseTSDBSink):
    def __init__(self, url, token, org, bucket, batch_size=100, flush_interval=5.0, **sink_options):
        self.client = influxdb_client.InfluxDBClient(url=url, token=token, org=org, timeout=5000)
        self.write_api = self.client.write_api(write_options=SYNCHRONOUS)
        self.bucket = bucket
        super().__init__(batch_size=batch_size, flush_interval=flush_interval, **sink_options)

    def on_ticker(self, ws, msg):
        # Yahoo's event timestamp may be delayed by an exchange. Capture local
        # receipt time separately so ingestion-rate charts measure the collector.
        msg = dict(msg)
        msg.setdefault('_received_at_ns', time.time_ns())
        super().on_ticker(ws, msg)

    def write_batch(self, batch):
        points = []
        for msg in batch:
            point = influxdb_client.Point("ticker").tag("id", msg.get('id'))
            currency = msg.get('currency')
            if currency:
                point.tag("currency", currency)
            point.field("price", float(msg.get('price'))).time(
                datetime.fromtimestamp(msg.get('timestamp') / 1000, tz=timezone.utc)
            )
            # proto3 scalar fields have no presence information here, so Yahoo's
            # missing dayVolume arrives as 0. Preserve availability explicitly
            # without storing that sentinel as a measured session volume.
            volume = msg.get('dayVolume')
            volume = float(volume) if volume is not None else 0.0
            point.field("volume_available", 1 if volume > 0 else 0)
            if volume > 0:
                point.field("volume", volume)
            received = influxdb_client.Point("ticker_ingest") \
                .tag("id", msg.get('id')) \
                .field("count", 1) \
                .time(msg.get('_received_at_ns', time.time_ns()), WritePrecision.NS)
            points.extend((point, received))
        
        self.write_api.write(bucket=self.bucket, record=points)

    def stop(self):
        try:
            super().stop()
        finally:
            self.client.close()

    def write_status(self, statuses):
        """Persist observations at receipt time; a failed heartbeat expires in Grafana."""
        now = time.time_ns()
        points = []
        for status in statuses:
            point = influxdb_client.Point("ticker_status").tag("id", status["symbol"])
            for field in ("state", "connection", "received", "written"):
                point.field(field, status[field])
            for field in ("receipt_age", "quote_age"):
                point.field(field, float(status[field]) if status[field] is not None else -1.0)
            points.append(point.time(now, WritePrecision.NS))
        with self._lock:
            self.write_api.write(bucket=self.bucket, record=points)
