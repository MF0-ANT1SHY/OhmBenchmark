import copy
from pathlib import Path
import sys
import hashlib
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from wan_web_progress import URL, verify, completed_pages, verify_capture


class WebRefreshEvidenceTest(unittest.TestCase):
    def test_cpu_window_requires_exact_original_native_bytes(self):
        obs = self.observation()
        obs['after']['ended_monotonic'] = 6
        obs['progress'] = verify(obs)
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)/'native-logs'
            folder.mkdir()
            for label in ('before', 'after'):
                raw = obs[label]['raw_logs'].encode()
                (folder/(label+'.stdout.bin')).write_bytes(raw)
                (folder/(label+'.stderr.bin')).write_bytes(b'')
                obs[label]['raw_sha256'] = hashlib.sha256(raw).hexdigest()
                obs[label]['stderr_sha256'] = hashlib.sha256(b'').hexdigest()
            self.assertEqual(verify_capture(obs, 3, 7, [42], tmp), obs['progress'])
            with self.assertRaises(ValueError):
                verify_capture(obs, 3, 5.5, [42], tmp)
            with self.assertRaises(ValueError):
                verify_capture(obs, 3, 7, [43], tmp)
            (folder/'after.stdout.bin').write_bytes(b'edited')
            with self.assertRaisesRegex(ValueError, 'original bytes'):
                verify_capture(obs, 3, 7, [42], tmp)

    def test_real_arkweb_initial_progress_and_duplicate_completion_order_is_preserved(self):
        rows = [(i, kind, value, str(i)) for i, (kind, value) in enumerate([
            ('progress', '10'), ('begin', URL), ('progress', '20'),
            ('title', 'weekly'), ('progress', '100'), ('end', URL),
            ('progress', '100'), ('progress', '10'), ('begin', URL),
            ('title', 'weekly'), ('progress', '100'), ('end', URL)])]
        pages = completed_pages(rows, 2)
        self.assertEqual([p['progress'] for p in pages], [[10, 20, 100, 100], [10, 100]])
        rows.append((99, 'progress', '10', 'unfinished'))
        with self.assertRaises(ValueError):
            completed_pages(rows, 2)

    def observation(self):
        def page(i):
            messages = ['onPageBegin url: '+URL, 'onProgressChange progress: 25',
                        'onTitleReceive title: weekly - wanandroid.com',
                        'onProgressChange progress: 100', 'onPageEnd url: '+URL]
            return [f'{100+i}.{j:09d} 42 43 I A00000/org.example.wan.ohos/WebPage: {m}'
                    for j, m in enumerate(messages)]
        before = '\n'.join(page(0))
        # stat start_ticks requires the 20th field following the command.
        stat = '42 (wan.ohos) '+' '.join(['S']+['0']*18+['999']+['0']*5)
        return {'pid': 42, 'stat_before': stat, 'stat_after': stat,
                'actions_start_monotonic': 3, 'actions_end_monotonic': 4,
                'before': {'pid': 42, 'ended_monotonic': 2, 'raw_logs': before},
                'after': {'pid': 42, 'started_monotonic': 5,
                          'raw_logs': before+'\n'+'\n'.join(line for i in range(1, 6) for line in page(i))}}

    def test_five_completed_refreshes_expose_actual_log_counts_not_performance(self):
        obs = self.observation()
        original = copy.deepcopy(obs)
        result = verify(obs)
        self.assertEqual(result['completed_refreshes'], 5)
        self.assertEqual(result['progress_logs_per_load'], [2]*5)
        self.assertFalse(result['performance_accepted'])
        self.assertEqual(obs, original)

    def test_incomplete_overlapping_foreign_or_failed_pages_cannot_pass(self):
        for kind in ('incomplete', 'overlap', 'redirect', 'error', 'foreign_pid', 'missing_title'):
            obs = self.observation()
            text = obs['after']['raw_logs']
            if kind == 'incomplete':
                text = '\n'.join(text.splitlines()[:-1])
            if kind == 'overlap':
                text = text.replace('onPageEnd url:', 'ignoredPageEnd url:', 2)
            if kind == 'redirect':
                text = text.replace(URL, 'https://unrelated.example/', 2)
            if kind == 'error':
                text = text.replace('onProgressChange progress: 25', 'onErrorReceive url: '+URL)
            if kind == 'foreign_pid':
                text = text.replace(' 42 43 ', ' 99 43 ')
            if kind == 'missing_title':
                text = text.replace('onTitleReceive title:', 'ignoredTitle:')
            obs['after']['raw_logs'] = text
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                verify(obs)

    def test_changed_process_clock_order_or_bad_initial_load_cannot_pass(self):
        for kind in ('pid', 'ticks', 'clock', 'setup'):
            obs = self.observation()
            if kind == 'pid':
                obs['after']['pid'] = 43
            if kind == 'ticks':
                obs['stat_after'] = obs['stat_after'].replace('999', '1000')
            if kind == 'clock':
                obs['after']['started_monotonic'] = 3
            if kind == 'setup':
                obs['before']['raw_logs'] = ''
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                verify(obs)

    def test_duplicate_or_reordered_native_lines_are_not_deduplicated_into_success(self):
        for duplicate in (True, False):
            obs = self.observation()
            lines = obs['after']['raw_logs'].splitlines()
            if duplicate:
                lines.append(lines[-1])
            else:
                lines[-1], lines[-2] = lines[-2], lines[-1]
            obs['after']['raw_logs'] = '\n'.join(lines)
            with self.assertRaises(ValueError):
                verify(obs)
