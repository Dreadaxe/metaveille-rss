import unittest
from datetime import datetime, timezone
from check_freshness import freshness

NOW = datetime(2026, 10, 26, 18, tzinfo=timezone.utc)

class FreshnessTests(unittest.TestCase):
    def test_stale_publications(self):
        state = {"posts": {"1": {"published_at": "2026-10-14T17:56:17Z"}}}
        result = freshness(state, NOW)
        self.assertTrue(result["stale"])
        self.assertEqual(result["published_last_7_days"], 0)

    def test_recent_publication(self):
        state = {"posts": {"1": {"published_at": "2026-10-25T12:00:00Z"}}}
        result = freshness(state, NOW)
        self.assertFalse(result["stale"])
        self.assertEqual(result["published_last_7_days"], 1)

    def test_placeholder_not_counted(self):
        state = {"posts": {"1": {"published_at": "", "placeholder": True}}}
        self.assertEqual(freshness(state, NOW)["total_posts"], 0)

if __name__ == "__main__":
    unittest.main()
