import unittest
from unittest.mock import MagicMock, patch
from yliveticker.sinks.clickhouse import ClickHouseSink
from datetime import datetime, timezone

class TestClickHouseSink(unittest.TestCase):
    @patch('clickhouse_connect.get_client')
    def test_write_batch(self, mock_get_client):
        # Setup mock
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        
        sink = ClickHouseSink(host='localhost', table_name='test_tickers')
        
        # Verify table creation call
        self.assertTrue(mock_client.command.called)
        create_sql = mock_client.command.call_args[0][0]
        self.assertIn("CREATE TABLE IF NOT EXISTS test_tickers", create_sql)
        
        # Sample ticker message
        msg = {
            'id': 'AAPL',
            'price': 150.0,
            'dayVolume': 1000000,
            'timestamp': 1600000000000
        }
        
        # Test write_batch
        sink.write_batch([msg])
        
        # Verify insert was called
        self.assertTrue(mock_client.insert.called)
        args, kwargs = mock_client.insert.call_args
        
        table_name = args[0]
        data = args[1]
        column_names = kwargs['column_names']
        
        self.assertEqual(table_name, 'test_tickers')
        self.assertEqual(column_names, ['time', 'symbol', 'price', 'volume'])
        self.assertEqual(len(data), 1)
        
        row = data[0]
        self.assertEqual(row[1], "AAPL")
        self.assertEqual(row[2], 150.0)
        self.assertEqual(row[3], 1000000.0)
        self.assertEqual(row[0], datetime.fromtimestamp(1600000000, tz=timezone.utc))

if __name__ == '__main__':
    unittest.main()
