import unittest
from datetime import date
from build_rss import initial_state, build_week_data
from import_comments import merge_comments_dataset

class TestComments(unittest.TestCase):
    def test_week_and_dedup(self):
        state = initial_state()
        item = {'facebookId':'1587557222607690','facebookUrl':'https://www.facebook.com/groups/warhammerquestfr/posts/1587557222607690/','commentUrl':'https://www.facebook.com/groups/warhammerquestfr/posts/1587557222607690/?comment_id=1601080907921988','commentId':'1601080907921988','date':'2026-10-22T12:29:29.000Z','text':'Commentaire test','profileName':'Auteur test'}
        self.assertEqual(merge_comments_dataset(state,[item],'2026-10-26T16:00:00Z')['comments_added'],1)
        self.assertEqual(merge_comments_dataset(state,[item],'2026-10-26T16:00:00Z')['comments_added'],0)
        info=build_week_data(state,date(2026,10,19))
        self.assertEqual(info['new_comment_count'],1)
        self.assertEqual(info['new_post_count'],0)

if __name__ == '__main__': unittest.main()
