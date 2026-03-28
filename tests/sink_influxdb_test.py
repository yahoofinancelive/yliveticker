import unittest
from unittest.mock import MagicMock, patch
from yliveticker.sinks.influxdb import InfluxDBSink
from datetime import datetime, timezone

class TestInfluxDBSink(unittest.TestCase):
    @patch('influxdb_client.InfluxDBClient')
    def test_write_batch(self, MockClient):
        # Setup mock
        mock_instance = MockClient.return_value
        mock_write_api = MagicMock()
        mock_instance.write_api.return_value = mock_write_api
        
        sink = InfluxDBSink(url="http://localhost:8086", token="token", org="org", bucket="bucket")
        
        # Sample ticker message
        msg = {
            'id': 'AAPL',
            'price': 150.0,
            'dayVolume': 1000000,
            'timestamp': 1600000000000 # 2020-09-13 12:26:40 UTC
        }
        
        # Test write_batch
        sink.write_batch([msg])
        
        # Verify write_api.write was called
        self.assertTrue(mock_write_api.write.called)
        
        # Extract the point sent to write
        args, kwargs = mock_write_api.write.call_args
        sent_points = kwargs['record']
        self.assertEqual(len(sent_points), 1)
        
        point = sent_points[0]
        self.assertEqual(point._name, "ticker")
        self.assertEqual(point._tags['id'], "AAPL")
        self.assertEqual(point._fields['price'], 150.0)
        self.assertEqual(point._fields['volume'], 1000000.0)
        
        # Verify timestamp (2020-09-13 12:26:40 UTC)
        expected_dt = datetime.fromtimestamp(1600000000, tz=timezone.utc)
        self.assertEqual(point._time, expected_dt)

if __name__ == '__main__':
    unittest.main()
