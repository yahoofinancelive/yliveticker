import time
from yliveticker.sinks.influxdb import InfluxDBSink
import influxdb_client
from influxdb_client.client.write_api import SYNCHRONOUS

# Configuration for InfluxDB (matches docker-compose.yml and local influxd setup)
URL = "http://localhost:8086"
TOKEN = "my-super-secret-auth-token"
ORG = "yliveticker"
BUCKET = "ticker_data"

def verify():
    print("Initializing InfluxDBSink...")
    sink = InfluxDBSink(url=URL, token=TOKEN, org=ORG, bucket=BUCKET, batch_size=1)
    
    # Mock some ticker data
    msg = {
        'id': 'TEST_TICKER',
        'price': 123.45,
        'dayVolume': 5000,
        'timestamp': int(time.time() * 1000)
    }
    
    print(f"Writing mock message to InfluxDB: {msg}")
    sink.on_ticker(None, msg)
    
    # Give it a moment to flush (though batch_size=1 and it should be synchronous in this implementation)
    time.sleep(1)
    
    print("Verifying data in InfluxDB...")
    client = influxdb_client.InfluxDBClient(url=URL, token=TOKEN, org=ORG)
    query_api = client.query_api()
    
    query = f'from(bucket: "{BUCKET}") |> range(start: -1m) |> filter(fn: (r) => r["_measurement"] == "ticker")'
    result = query_api.query(org=ORG, query=query)
    
    found_price = False
    found_volume = False
    
    for table in result:
        for record in table.records:
            print(f"Record found: {record.get_field()} = {record.get_value()} for symbol {record['id']}")
            if record.get_field() == "price" and record.get_value() == 123.45:
                found_price = True
            if record.get_field() == "volume" and record.get_value() == 5000.0:
                found_volume = True

    if found_price and found_volume:
        print("\nSUCCESS: Data correctly written and verified in InfluxDB!")
    else:
        print("\nFAILURE: Could not find the written data in InfluxDB.")
        exit(1)

if __name__ == "__main__":
    verify()
