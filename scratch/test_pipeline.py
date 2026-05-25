import sys
import os
import unittest
from unittest.mock import MagicMock, patch

# Ensure /app is in python path
sys.path.insert(0, '/app')

import redis
from config import CELERY_BROKER_URL

class TestPipelineCompletionLogic(unittest.TestCase):
    def setUp(self):
        self.r = redis.Redis.from_url(CELERY_BROKER_URL)
        self.run_id = "test-run-123"
        self.active_key = f"pipeline:{self.run_id}:active_actors"
        self.in_flight_key = f"pipeline:{self.run_id}:in_flight"
        self.dispatched_key = f"pipeline:{self.run_id}:dispatched_at"
        self.summary_sent_key = f"pipeline:{self.run_id}:summary_sent"
        
        # Clean up keys
        self.r.delete(self.active_key, self.in_flight_key, self.dispatched_key, self.summary_sent_key)

    def tearDown(self):
        self.r.delete(self.active_key, self.in_flight_key, self.dispatched_key, self.summary_sent_key)

    @patch('tasks.pipeline.send_discord_summary.delay')
    def test_normal_completion(self, mock_discord_delay):
        from tasks.ranking import _check_and_trigger_discord
        
        # Simulate scrapers active, 2 jobs in flight
        self.r.set(self.active_key, 1)
        self.r.sadd(self.in_flight_key, 100, 200)
        self.r.hset(self.dispatched_key, 100, "100.0")
        self.r.hset(self.dispatched_key, 200, "200.0")
        
        # First job finishes. Scrapers still active (active=1).
        _check_and_trigger_discord(self.run_id, 100)
        self.assertFalse(self.r.sismember(self.in_flight_key, 100))
        self.assertTrue(self.r.sismember(self.in_flight_key, 200))
        self.assertFalse(self.r.hexists(self.dispatched_key, 100))
        mock_discord_delay.assert_not_called()
        
        # Scrapers finish (active=0).
        self.r.set(self.active_key, 0)
        
        # Second job finishes. Now active=0 and in_flight=0.
        _check_and_trigger_discord(self.run_id, 200)
        self.assertFalse(self.r.sismember(self.in_flight_key, 200))
        mock_discord_delay.assert_called_once_with(self.run_id)

    @patch('tasks.pipeline.send_discord_summary.delay')
    def test_duplicate_completion_does_not_double_trigger(self, mock_discord_delay):
        from tasks.ranking import _check_and_trigger_discord
        
        # Simulate active=0, 2 jobs in flight
        self.r.set(self.active_key, 0)
        self.r.sadd(self.in_flight_key, 100, 200)
        
        # Job A finishes first time
        _check_and_trigger_discord(self.run_id, 100)
        mock_discord_delay.assert_not_called()
        
        # Job A finishes second time (duplicate delivery)
        _check_and_trigger_discord(self.run_id, 100)
        mock_discord_delay.assert_not_called()
        
        # Job B finishes. Completes pipeline.
        _check_and_trigger_discord(self.run_id, 200)
        mock_discord_delay.assert_called_once_with(self.run_id)

    @patch('tasks.pipeline.send_discord_summary.delay')
    def test_reconciler_sweeps_timeout(self, mock_discord_delay):
        import time
        from tasks.pipeline import check_pipeline_completion
        
        # Simulate active=0 (scrapers finished)
        self.r.set(self.active_key, 0)
        
        # Job A (timed out), Job B (active)
        now = time.time()
        self.r.sadd(self.in_flight_key, 100, 200)
        self.r.hset(self.dispatched_key, 100, str(now - 400)) # 400 seconds ago (> 300s timeout)
        self.r.hset(self.dispatched_key, 200, str(now - 30))  # 30 seconds ago
        
        # Run completion check. It should retry because Job B is still in flight and not timed out.
        with self.assertRaises(Exception):
            check_pipeline_completion(self.run_id)
            
        # Verify Job A was swept, Job B remains
        self.assertFalse(self.r.sismember(self.in_flight_key, 100))
        self.assertTrue(self.r.sismember(self.in_flight_key, 200))
        self.assertFalse(self.r.hexists(self.dispatched_key, 100))
        self.assertTrue(self.r.hexists(self.dispatched_key, 200))
        mock_discord_delay.assert_not_called()
        
        # Now make Job B also timed out
        self.r.hset(self.dispatched_key, 200, str(now - 400))
        
        # Run completion check again. Both are now timed out. It should complete and send Discord.
        res = check_pipeline_completion(self.run_id)
        self.assertEqual(res, {"status": "completed_by_reconciler"})
        self.assertFalse(self.r.exists(self.active_key))
        self.assertFalse(self.r.exists(self.in_flight_key))
        mock_discord_delay.assert_called_once_with(self.run_id)

if __name__ == '__main__':
    unittest.main()
