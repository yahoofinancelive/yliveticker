import time
from yliveticker.sinks.timescaledb import TimescaleDBSink
import psycopg2
from datetime import datetime, timezone

# Configuration for local PostgreSQL
DSN = "dbname=yliveticker user=yliveticker password=yliveticker host=localhost"

def verify():
    print("Initializing TimescaleDBSink (PostgreSQL mode)...")
    sink = TimescaleDBSink(dsn=DSN, batch_size=1)
    
    # Mock some ticker data
    msg = {
        'id': 'TEST_TICKER',
        'price': 456.78,
        'dayVolume': 10000,
        'timestamp': int(time.time() * 1000)
    }
    
    print(f"Writing mock message to PostgreSQL: {msg}")
    sink.on_ticker(None, msg)
    
    # Give it a moment to flush
    time.sleep(1)
    
    print("Verifying data in PostgreSQL...")
    conn = psycopg2.connect(DSN)
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM tickers WHERE symbol = 'TEST_TICKER'")
        row = cur.fetchone()
        
        if row:
            print(f"Record found: Time={row[0]}, Symbol={row[1]}, Price={row[2]}, Volume={row[3]}")
            if row[1] == 'TEST_TICKER' and float(row[2]) == 456.78 and float(row[3]) == 10000.0:
                 print("\nSUCCESS: Data correctly written and verified in PostgreSQL!")
            else:
                 print("\nFAILURE: Data found but values do not match.")
                 exit(1)
        else:
            print("\nFAILURE: Could not find the written data in PostgreSQL.")
            exit(1)
    conn.close()

if __name__ == "__main__":
    verify()
