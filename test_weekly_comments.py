import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo
from start_weekly_comments import run_once, select_posts

TZ = ZoneInfo("Europe/Paris")
NOW = datetime(2026, 10, 25, 19, tzinfo=TZ)
POST = "1587557222607690"
STATE = {"posts": {POST: {"id": POST, "url": f"https://www.facebook.com/groups/warhammerquestfr/posts/{POST}/",
                           "published_at": "2026-10-22T12:29:29Z", "comments": {}}}}


class WeeklyCollectionTests(unittest.TestCase):
    def test_recent_selection(self):
        self.assertEqual(len(select_posts(STATE, NOW)), 1)
        self.assertEqual(select_posts({"posts": {}}, NOW), [])

    def test_existing_week_run_does_not_start_another(self):
        with patch("start_weekly_comments.request", return_value={"items": [
                {"id": "old", "startedAt": "2026-10-25T18:00:00Z", "status": "SUCCEEDED"}]}) as api:
            self.assertFalse(run_once("test", NOW))
            self.assertEqual(api.call_count, 1)

    def test_no_recent_posts_no_paid_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_file = Path(tmp) / "state.json"
            state_file.write_text('{"posts":{}}')
            with patch("start_weekly_comments.request", return_value={"items": []}) as api:
                self.assertFalse(run_once("test", NOW, state_file))
                self.assertEqual(api.call_count, 1)

    def test_input_override_preserves_options(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_file = Path(tmp) / "state.json"
            state_file.write_text(json.dumps(STATE))
            calls = []
            def fake(path, token, method="GET", payload=None):
                calls.append((path, method, payload))
                if path.startswith("/runs?"):
                    return {"items": []}
                if path == "/input":
                    return {"resultsLimit": 20, "includeNestedComments": True, "startUrls": [{"url": "old"}]}
                if path == "/runs" and method == "POST":
                    return {"id": "new", "status": "READY"}
                raise AssertionError(path)
            with patch("start_weekly_comments.request", side_effect=fake):
                self.assertTrue(run_once("test", NOW, state_file))
            sent = calls[-1][2]
            self.assertEqual(sent["resultsLimit"], 20)
            self.assertTrue(sent["includeNestedComments"])
            self.assertEqual(sent["onlyCommentsNewerThan"], "2026-10-19")
            self.assertIn(POST, sent["startUrls"][0]["url"])

if __name__ == "__main__":
    unittest.main()
