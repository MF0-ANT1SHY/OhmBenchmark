import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
import accept_wan_home_memory as gate
from accept_pss_evidence import accept as accept_pss


class WanMemoryAcceptanceTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        (self.root/'old.json').write_text('{"original_verdict":"negative"}')
        self.case = self.root/'cases'/gate.CASE/'case.json'
        self.case.parent.mkdir(parents=True)
        self.record = {
            'acceptance_revision': {'id': 'native-memory-and-cache-v2',
                'previous_case': 'old.json',
                'previous_case_sha256': hashlib.sha256((self.root/'old.json').read_bytes()).hexdigest()},
            'test_oracle': {'mechanism_oracle': {'metric': 'native_home_cache_contents'}}}
        self.case.write_text(json.dumps(self.record))

    def test_one_weak_pair_cannot_be_hidden_by_strong_median(self):
        proof = {'primary_criterion_met': True, 'paired_ratios': [1.7, 1.29, 1.8], 'median_ratio': 1.7}
        with patch.object(gate, 'ROOT', self.root), patch.object(gate, 'audit', return_value=proof):
            with self.assertRaisesRegex(ValueError, '1.3x'):
                gate.accept(write=False)

    def test_changed_historical_contract_is_rejected_before_raw_audit(self):
        (self.root/'old.json').write_text('{}')
        with patch.object(gate, 'ROOT', self.root), patch.object(gate, 'audit') as audit:
            with self.assertRaisesRegex(ValueError, 'remain intact'):
                gate.accept(write=False)
            audit.assert_not_called()

    def test_unrevised_oracle_is_not_accepted(self):
        self.record['acceptance_revision']['id'] = 'original'
        self.case.write_text(json.dumps(self.record))
        with patch.object(gate, 'ROOT', self.root):
            with self.assertRaisesRegex(ValueError, 'explicit revised'):
                gate.accept(write=False)

    def test_partial_negative_screen_cannot_accept_revised_case(self):
        with self.assertRaisesRegex(ValueError, 'all three'):
            accept_pss(gate.CASE, write=False, require_pass=False, negative_screen=True)
