from yliveticker.sinks.base import BaseTSDBSink
import boto3
from botocore.config import Config

class TimestreamSink(BaseTSDBSink):
    def __init__(self, database_name, table_name, region_name=None, batch_size=100, flush_interval=5.0, **sink_options):
        # Timestream has a limit of 100 records per write_records call
        if batch_size > 100:
            batch_size = 100
        self.client = boto3.client('timestream-write', region_name=region_name, config=Config(
            connect_timeout=5, read_timeout=5,
            retries={"total_max_attempts": 2, "mode": "standard"}))
        self.database_name = database_name
        self.table_name = table_name
        super().__init__(batch_size=batch_size, flush_interval=flush_interval, **sink_options)

    def write_batch(self, batch):
        # Even if batch_size is set to 100, let's ensure we chunk it just in case
        for i in range(0, len(batch), 100):
            chunk = batch[i:i + 100]
            records = []
            for msg in chunk:
                record = {
                    'Dimensions': [
                        {'Name': 'symbol', 'Value': msg.get('id')}
                    ],
                    'MeasureName': 'ticker_data',
                    'MeasureValueType': 'MULTI',
                    'MeasureValues': [
                        {'Name': 'price', 'Value': str(msg.get('price')), 'Type': 'DOUBLE'},
                        {'Name': 'volume', 'Value': str(msg.get('dayVolume')), 'Type': 'DOUBLE'}
                    ],
                    'Time': str(int(msg.get('timestamp'))),
                    'TimeUnit': 'MILLISECONDS'
                }
                records.append(record)
            
            self.client.write_records(
                DatabaseName=self.database_name,
                TableName=self.table_name,
                Records=records
            )

    def stop(self):
        try:
            super().stop()
        finally:
            self.client.close()
