import copy
import json
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from wan_html_inputs import decode, transformed, verify_trial, verify_pair, verify_capture, FIRST_PAGE


class WanHtmlInputsTest(unittest.TestCase):
    def test_original_backend_and_native_log_bytes_are_required_inside_cpu_window(self):
        rows = self.rows()
        setup, after = self.state(rows[:10]), self.state(rows)
        after.update(status='ORIGINAL_TWELVE_SWIPES_COMPLETED', action_start_monotonic=3, action_end_monotonic=4)
        after['raw_logs'] = ('100.000000001 42 43 I tag/org.example.wan.ohos/network: get: '
                            'https://www.wanandroid.com/article/list/1/json?page=1&page_size=10\n'
                            '100.000000002 42 43 I tag/org.example.wan.ohos/network: (200) response: {"curPage":2}')
        backend = {'errorCode': 0, 'data': {'datas': rows[:10]}}
        observation = {'setup': setup, 'after': after, 'backend': backend,
                       'progress': verify_trial(setup, after, backend, 'unfixed')}
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            (directory/'native-logs').mkdir()
            raw = json.dumps(backend).encode()
            (directory/'backend-first-page.json').write_bytes(raw)
            for label, state, ended in (('setup', setup, 2), ('after', after, 6)):
                logs = state['raw_logs'].encode()
                (directory/'native-logs'/(label+'.stdout.bin')).write_bytes(logs)
                (directory/'native-logs'/(label+'.stderr.bin')).write_bytes(b'')
                state['native_log_receipt'] = {'raw_sha256': hashlib.sha256(logs).hexdigest(),
                                               'stderr_sha256': hashlib.sha256(b'').hexdigest(),
                                               'ended_monotonic': ended}
            prep = {'variant': 'unfixed', 'backend_url': FIRST_PAGE,
                    'backend_raw_sha256': hashlib.sha256(raw).hexdigest(),
                    'sha256': hashlib.sha256(json.dumps(rows[:10], ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
                    'normal_online_first_page_verified': True, 'native_preferences_written_by_evaluator': False}
            self.assertEqual(verify_capture(observation, prep, 3, 7, [42], directory), observation['progress'])
            for bad in (dict(prep, native_preferences_written_by_evaluator=True), dict(prep, backend_raw_sha256='0'*64)):
                with self.assertRaises(ValueError):
                    verify_capture(observation, bad, 3, 7, [42], directory)
            with self.assertRaises(ValueError):
                verify_capture(observation, prep, 3, 5, [42], directory)
            (directory/'native-logs/after.stdout.bin').write_bytes(b'changed')
            with self.assertRaises(ValueError):
                verify_capture(observation, prep, 3, 7, [42], directory)

    def rows(self):
        return [{'id': i+1, 'title': f'Article {i} &amp; &ldquo;title&rdquo;',
                 'chapterName': 'A &gt; B', 'desc': '&amp;quot;description&amp;quot;',
                 'author': 'ordinary author'} for i in range(20)]

    def state(self, rows):
        root = ET.Element('preferences')
        ET.SubElement(root, 'string', {'key': 'homeList'}).text = json.dumps(rows)
        return {'pid': 42, 'stat': '42 (wan) '+' '.join(['S']+['0']*18+['999']+['0']*5),
                'raw_preferences': ET.tostring(root, encoding='unicode'),
                'layout': {'attributes': {'bundleName': 'org.example.wan.ohos'},
                           'children': [{'attributes': {'text': decode(rows[-1]['title'])}}]},
                'raw_logs': ''}

    def test_source_order_is_not_recursive_or_a_generic_html_decoder(self):
        self.assertEqual(decode('&amp;lt; &amp;quot; &#x41; &mdash;'), '&lt; " &#x41; —')
        rows = self.rows()
        original = copy.deepcopy(rows)
        fixed = transformed(rows)
        self.assertEqual(fixed[0]['desc'], '"description"')
        self.assertEqual(fixed[0]['chapterName'], 'A > B')
        self.assertEqual(rows, original)

    def test_complete_paired_business_data_must_match_not_just_ids(self):
        u = self.state(self.rows())
        fixed = transformed(self.rows())
        self.assertTrue(verify_pair(u, self.state(fixed))['same_complete_business_data_after_exact_transform'])
        fixed[0]['author'] = 'different body'
        with self.assertRaises(ValueError):
            verify_pair(u, self.state(fixed))

    def test_real_progress_first_page_rendering_and_process_identity_are_required(self):
        rows = self.rows()
        setup, after = self.state(rows[:10]), self.state(rows)
        after.update(status='ORIGINAL_TWELVE_SWIPES_COMPLETED', action_start_monotonic=2, action_end_monotonic=3)
        after['raw_logs'] = ('100.000000001 42 43 I tag/org.example.wan.ohos/network: get: '
                            'https://www.wanandroid.com/article/list/1/json?page=1&page_size=10\n'
                            '100.000000002 42 43 I tag/org.example.wan.ohos/network: (200) response: {"curPage":2}')
        backend = {'errorCode': 0, 'data': {'datas': rows[:10]}}
        self.assertEqual(verify_trial(setup, after, backend, 'unfixed')['final_ids'], list(range(1,21)))
        for kind in ('pid', 'body', 'network', 'render'):
            left, right, api = copy.deepcopy((setup, after, backend))
            if kind == 'pid':
                right['pid'] = 43
            if kind == 'body':
                api['data']['datas'][0]['author'] = 'changed'
            if kind == 'network':
                right['raw_logs'] = ''
            if kind == 'render':
                right['layout']['children'] = []
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                verify_trial(left, right, api, 'unfixed')
