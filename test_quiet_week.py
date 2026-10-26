import unittest
from datetime import date
from build_rss import activity_notice, rss_summary, document

class TestQuietWeek(unittest.TestCase):
    def info(self, posts=0, comments=0):
        return {'start': date(2026,10,19), 'end': date(2026,10,25), 'year':2026,'week':43,
                'new_post_count':posts,'new_comment_count':comments,'posts':[]}
    def test_no_activity(self):
        i=self.info()
        self.assertIn('Aucune nouvelle publication ni aucun nouveau commentaire',rss_summary(i))
        self.assertIn('Aucune nouvelle publication ni aucun nouveau commentaire',document(i,'https://example.org/'))
    def test_comments_only(self):
        i=self.info(comments=1)
        self.assertIn('sur des publications antérieures',rss_summary(i))
    def test_new_posts(self):
        self.assertEqual(activity_notice(self.info(posts=1)),'')

if __name__ == '__main__':
    unittest.main()
