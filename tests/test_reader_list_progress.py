import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from reader_list_progress import BUNDLE, verify_observation, verify_capture


class ArticleRenderingTest(unittest.TestCase):
    def observation(self):
        layout = {'attributes': {'bundleName': BUNDLE}, 'children': [
            {'attributes': {'text': '300 篇'}},
            {'attributes': {'text': 'Journal 10 article 100', 'visible': 'true'}}]}
        obs = {'before': {'pid': 42, 'layout': layout, 'started_monotonic': 1, 'ended_monotonic': 2},
               'after': {'pid': 43, 'layout': copy.deepcopy(layout), 'started_monotonic': 5, 'ended_monotonic': 6}}
        obs['progress'] = verify_observation(obs)
        return obs

    def test_fresh_process_renders_business_titles(self):
        self.assertEqual(verify_capture(self.observation(), 3, 7, [43])['loaded_articles'], 300)

    def test_no_process_reconstruction_or_wrong_attribution_rejected(self):
        obs = self.observation()
        obs['after']['pid'] = 42
        with self.assertRaises(ValueError):
            verify_observation(obs)
        with self.assertRaises(ValueError):
            verify_capture(self.observation(), 3, 7, [44])

    def test_header_without_articles_or_other_app_titles_rejected(self):
        for change in ('remove', 'other_bundle'):
            obs = self.observation()
            article = obs['after']['layout']['children'][1]
            if change == 'remove':
                article['attributes']['text'] = 'No articles'
            else:
                article['attributes']['bundleName'] = 'observer'
            with self.assertRaises(ValueError):
                verify_observation(obs)

    def test_rendering_outside_capture_rejected(self):
        with self.assertRaises(ValueError):
            verify_capture(self.observation(), 3, 5.5, [43])


if __name__ == '__main__':
    unittest.main()
