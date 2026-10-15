import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from hap_profile_validity import verify_profile


class HAPProfileValidityTest(unittest.TestCase):
    def setUp(self):
        self.profile = {'validity':{'not-before':100,'not-after':200},
                        'bundle-info':{'bundle-name':'app.bundle'}}

    def test_current_profile_is_valid_without_mutating_historical_evidence(self):
        original=copy.deepcopy(self.profile)
        result=verify_profile(self.profile,'app.bundle',150)
        self.assertEqual(result,{'bundle':'app.bundle','not_before':100,'not_after':200,'checked_at':150})
        self.assertEqual(self.profile,original)

    def test_expired_future_and_boundary_dates_are_rejected(self):
        for now in (99,200,201):
            with self.subTest(now=now),self.assertRaises(ValueError): verify_profile(self.profile,'app.bundle',now)
        self.assertEqual(verify_profile(self.profile,'app.bundle',100)['not_before'],100)

    def test_foreign_bundle_cannot_reuse_valid_dates(self):
        with self.assertRaisesRegex(ValueError,'different bundle'): verify_profile(self.profile,'other.bundle',150)

    def test_malformed_intervals_and_nonfinite_clock_cannot_pass(self):
        for validity in ({},{'not-before':200,'not-after':100},
                         {'not-before':100,'not-after':100},{'not-before':100,'not-after':'200'},
                         {'not-before':True,'not-after':200}):
            p=copy.deepcopy(self.profile);p['validity']=validity
            with self.subTest(validity=validity),self.assertRaises(ValueError): verify_profile(p,'app.bundle',150)
        for now in (float('nan'),float('inf')):
            with self.subTest(now=now),self.assertRaises(ValueError): verify_profile(self.profile,'app.bundle',now)
