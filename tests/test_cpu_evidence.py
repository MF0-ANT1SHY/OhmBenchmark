import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from accept_cpu_evidence import accept


class CPUEvidenceTests(unittest.TestCase):
    cid = 'browser_history_delete_no_transaction'

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.case_dir = self.root/'cases'/self.cid
        self.case_dir.mkdir(parents=True)
        (self.case_dir/'workload.json').write_text('{}')
        self.plan_hash = hashlib.sha256(b'{}').hexdigest()
        self.put(self.case_dir/'case.json', {'id':self.cid,'host_app':{'bundle_name':'app.bundle'},
            'testcase':{'workload':'workload.json'},'test_oracle':{'metric':'hiperf_instructions','evidence':{}}})
        for variant,value in [('unfixed',200),('fixed',100)]:
            folder=self.root/'artifacts/clean'/self.cid/variant
            self.put(folder/'sign.json', {'audit':{'sha256':'package'}})
            self.put(folder/'workload.json', {'status':'PASS','plan_sha256':self.plan_hash,'signed_sha256':'package','fixture':{'sha256':'fixture'},
                'functional_check':'all history rows and dates cleared through the production UI','cleared_tables':61})
            for number in range(1,4):
                capture=folder/'cpu-captures'/f'round-{number}'
                self.put(capture/'capture.json', {'status':'CAPTURED','plan_sha256':self.plan_hash,
                    'signed_sha256':'package','fixture_sha256':'fixture','pids':[10],
                    'app_instruction_period_sum':value,'completion_check':'database cleared before capture stop',
                    'action_start_monotonic':100,'action_end_monotonic':101,'remote_artifacts':'private-path'})
                self.put(capture/'report.json', {'processNameMap':{'10':'app.bundle','20':'observer'},
                    'recordSampleInfo':[{'eventConfigName':'hw-instructions','eventCount':999999,
                        'processes':[{'pid':10,'eventCount':value,'threads':[{'sampleCount':5}]},
                                     {'pid':20,'eventCount':999999-value,'threads':[{'sampleCount':999}]}]}]})

    def put(self,path,data):
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(data))

    def change_capture(self,key,value):
        path=self.root/'artifacts/clean'/self.cid/'unfixed/cpu-captures/round-1/capture.json'
        data=json.loads(path.read_text())
        data[key]=value
        self.put(path,data)

    def check(self):
        with patch('accept_cpu_evidence.ROOT', self.root):
            return accept(self.cid,write=False)

    def test_raw_app_attribution_not_system_total_and_readonly(self):
        before={p:p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        results=self.check()
        self.assertEqual(results['unfixed']['samples'], [200]*3)
        self.assertEqual(results['fixed']['samples'], [100]*3)
        self.assertEqual(results['unfixed']['median_ratio'], 2)
        self.assertEqual(before,{p:p.read_bytes() for p in self.root.rglob('*') if p.is_file()})

    def test_missing_async_completion_rejected(self):
        self.change_capture('completion_check',None)
        with self.assertRaisesRegex(RuntimeError,'completion'):
            self.check()

    def test_fixture_different_from_ui_validation_rejected(self):
        self.change_capture('fixture_sha256','different')
        with self.assertRaisesRegex(RuntimeError,'fixture differs'):
            self.check()

    def test_claimed_count_different_from_raw_report_rejected(self):
        self.change_capture('app_instruction_period_sum',999999)
        with self.assertRaisesRegex(RuntimeError,'attribution'):
            self.check()

    def test_valid_but_insufficient_improvement_is_recorded_as_failure(self):
        folder=self.root/'artifacts/clean'/self.cid/'unfixed'
        for n in range(1,4):
            path=folder/'cpu-captures'/f'round-{n}'/'capture.json'
            capture=json.loads(path.read_text());capture['app_instruction_period_sum']=110
            self.put(path,capture)
            path=path.with_name('report.json');report=json.loads(path.read_text())
            report['recordSampleInfo'][0]['processes'][0]['eventCount']=110
            self.put(path,report)
        with patch('accept_cpu_evidence.ROOT',self.root):
            with self.assertRaisesRegex(RuntimeError,'criterion not met'):
                accept(self.cid)
        case=json.loads((self.case_dir/'case.json').read_text())
        self.assertEqual(case['test_oracle']['evidence']['status'],'measured_clean_failed')
        result=json.loads((folder/'performance.json').read_text())
        self.assertEqual(result['status'],'FAIL')
        self.assertEqual(result['samples'],[110]*3)


if __name__ == '__main__':
    unittest.main()
