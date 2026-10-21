import unittest
from weather_session_memory import MIB,growth_bounds,gate
class GrowthTest(unittest.TestCase):
    def test_uses_extremes_not_favorable_single_sample(self):
        self.assertEqual(growth_bounds([10,12,11],[18,20,19]),{'lower_bytes':6,'upper_bytes':10,'median_bytes':8})
    def test_zero_or_negative_fixed_growth_has_noise_floor(self):
        for fixed in (0,-MIB):
            r=gate({'lower_bytes':6*MIB},{'upper_bytes':fixed});self.assertTrue(r['passed']);self.assertEqual(r['noise_bounded_ratio'],6)
    def test_tiny_or_noisy_gaps_do_not_pass(self):
        for u,f in ((4*MIB,0),(6*MIB,3*MIB),(9*MIB,4*MIB)):
            self.assertFalse(gate({'lower_bytes':u},{'upper_bytes':f})['passed'])
    def test_missing_window_or_nonphysical_total_rejected(self):
        for before,after in (([1,2],[3,4,5]),([1,2,3],[0,2,3])):
            with self.assertRaises(ValueError):growth_bounds(before,after)

class FrozenContractTest(unittest.TestCase):
    def test_lowered_contract_is_rejected_even_with_matching_hash(self):
        import hashlib,json,tempfile
        from pathlib import Path
        from unittest.mock import patch
        import weather_session_memory as module
        root=Path(module.__file__).resolve().parents[1]
        contract=json.loads((root/'validation/weather-sessions-growth-v5-contract.json').read_text())
        contract['required_ratio_each_pair_and_median']=2.0
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory);(base/'validation').mkdir();p=base/'validation/weather-sessions-growth-v5-contract.json';p.write_text(json.dumps(contract))
            record={'measurement_revision':'growth-v5','contract_sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
            with patch.object(module,'__file__',str(base/'tools/weather_session_memory.py')):
                with self.assertRaisesRegex(ValueError,'frozen memory gate changed'):module.verify_capture(record,base)
