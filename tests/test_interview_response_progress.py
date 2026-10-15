import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from interview_response_progress import BUNDLE, URL, records, verify_observation, verify_capture


def state(logs, start, end):
    stat = '42 (interview) ' + ' '.join(['0']*19 + ['123'])
    return dict(pid=42, raw_stat=stat, raw_stat_after=stat, raw_cmdline=BUNDLE+'\0',
                raw_logs=logs, started_monotonic=start, ended_monotonic=end)


class InterviewResponseProgressTest(unittest.TestCase):
    def observation(self, fixed=False):
        payload = 'code=10000 message=success' if fixed else '{"code":10000,"message":"success","data":{}}'
        lines = [f'179203237{i}.123456789 42 42 I A0FF09/{BUNDLE}/PASS_INTERVIEW_LOGGER: {URL}questionBankType=10&type=401&page=1&sort=0&keyword=, {payload}'
                 for i in range(6)]
        return dict(before=state(lines[0], 1, 2), after=state('\n'.join(lines), 4, 5))

    def test_both_production_formats_and_nanosecond_precision(self):
        for fixed in (False, True):
            obs = self.observation(fixed)
            obs['progress'] = verify_observation(obs)
            self.assertEqual(verify_capture(obs, 3, 6, [42])['successful_question_lists'], 5)
            self.assertEqual(records(obs['after'])[0][0], 1792032370123456789)

    def test_old_missing_extra_duplicate_failed_and_foreign_logs_rejected(self):
        for kind in ('old', 'missing', 'extra', 'duplicate', 'failed', 'foreign', 'clock'):
            obs = self.observation()
            lines = obs['after']['raw_logs'].splitlines()
            if kind == 'old': obs['before']['raw_logs'] = obs['after']['raw_logs']
            if kind == 'missing': lines.pop()
            if kind == 'extra': lines.append(lines[-1].replace('2375.', '2376.'))
            if kind == 'duplicate': lines[-1] = lines[-2]
            if kind == 'failed': lines[-1] = lines[-1].replace('10000', '401')
            if kind == 'foreign': lines[-1] = lines[-1].replace(' 42 42 I', ' 43 43 I')
            if kind == 'clock': lines[-2:] = reversed(lines[-2:])
            obs['after']['raw_logs'] = '\n'.join(lines)
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                verify_observation(obs)

    def test_restarted_process_and_foreign_cmdline_rejected(self):
        for field, value in [('raw_stat_after', '42 (interview) '+' '.join(['0']*19+['124'])),
                             ('raw_cmdline', 'other.bundle\0')]:
            obs = self.observation()
            obs['after'][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError): verify_observation(obs)

    def test_pagination_other_categories_and_other_loggers_are_not_refreshes(self):
        for old, new in [('page=1', 'page=2'), ('type=401', 'type=402'),
                         ('PASS_INTERVIEW_LOGGER', 'other_logger')]:
            obs = self.observation()
            obs['after']['raw_logs'] = obs['after']['raw_logs'].replace(old, new)
            with self.subTest(new=new), self.assertRaises(ValueError): verify_observation(obs)

    def test_capture_must_include_completions_and_summary_must_match(self):
        obs = self.observation()
        obs['progress'] = verify_observation(obs)
        with self.assertRaises(ValueError): verify_capture(obs, 3, 4.5, [42])
        with self.assertRaises(ValueError): verify_capture(obs, 3, 6, [43])
        forged = copy.deepcopy(obs)
        forged['progress']['successful_question_lists'] = 6
        with self.assertRaises(ValueError): verify_capture(forged, 3, 6, [42])
