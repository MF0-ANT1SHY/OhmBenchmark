import hashlib
import json
from pathlib import Path
import sys
import tempfile
import shutil
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from prepare_reproduction_signature import prepare


class ReproductionPreparationTest(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory();self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name);case=self.root/'cases/case';case.mkdir(parents=True)
        self.case={'host_app':{'bundle_name':'app.bundle'},'test_oracle':{'evidence':{'status':'measured_clean'}}}
        (case/'case.json').write_text(json.dumps(self.case))
        self.base=self.root/'artifacts/clean/case/unfixed';self.base.mkdir(parents=True)
        (self.base/'app-unsigned.hap').write_bytes(b'business');(self.base/'app-export.hap').write_bytes(b'measured')
        unsigned=hashlib.sha256(b'business').hexdigest()
        self.put(self.base/'build.json',{'status':'PASS','hap':{'passed':True,'sha256':unsigned}})
        self.put(self.base/'sign.json',{'unsigned_sha256':unsigned,'audit':{'sha256':hashlib.sha256(b'measured').hexdigest()}})
        self.folder=self.root/'artifacts/reproduction-signatures/case/unfixed';self.folder.mkdir(parents=True)
        (self.folder/'app-export.hap').write_bytes(b'renewed')
        self.put(self.folder/'sign.json',{'status':'PASS','unsigned_sha256':unsigned,
            'audit':{'passed':True,'sha256':hashlib.sha256(b'renewed').hexdigest()}})
        self.put(self.folder/'identity.json',{})
        self.profile={'bundle-info':{'bundle-name':'app.bundle'},'validity':{'not-before':1,'not-after':2},
                      'debug-info':{'device-ids':['A'*64]}}

    def put(self,path,data):path.write_text(json.dumps(data))

    def check(self,variant='unfixed'):
        class NoTransport:
            def __getattr__(self,name):raise AssertionError('unexpected remote/device operation '+name)
        with patch('prepare_reproduction_signature.ROOT',self.root),\
                patch('prepare_reproduction_signature.require_accepted_case'),\
                patch('prepare_reproduction_signature.read_signed_profile',return_value=(self.profile,b'certificate')),\
                patch('prepare_reproduction_signature.verify_identity',return_value={'status':'LAUNCH_PENDING','fresh_launch_verified':False}):
            return prepare(NoTransport(),'case',variant)

    def test_existing_identity_is_rechecked_without_touching_device_or_originals(self):
        before={p:p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        result=self.check();self.assertTrue(result['existing_preparation_rechecked'])
        self.assertFalse(result['live_device_queries_performed']);self.assertFalse(result['fresh_launch_verified'])
        self.assertEqual(before,{p:p.read_bytes() for p in self.root.rglob('*') if p.is_file()})

    def test_modified_unsigned_build_or_stale_signature_metadata_cannot_be_prepared(self):
        (self.folder/'app-export.hap').write_bytes(b'changed-package')
        with self.assertRaisesRegex(ValueError,'signature metadata'):self.check()
        (self.base/'app-unsigned.hap').write_bytes(b'changed-build')
        with self.assertRaisesRegex(ValueError,'audited measured business build'):self.check()

    def test_negative_case_is_rejected_before_build_or_remote_access(self):
        self.case['test_oracle']['evidence']['status']='negative_screen_failed'
        self.put(self.root/'cases/case/case.json',self.case)
        with patch('prepare_reproduction_signature.ROOT',self.root),self.assertRaisesRegex(ValueError,'pending and negative'):
            prepare(None,'case')

    def test_fixed_reference_uses_its_own_historical_and_reproduction_artifacts(self):
        shutil.copytree(self.base,self.base.with_name('fixed'))
        shutil.copytree(self.folder,self.folder.with_name('fixed'))
        result=self.check('fixed')
        self.assertEqual(result['variant'],'fixed')
        with self.assertRaises(ValueError):prepare(None,'case','../another')
