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
        self.addCleanup(sink.stop)
        
        # Sample ticker message
        msg = {
            'id': 'AAPL',
            'currency': 'USD',
            'price': 150.0,
            'dayVolume': 1000000,
            'timestamp': 1600000000000, # 2020-09-13 12:26:40 UTC
            '_received_at_ns': 1600000000123456789,
        }
        
        # Test write_batch
        sink.write_batch([msg])
        
        # Verify write_api.write was called
        self.assertTrue(mock_write_api.write.called)
        
        # Extract the point sent to write
        args, kwargs = mock_write_api.write.call_args
        sent_points = kwargs['record']
        self.assertEqual(len(sent_points), 2)
        
        point = next(point for point in sent_points if point._name == "ticker")
        self.assertEqual(point._name, "ticker")
        self.assertEqual(point._tags['id'], "AAPL")
        self.assertEqual(point._tags['currency'], "USD")
        self.assertEqual(point._fields['price'], 150.0)
        self.assertEqual(point._fields['volume'], 1000000.0)
        self.assertEqual(point._fields['volume_available'], 1)
        
        # Verify timestamp (2020-09-13 12:26:40 UTC)
        expected_dt = datetime.fromtimestamp(1600000000, tz=timezone.utc)
        self.assertEqual(point._time, expected_dt)

        received = next(point for point in sent_points if point._name == "ticker_ingest")
        self.assertEqual(received._tags['id'], "AAPL")
        self.assertEqual(received._fields['count'], 1)
        self.assertEqual(received._time, 1600000000123456789)

    @patch('influxdb_client.InfluxDBClient')
    def test_zero_volume_is_treated_as_unavailable(self, MockClient):
        mock_write_api = MockClient.return_value.write_api.return_value
        sink = InfluxDBSink(url="http://localhost:8086", token="token", org="org", bucket="bucket")
        self.addCleanup(sink.stop)

        sink.write_batch([{
            'id': 'EURUSD=X',
            'price': 1.16,
            'dayVolume': 0,
            'timestamp': 1600000000000,
            '_received_at_ns': 1600000000123456789,
        }])

        points = mock_write_api.write.call_args.kwargs['record']
        self.assertEqual(len(points), 2)
        point = next(point for point in points if point._name == "ticker")
        self.assertEqual(point._fields['price'], 1.16)
        self.assertEqual(point._fields['volume_available'], 0)
        self.assertNotIn('volume', point._fields)

    @patch('influxdb_client.InfluxDBClient')
    def test_missing_currency_does_not_create_an_empty_tag(self, MockClient):
        mock_write_api = MockClient.return_value.write_api.return_value
        sink = InfluxDBSink(url="http://localhost:8086", token="token", org="org", bucket="bucket")
        self.addCleanup(sink.stop)

        sink.write_batch([{
            'id': 'UNKNOWN',
            'currency': '',
            'price': 10,
            'dayVolume': 1,
            'timestamp': 1600000000000,
            '_received_at_ns': 1600000000123456789,
        }])

        point = next(point for point in mock_write_api.write.call_args.kwargs['record']
                     if point._name == "ticker")
        self.assertNotIn('currency', point._tags)

if __name__ == '__main__':
    unittest.main()
