import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from accept_pss_evidence import accept
from seed_search_history import seed


class PSSEvidenceTest(unittest.TestCase):
    cid='interviewapp_search_history_unbounded'

    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name)
        self.fixture=self.root/'fixture';self.fixture_receipt=seed(self.fixture,60)
        self.case=self.root/'cases'/self.cid;self.case.mkdir(parents=True)
        (self.case/'workload.json').write_text('{}')
        self.plan_hash=hashlib.sha256(b'{}').hexdigest()
        self.put(self.case/'case.json',{'id':self.cid,'host_app':{'bundle_name':'app.bundle'},
            'testcase':{'workload':'workload.json'},'test_oracle':{'metric':'app_pss_bytes','evidence':{}}})
        for variant,kb in [('unfixed',200),('fixed',100)]:
            folder=self.root/'artifacts/clean'/self.cid/variant
            self.put(folder/'sign.json',{'status':'PASS','audit':{'sha256':'package'}})
            identity=self.fixture_receipt['fixture_sha256']
            self.put(folder/'workload.json',{'status':'PASS','signed_sha256':'package','plan_sha256':self.plan_hash,
                                             'fixture':{'sha256':identity,'functional_read_verified':True}})
            for n in range(1,4):
                stat='123 (app name) '+' '.join(['S']+['0']*18+['100']+['0']*4)
                snapshots=[]
                for phase,stamp,value in [('before',99,300),('workload',110,400),('after',125,kb)]:
                    snapshots.append({'phase':phase,'monotonic':stamp,'read_start_monotonic':stamp-1,
                        'pid':123,'bundle':'app.bundle','process_start_ticks':100,
                        'raw_stat_before':stat,'raw_stat_after':stat,
                        'raw_cmdline_before':'app.bundle\x00','raw_cmdline_after':'app.bundle\x00',
                        'raw_smaps_rollup':f'Pss: {value} kB\n','pss_bytes':value*1024})
                self.put(folder/f'pss-captures/round-{n}/capture.json',{'status':'CAPTURED','case':self.cid,
                    'variant':variant,'round':n,'metric':'app_pss_bytes','signed_sha256':'package',
                    'plan_sha256':self.plan_hash,'fixture_sha256':identity,'input_preparation_verified':True,
                    'preparation':{'installation_verified':True,'sha256':identity,'variant':variant,
                        'fixture_dir':str(self.fixture),'deployed_sha256':self.fixture_receipt['variants'][variant]['sha256']},
                    'action_start_monotonic':100,'action_end_monotonic':120,'snapshots':snapshots,'app_pss_bytes':kb*1024})

    def put(self,path,data):
        path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(data))

    def test_readonly_acceptance_uses_final_absolute_pss(self):
        before={p:p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        with patch('accept_pss_evidence.ROOT',self.root):r=accept(self.cid,write=False)
        self.assertEqual(r['unfixed']['samples'],[200*1024]*3)
        self.assertEqual(r['fixed']['samples'],[100*1024]*3)
        self.assertEqual(r['unfixed']['median_ratio'],2)
        self.assertEqual(before,{p:p.read_bytes() for p in self.root.rglob('*') if p.is_file()})

    def test_raised_contract_cannot_accept_an_old_threshold_only_result(self):
        for number in (1,2,3):
            path=self.root/'artifacts/clean'/self.cid/'unfixed'/f'pss-captures/round-{number}/capture.json'
            record=json.loads(path.read_text())
            record['app_pss_bytes']=125*1024
            record['snapshots'][-1].update(pss_bytes=125*1024,raw_smaps_rollup='Pss: 125 kB\n')
            self.put(path,record)
        path=self.case/'case.json';case=json.loads(path.read_text())
        case['test_oracle']['comparison']='unfixed >= 1.3 * fixed over >= 3 rounds per variant'
        self.put(path,case)
        with patch('accept_pss_evidence.ROOT',self.root):
            result=accept(self.cid,write=False,require_pass=False)
            self.assertEqual(result['unfixed']['status'],'FAIL')
            case['test_oracle']['comparison']='unfixed >= 1.2 * fixed over >= 3 rounds per variant'
            self.put(path,case)
            self.assertEqual(accept(self.cid,write=False)['unfixed']['status'],'PASS')

    def test_missing_fresh_reset_or_changed_raw_total_cannot_pass(self):
        path=self.root/'artifacts/clean'/self.cid/'unfixed/pss-captures/round-1/capture.json'
        original=json.loads(path.read_text())
        for kind in ['reset','raw']:
            record=json.loads(json.dumps(original))
            if kind=='reset':record['input_preparation_verified']=False
            else:record['snapshots'][-1]['raw_smaps_rollup']='Pss: 1 kB\n'
            self.put(path,record)
            with self.subTest(kind=kind),patch('accept_pss_evidence.ROOT',self.root),self.assertRaises(ValueError):
                accept(self.cid,write=False)

    def test_valid_below_threshold_trials_remain_failed(self):
        folder=self.root/'artifacts/clean'/self.cid/'unfixed'
        for n in range(1,4):
            path=folder/f'pss-captures/round-{n}/capture.json';record=json.loads(path.read_text())
            record['app_pss_bytes']=110*1024
            record['snapshots'][-1].update(pss_bytes=110*1024,raw_smaps_rollup='Pss: 110 kB\n')
            self.put(path,record)
        with patch('accept_pss_evidence.ROOT',self.root):
            with self.assertRaisesRegex(RuntimeError,'criterion not met'):accept(self.cid)
            audited=accept(self.cid,write=False,require_pass=False)
        self.assertEqual(audited['unfixed']['status'],'FAIL')
        self.assertEqual(json.loads((self.case/'case.json').read_text())['test_oracle']['evidence']['status'],
                         'measured_clean_failed')

    def test_negative_screen_cannot_accept_or_write_partial_positive_data(self):
        with patch('accept_pss_evidence.ROOT',self.root):
            for options in ({}, {'write':False}, {'require_pass':False}):
                with self.assertRaises(ValueError):
                    accept(self.cid,negative_screen=True,**options)
            with self.assertRaisesRegex(ValueError,'three complete pairs'):
                accept(self.cid,write=False,require_pass=False,negative_screen=True)

    def test_first_failed_pair_rejects_without_later_trials_or_file_changes(self):
        folder=self.root/'artifacts/clean'/self.cid
        for variant in ('unfixed','fixed'):
            for n in (2,3):
                (folder/variant/f'pss-captures/round-{n}/capture.json').unlink()
        path=folder/'unfixed/pss-captures/round-1/capture.json'
        record=json.loads(path.read_text());record['app_pss_bytes']=110*1024
        record['snapshots'][-1].update(pss_bytes=110*1024,raw_smaps_rollup='Pss: 110 kB\n')
        self.put(path,record)
        before={p:p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        with patch('accept_pss_evidence.ROOT',self.root):
            result=accept(self.cid,write=False,require_pass=False,negative_screen=True)
            with self.assertRaises(FileNotFoundError):accept(self.cid,write=False)
        self.assertEqual(result['unfixed']['status'],'FAIL')
        self.assertEqual(result['unfixed']['rounds'],1)
        self.assertEqual(before,{p:p.read_bytes() for p in self.root.rglob('*') if p.is_file()})


if __name__=='__main__':unittest.main()
