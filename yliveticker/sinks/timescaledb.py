from yliveticker.sinks.base import BaseTSDBSink
import psycopg2
from psycopg2.extras import execute_values
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)

class TimescaleDBSink(BaseTSDBSink):
    def __init__(self, dsn, table_name="tickers", batch_size=100, flush_interval=5.0):
        super().__init__(batch_size=batch_size, flush_interval=flush_interval)
        self.conn = psycopg2.connect(dsn)
        self.table_name = table_name
        self._create_table()

    def _create_table(self):
        try:
            with self.conn.cursor() as cur:
                cur.execute(f"""
                    CREATE TABLE IF NOT EXISTS {self.table_name} (
                        time TIMESTAMPTZ NOT NULL,
                        symbol TEXT NOT NULL,
                        price DOUBLE PRECISION,
                        volume DOUBLE PRECISION
                    );
                    SELECT create_hypertable('{self.table_name}', 'time', if_not_exists => TRUE);
                """)
        except psycopg2.Error as e:
            if "create_hypertable" in str(e):
                logger.warning("TimescaleDB extension not found, using standard PostgreSQL table.")
                self.conn.rollback()
                # Create standard table instead
                with self.conn.cursor() as cur:
                    cur.execute(f"""
                        CREATE TABLE IF NOT EXISTS {self.table_name} (
                            time TIMESTAMPTZ NOT NULL,
                            symbol TEXT NOT NULL,
                            price DOUBLE PRECISION,
                            volume DOUBLE PRECISION
                        );
                    """)
            else:
                raise e
        self.conn.commit()

    def write_batch(self, batch):
        values = []
        for msg in batch:
            dt = datetime.fromtimestamp(msg.get('timestamp') / 1000, tz=timezone.utc)
            values.append((dt, msg.get('id'), float(msg.get('price')), float(msg.get('dayVolume'))))
        
        with self.conn.cursor() as cur:
            execute_values(cur, f"INSERT INTO {self.table_name} (time, symbol, price, volume) VALUES %s", values)
            self.conn.commit()

    def stop(self):
        super().stop()
        self.conn.close()
