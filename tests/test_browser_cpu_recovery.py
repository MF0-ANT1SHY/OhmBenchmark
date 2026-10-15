import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from recover_browser_cpu_capture import recover, CASE


class BrowserCPURecoveryTest(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory();self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name);self.remote_root=self.root/'native';self.remote_root.mkdir()
        self.folder=self.root/'artifacts/clean'/CASE/'unfixed/cpu-captures/round-1';self.folder.mkdir(parents=True)
        case=self.root/'cases'/CASE;case.mkdir(parents=True);(case/'workload.json').write_text('{}')
        self.put(case/'case.json',{'testcase':{'workload':'workload.json'},'host_app':{'bundle_name':'com.example.nanvision'}})
        self.fixture=self.root/'input.db';self.fixture.write_bytes(b'ordinary empty database')
        digest=hashlib.sha256(self.fixture.read_bytes()).hexdigest()
        self.put(self.folder.parents[1]/'sign.json',{'audit':{'sha256':'signed'},'signed_hap':'/private/signed.hap'})
        self.put(self.folder.parents[1]/'workload.json',{'status':'PASS','plan_sha256':hashlib.sha256(b'{}').hexdigest(),
            'signed_sha256':'signed','fixture':{'sha256':digest}})
        stat='42 (app) '+' '.join(['0']*19+['100'])
        self.put(self.folder/'transport-owner.json',{'remote_python_pid':42,'remote_python_stat':stat,
            'app':{'pid':42,'stat':stat,'cmdline':'com.example.nanvision\0'}})
        def state(rows,start,end):
            return {'raw_tables':'[{"name":"history_2026_10_15"}]','raw_rows':json.dumps(rows),
                    'started_monotonic':start,'ended_monotonic':end}
        rows=[{'history_table':'history_2026_10_15','id':i,'url':'https://example.com/',
               'title':'Example Domain','timestamp':'2026_10_15 09:30'} for i in range(1,16)]
        from browser_visit_progress import verify_progress
        before,after=state([],1,2),state(rows,4,5)
        self.put(self.remote_root/'capture.json',{'status':'CAPTURED','event':'hw-instructions','pids':[42],'action_start_monotonic':3,
            'action_end_monotonic':6,'browser_visits':{'before':before,'after':after,'progress':verify_progress(before,after)}})
        self.put(self.remote_root/'report.json',{'processNameMap':{'42':'com.example.nanvision'},
            'recordSampleInfo':[{'eventConfigName':'hw-instructions','processes':[
                {'pid':42,'eventCount':200,'threads':[{'sampleCount':5}]}]}]})
        (self.remote_root/'perf.data').write_bytes(b'original native raw capture')
        outer=self
        class Remote:
            def python(self,code,data,timeout):
                if 'ui.run' in code:raise AssertionError('recovery must not execute UI')
                return json.dumps({name:hashlib.sha256((outer.remote_root/name).read_bytes()).hexdigest()
                                   for name in ('capture.json','report.json','perf.data')})
            def download(self,remote,local):shutil.copyfile(outer.remote_root/Path(remote).name,local)
        self.remote=Remote()

    def put(self,path,data):path.write_text(json.dumps(data))

    def check(self):
        with patch('recover_browser_cpu_capture.ROOT',self.root):return recover(self.remote,'unfixed',1,self.fixture)

    def test_completed_original_trial_recovered_without_ui_or_raw_data_mutation(self):
        before={p:p.read_bytes() for p in self.remote_root.iterdir()}
        result=self.check()
        self.assertEqual(result['app_instruction_period_sum'],200)
        self.assertFalse(result['transport_recovery']['ui_rerun'])
        self.assertEqual(before,{p:p.read_bytes() for p in self.remote_root.iterdir()})
        with self.assertRaisesRegex(ValueError,'replace'):self.check()

    def test_live_original_remote_job_is_not_restarted_or_finalized(self):
        with patch.object(self.remote,'python',side_effect=RuntimeError('original remote capture job is still live')):
            with self.assertRaisesRegex(RuntimeError,'still live'):self.check()
        self.assertFalse((self.folder/'capture.json').exists())

    def test_foreign_app_or_local_raw_mismatch_is_rejected_without_overwriting(self):
        raw=self.folder/'raw-device-capture.json';raw.write_bytes(b'preexisting different raw evidence')
        with self.assertRaisesRegex(ValueError,'preserve/archive'):self.check()
        self.assertEqual(raw.read_bytes(),b'preexisting different raw evidence')
        raw.unlink()
        p=self.remote_root/'report.json';data=json.loads(p.read_text());data['processNameMap']['42']='other.bundle';self.put(p,data)
        with self.assertRaisesRegex(ValueError,'observed app'):self.check()
        self.assertFalse((self.folder/'capture.json').exists())

    def test_changed_input_cannot_be_attached_to_original_trial(self):
        self.fixture.write_bytes(b'different input')
        with self.assertRaisesRegex(ValueError,'matching validated'):self.check()
        self.assertFalse((self.folder/'capture.json').exists())

    def test_failed_native_job_is_not_promoted_to_captured(self):
        p=self.remote_root/'capture.json';data=json.loads(p.read_text());data['status']='FAIL';self.put(p,data)
        with self.assertRaisesRegex(ValueError,'did not complete'):self.check()
        self.assertFalse((self.folder/'capture.json').exists())
