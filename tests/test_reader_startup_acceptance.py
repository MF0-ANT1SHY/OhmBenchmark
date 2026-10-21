import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
import accept_reader_startup_evidence as target


class StartupAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name);self.cid = target.CASE
        self.addCleanup(patch.stopall);patch.object(target, 'ROOT', self.root).start()
        patch.object(target, 'verify_preparation').start();patch.object(target, 'same_instance').start()
        patch.object(target, 'verify_native_capture', side_effect=lambda r,p: (
            {'elapsed_upper_s': r['upper'], 'elapsed_lower_s': r['lower']},
            {'trace_sha256': 'trace', 'app_cpu_ms': 10})).start()
        case = self.root/'cases'/self.cid;case.mkdir(parents=True)
        (case/'workload.json').write_text('{}');digest = hashlib.sha256(b'{}').hexdigest()
        self.put(case/'case.json', {'measurement_revision': 'revision',
            'testcase': {'workload': 'workload.json'},
            'test_oracle': {'metric': target.METRIC, 'comparison': target.COMPARISON}})
        for variant in ('unfixed', 'fixed'):
            folder = self.root/'artifacts/clean'/self.cid/variant;folder.mkdir(parents=True)
            self.put(folder/'sign.json', {'audit': {'sha256': variant}})
            for number in (1, 2, 3):
                directory = folder/'trace-captures/revision'/f'round-{number}';directory.mkdir(parents=True)
                self.put(directory/'capture.json', {'case': self.cid, 'variant': variant, 'round': number,
                    'measurement_revision': 'revision', 'signed_sha256': variant, 'plan_sha256': digest,
                    'fixture_sha256': 'fixture', 'reader_fixture_before': {'sha256': 'fixture', 'service': {'network_delay_s': 1.5}},
                    'reader_fixture_after': {}, 'upper': 20 if variant=='unfixed' else 10,
                    'lower': 18 if variant=='unfixed' else 8, 'remote_artifacts': 'remote'})
            self.put(folder/'workload.json', {'status': 'PASS', 'plan_sha256': digest, 'signed_sha256': variant,
                'native_capture_sha256': hashlib.sha256((folder/'trace-captures/revision/round-1/capture.json').read_bytes()).hexdigest()})

    def put(self, path, value):
        path.write_text(json.dumps(value))

    def test_requires_all_three_pairs(self):
        p=self.root/'artifacts/clean'/self.cid/'fixed/trace-captures/revision/round-3/capture.json';p.unlink()
        with self.assertRaises(FileNotFoundError):target.accept(self.cid, write=False)

    def test_every_conservative_pair_must_pass(self):
        p=self.root/'artifacts/clean'/self.cid/'unfixed/trace-captures/revision/round-2/capture.json'
        r=json.loads(p.read_text());r['lower']=14.9;self.put(p,r)
        with self.assertRaisesRegex(ValueError, 'below 1.5x'):target.accept(self.cid, write=False)

    def test_nominal_speedup_does_not_replace_lower_bound(self):
        result=target.accept(self.cid, write=False)
        self.assertEqual(result['unfixed']['paired_ratios'], [1.8]*3)
        self.assertEqual(result['unfixed']['nominal_paired_ratios'], [2]*3)

    def test_signature_mismatch_rejected(self):
        p=self.root/'artifacts/clean'/self.cid/'fixed/trace-captures/revision/round-2/capture.json'
        r=json.loads(p.read_text());r['signed_sha256']='other';self.put(p,r)
        with self.assertRaisesRegex(ValueError, 'provenance'):target.accept(self.cid, write=False)
