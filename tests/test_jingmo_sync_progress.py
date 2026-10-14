import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from jingmo_sync_progress import verify_observation, verify_capture, complete_sync, read_state, records


class SyncCompletionTest(unittest.TestCase):
    def observation(self, skipped=False):
        lines = []
        for n in range(3):
            lines.append(f'{100+n*2}.000 42 42 I A0FF00/com.hefengbao.jingmo.hw/JINGMO@SyncData: classic poem dataset size: 1332826')
            message = ('JINGMO@DatasetViewModel: dataset already imported (5000 rows), skip import'
                       if skipped else 'JINGMO@ClassicPoemDao: Batch insert is successful, rowCount = 5000')
            lines.append(f'{101+n*2}.000 42 42 I A0FF00/com.hefengbao.jingmo.hw/{message}')
        return {'before': {'pid': 42, 'raw_logs': '', 'started_monotonic': 1, 'ended_monotonic': 2},
                'after': {'pid': 42, 'raw_logs': '\n'.join(lines), 'started_monotonic': 10, 'ended_monotonic': 11},
                'expected_cycles': 3}

    def test_all_three_normal_cycles_must_complete(self):
        for skipped in (False, True):
            with self.subTest(skipped=skipped):
                obs = self.observation(skipped)
                obs['progress'] = verify_observation(obs)
                self.assertEqual(verify_capture(obs, 3, 12)['completed_cycles'], 3)

    def test_missing_completion_is_not_same_row_count_proof(self):
        obs = self.observation()
        obs['after']['raw_logs'] = '\n'.join(obs['after']['raw_logs'].splitlines()[:-1])
        with self.assertRaises(ValueError):
            verify_observation(obs)

    def test_old_logs_cannot_be_reused(self):
        obs = self.observation()
        obs['before']['raw_logs'] = obs['after']['raw_logs']
        with self.assertRaises(ValueError):
            verify_observation(obs)

    def test_different_process_and_duplicate_records_rejected(self):
        for change in ('pid', 'duplicate'):
            obs = self.observation()
            if change == 'pid':
                obs['after']['pid'] = 43
            else:
                obs['after']['raw_logs'] += '\n' + obs['after']['raw_logs'].splitlines()[-1]
            with self.assertRaises(ValueError):
                verify_observation(obs)

    def test_completion_after_profile_stop_rejected(self):
        obs = self.observation()
        obs['progress'] = verify_observation(obs)
        with self.assertRaises(ValueError):
            verify_capture(obs, 3, 10.5)

    def test_failed_completion_preserves_raw_log_evidence(self):
        obs = self.observation(True)
        raw = obs['after']['raw_logs'].replace('105.000', '103.500')
        class UI:
            def shell(self, command):
                return '42' if command.startswith('pidof ') else raw
        with self.assertRaisesRegex(ValueError, 'out of order') as failure:
            complete_sync(UI(), obs['before'], timeout=0)
        self.assertEqual(failure.exception.observation['after']['raw_logs'], raw)
        self.assertEqual(failure.exception.observation['before'], obs['before'])

    def test_log_read_uses_one_clock_and_preserves_epoch_nanoseconds(self):
        calls=[]
        def shell(command):
            calls.append(command)
            if command.startswith('pidof '):return '42'
            return '1791940000.123456789 42 42 I A0FF00/JINGMO@SyncData: classic poem dataset size: 1332826\n'
        state=read_state(shell)
        self.assertIn('-v epoch -v nsec',calls[-1])
        self.assertNotIn('-v monotonic',calls[-1])
        self.assertEqual(records(state)[0][0],1791940000123456789)


if __name__ == '__main__':
    unittest.main()
