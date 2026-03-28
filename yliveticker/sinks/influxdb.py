from yliveticker.sinks.base import BaseTSDBSink
import influxdb_client
from influxdb_client.client.write_api import SYNCHRONOUS
from datetime import datetime, timezone

class InfluxDBSink(BaseTSDBSink):
    def __init__(self, url, token, org, bucket, batch_size=100, flush_interval=5.0):
        super().__init__(batch_size=batch_size, flush_interval=flush_interval)
        self.client = influxdb_client.InfluxDBClient(url=url, token=token, org=org)
        self.write_api = self.client.write_api(write_options=SYNCHRONOUS)
        self.bucket = bucket

    def write_batch(self, batch):
        points = []
        for msg in batch:
            point = influxdb_client.Point("ticker") \
                .tag("id", msg.get('id')) \
                .field("price", float(msg.get('price'))) \
                .field("volume", float(msg.get('dayVolume'))) \
                .time(datetime.fromtimestamp(msg.get('timestamp') / 1000, tz=timezone.utc))
            points.append(point)
        
        self.write_api.write(bucket=self.bucket, record=points)

    def stop(self):
        super().stop()
        self.client.close()
