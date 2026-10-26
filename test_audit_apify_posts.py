import unittest
from datetime import datetime, timezone
from audit_apify_posts import summarize

class AuditPostsTests(unittest.TestCase):
    def test_accepted_and_rejected(self):
        good = {"facebookId": "309721797057912", "id": "123",
                "url": "https://www.facebook.com/groups/warhammerquestfr/posts/123/",
                "time": "2026-10-25T10:00:00Z"}
        wrong = dict(good, facebookId="999", facebookUrl="https://www.facebook.com/groups/999/", inputUrl="https://www.facebook.com/groups/999/")
        bad = dict(good, id="124", url="http://example.com/post")
        report = summarize([good, wrong, bad], datetime(2026, 10, 26, tzinfo=timezone.utc))
        self.assertEqual(report["accepted"], 1)
        self.assertEqual(report["unique_ids"], 1)
        self.assertEqual(report["rejected"]["wrong_group"], 1)
        self.assertEqual(report["rejected"]["unsafe_url"], 1)
        self.assertEqual(report["newest_age_days"], 0.6)

if __name__ == "__main__":
    unittest.main()
