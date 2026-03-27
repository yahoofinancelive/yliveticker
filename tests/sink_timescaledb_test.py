import unittest
from unittest.mock import MagicMock, patch
from yliveticker.sinks.timescaledb import TimescaleDBSink
from datetime import datetime, timezone

class TestTimescaleDBSink(unittest.TestCase):
    @patch('psycopg2.connect')
    def test_write_batch(self, mock_connect):
        # Setup mock connection and cursor
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        
        # Instantiate sink (this calls _create_table)
        sink = TimescaleDBSink(dsn="dbname=test user=test")
        
        # Sample ticker message
        msg = {
            'id': 'AAPL',
            'price': 150.0,
            'dayVolume': 1000000,
            'timestamp': 1600000000000
        }
        
        # Mock execute_values directly to avoid internal psycopg2 logic issues with mocks
        with patch('yliveticker.sinks.timescaledb.execute_values') as mock_execute_values:
            sink.write_batch([msg])
            
            # Verify execute_values was called
            self.assertTrue(mock_execute_values.called)
            
            # Check the values passed to execute_values
            # execute_values(cur, sql, values)
            args, _ = mock_execute_values.call_args
            passed_cur = args[0]
            passed_sql = args[1]
            passed_values = args[2]
            
            self.assertEqual(passed_cur, mock_cur)
            self.assertIn("INSERT INTO tickers", passed_sql)
            self.assertEqual(len(passed_values), 1)
            
            dt, symbol, price, volume = passed_values[0]
            self.assertEqual(symbol, "AAPL")
            self.assertEqual(price, 150.0)
            self.assertEqual(volume, 1000000.0)
            self.assertEqual(dt, datetime.fromtimestamp(1600000000, tz=timezone.utc))

if __name__ == '__main__':
    unittest.main()
