from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from screen_wan_home_write_mechanism import upper_bound


class NativeWriteBoundTest(unittest.TestCase):
    def test_complete_unfixed_and_fixed_prefix_can_prove_impossibility(self):
        r=upper_bound(1212155,611898,10,1)
        self.assertTrue(r['necessary_criterion_failed'])
        self.assertLess(r['maximum_possible_unfixed_to_fixed_ratio'],3)
        self.assertEqual(r['remaining_fixed_bytes_lower_bound'],0)

    def test_missing_work_nonpositive_prefix_and_exact_threshold_cannot_reject(self):
        for args in ((1200,600,9,1),(1200,600,10,0),(1200,0,10,1),(1200,400,10,1),(1200,100,10,1)):
            with self.subTest(args=args),self.assertRaises(ValueError):upper_bound(*args)
