import unittest
from audit_apify_input import redact_input

class TestRedaction(unittest.TestCase):
    def test_secrets_not_logged(self):
        data = {"resultsLimit": 20, "sort": "RECENT", "cookies": "secret",
                "proxyConfiguration": {"password": "secret"},
                "startUrls": [{"url": "https://www.facebook.com/groups/example/"}]}
        result = redact_input(data)
        self.assertEqual(result["settings"]["resultsLimit"], 20)
        self.assertEqual(result["settings"]["startUrls_count"], 1)
        self.assertNotIn("cookies", result["settings"])
        self.assertNotIn("proxyConfiguration", result["settings"])
        self.assertNotIn("secret", str(result))

if __name__ == "__main__":
    unittest.main()
