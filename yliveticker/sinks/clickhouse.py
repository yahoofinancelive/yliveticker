from yliveticker.sinks.base import BaseTSDBSink
import clickhouse_connect
from datetime import datetime, timezone

class ClickHouseSink(BaseTSDBSink):
    def __init__(self, host='localhost', port=8123, username='default', password='', database='default', table_name='tickers', batch_size=100, flush_interval=5.0, **sink_options):
        if not table_name.isidentifier():
            raise ValueError("table_name must be a simple SQL identifier")
        self.client = clickhouse_connect.get_client(host=host, port=port, username=username, password=password, database=database, connect_timeout=5, send_receive_timeout=5)
        self.table_name = table_name
        try:
            self._create_table()
        except Exception:
            self.client.close()
            raise
        super().__init__(batch_size=batch_size, flush_interval=flush_interval, **sink_options)

    def _create_table(self):
        self.client.command(f"""
            CREATE TABLE IF NOT EXISTS {self.table_name} (
                time DateTime64(3, 'UTC'),
                symbol String,
                price Float64,
                volume Float64
            ) ENGINE = MergeTree()
            ORDER BY (symbol, time)
        """)

    def write_batch(self, batch):
        data = []
        for msg in batch:
            dt = datetime.fromtimestamp(msg.get('timestamp') / 1000, tz=timezone.utc)
            data.append([dt, msg.get('id'), float(msg.get('price')), float(msg.get('dayVolume'))])
        
        self.client.insert(self.table_name, data, column_names=['time', 'symbol', 'price', 'volume'])

    def stop(self):
        try:
            super().stop()
        finally:
            self.client.close()
