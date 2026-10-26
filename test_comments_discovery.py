import unittest
from datetime import datetime, timezone
from unittest.mock import patch
from build_rss import initial_state, sync_comments_runs, COMMENTS_ACTOR_ID

POST = '1587557222607690'
COMMENT = '1601080907921988'
ITEM = {'facebookId': POST, 'facebookUrl': f'https://www.facebook.com/groups/warhammerquestfr/posts/{POST}/', 'commentUrl': f'https://www.facebook.com/groups/warhammerquestfr/posts/{POST}/?comment_id={COMMENT}', 'commentId': COMMENT, 'date': '2026-10-22T12:29:29Z', 'text': 'Test', 'profileName': 'Auteur'}
RUN = {'id': 'run123', 'actId': COMMENTS_ACTOR_ID, 'status': 'SUCCEEDED', 'finishedAt': '2026-10-26T12:00:00Z', 'defaultDatasetId': 'dataset123'}

class TestCommentsDiscovery(unittest.TestCase):
    def test_discovery_and_idempotence(self):
        calls = []
        def fake_api(path, token):
            calls.append(path)
            if path.startswith('/v2/actor-runs?'):
                return {'data': {'items': [dict(RUN), dict(RUN, id='other', actId='otheractor')]}}
            if path.startswith('/v2/datasets/dataset123/items?'):
                return [ITEM]
            raise AssertionError('Unexpected API call: ' + path)
        state = initial_state()
        now = datetime(2026, 10, 26, 18, tzinfo=timezone.utc)
        with patch('build_rss.api_json', side_effect=fake_api):
            first = sync_comments_runs(state, 'test-token', now=now)
            second = sync_comments_runs(state, 'test-token', now=now)
        self.assertEqual(first['comments_added'], 1)
        self.assertEqual(first['runs_imported'], 1)
        self.assertEqual(second['runs_imported'], 0)
        self.assertEqual(len([p for p in calls if '/datasets/' in p]), 1)
        self.assertIn(COMMENT, state['posts'][POST]['comments'])

if __name__ == '__main__':
    unittest.main()
