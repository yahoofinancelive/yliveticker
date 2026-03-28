from yliveticker.sinks.base import BaseTSDBSink
import questdb.ingress as qdb
from datetime import datetime, timezone

class QuestDBSink(BaseTSDBSink):
    def __init__(self, host='localhost', port=9009, table_name='tickers', batch_size=100, flush_interval=5.0):
        super().__init__(batch_size=batch_size, flush_interval=flush_interval)
        self.conf = f"tcp::addr={host}:{port};"
        self.table_name = table_name

    def write_batch(self, batch):
        with qdb.Sender.from_conf(self.conf) as sender:
            for msg in batch:
                timestamp = int(msg.get('timestamp') * 1000) # nanoseconds for questdb
                sender.row(
                    self.table_name,
                    symbols={'id': msg.get('id')},
                    columns={
                        'price': float(msg.get('price')),
                        'volume': float(msg.get('dayVolume'))
                    },
                    at=qdb.TimestampNanos(timestamp)
                )
            sender.flush()
