import unittest
from datetime import date
from build_rss import heading, rss_xml, GROUP_NAME
from datetime import datetime, timezone
from xml.etree import ElementTree as ET

class TestRssTitle(unittest.TestCase):
    def test_no_repeated_group_name_in_combined_subject(self):
        info = {"start": date(2026,10,19), "end": date(2026,10,25),
                "year": 2026, "week": 43, "posts": [], "new_post_count": 0,
                "new_comment_count": 0}
        rss = ET.fromstring(rss_xml([info], "https://example.org/", datetime(2026,10,26,tzinfo=timezone.utc)))
        channel_title = rss.findtext("./channel/title")
        item_title = rss.findtext("./channel/item/title")
        self.assertIn(GROUP_NAME, channel_title)
        self.assertNotIn(GROUP_NAME, item_title)
        self.assertEqual(item_title, "Semaine 43 — Bilan du 19/10/2026 au 25/10/2026")
        self.assertEqual((channel_title + " — " + item_title).count(GROUP_NAME), 1)

if __name__ == "__main__":
    unittest.main()
