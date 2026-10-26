import unittest
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo
from start_weekly_comments import run_once

TZ = ZoneInfo("Europe/Paris")

class WeeklyCollectionTests(unittest.TestCase):
    def test_existing_week_run_does_not_start_another(self):
        with patch("start_weekly_comments.request", return_value={"items":[{"id":"old","startedAt":"2026-10-25T18:00:00Z","status":"SUCCEEDED"}]}) as api:
            self.assertFalse(run_once("test", datetime(2026,10,25,20,tzinfo=TZ)))
            self.assertEqual(api.call_count, 1)

    def test_previous_week_allows_one_new_run(self):
        def fake(path, token, method="GET"):
            return {"items":[{"startedAt":"2026-10-18T17:00:00Z"}]} if method == "GET" else {"id":"new","status":"READY"}
        with patch("start_weekly_comments.request", side_effect=fake) as api:
            self.assertTrue(run_once("test", datetime(2026,10,25,19,tzinfo=TZ)))
            self.assertEqual(api.call_count, 2)
            self.assertEqual(api.call_args.kwargs["method"], "POST")

if __name__ == "__main__":
    unittest.main()
