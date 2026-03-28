import time
from yliveticker.sinks.questdb import QuestDBSink
import requests
import json

# Configuration for local QuestDB (default ports)
HOST = "localhost"
TCP_PORT = 9009
HTTP_PORT = 9000

def verify():
    print("Initializing QuestDBSink...")
    sink = QuestDBSink(host=HOST, port=TCP_PORT, table_name="tickers", batch_size=1)
    
    # Mock some ticker data
    # QuestDB timestamp for 'at' should be in microseconds or nanoseconds depending on sender
    # In my sink implementation: timestamp = int(msg.get('timestamp') * 1000) # nanoseconds for questdb
    msg = {
        'id': 'QUEST_TICKER',
        'price': 789.01,
        'dayVolume': 20000,
        'timestamp': int(time.time() * 1000)
    }
    
    print(f"Writing mock message to QuestDB via ILP: {msg}")
    sink.on_ticker(None, msg)
    
    # ILP is asynchronous, give it a moment to commit
    time.sleep(2)
    
    print("Verifying data in QuestDB via HTTP SQL API...")
    query = "select * from tickers where id = 'QUEST_TICKER'"
    response = requests.get(f"http://{HOST}:{HTTP_PORT}/exec", params={'query': query})
    
    if response.status_code == 200:
        data = response.json()
        print(f"Response from QuestDB: {json.dumps(data)}")
        if data.get('count', 0) > 0:
            row = data['dataset'][0]
            # Column order might vary but usually it's [timestamp, id, price, volume] 
            # or based on how ILP created the table
            print(f"Record found in QuestDB: {row}")
            print("\nSUCCESS: Data correctly written and verified in QuestDB!")
        else:
            print("\nFAILURE: Could not find the written data in QuestDB.")
            exit(1)
    else:
        print(f"\nFAILURE: QuestDB query failed with status {response.status_code}")
        exit(1)

if __name__ == "__main__":
    verify()
