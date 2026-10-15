import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from export_agent_data import installable_reproduction
from hap_profile_validity import ExpiredProfileError


class ReproductionExportSelectionTest(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory();self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name);self.old=self.root/'measured.hap';self.unsigned=self.root/'unsigned.hap'
        self.old.write_bytes(b'historical measured package');self.unsigned.write_bytes(b'unchanged business code')
        self.folder=self.root/'artifacts/reproduction-signatures/case/unfixed';self.folder.mkdir(parents=True)
        self.new=self.folder/'app-export.hap';self.new.write_bytes(b'renewed signature package')
        self.digest=hashlib.sha256(self.new.read_bytes()).hexdigest()
        self.put('sign.json',{'status':'PASS','audit':{'passed':True,'sha256':self.digest},
            'unsigned_sha256':hashlib.sha256(self.unsigned.read_bytes()).hexdigest()})
        self.put('smoke.json',{'status':'PASS','signed_sha256':self.digest,'foreground_bundle':'app.bundle','pids':[42]})

    def put(self,name,data):(self.folder/name).write_text(json.dumps(data))

    def check(self):
        with patch('export_agent_data.ROOT',self.root),patch('export_agent_data.verify_installable_profile',side_effect=ExpiredProfileError('expired')):
            return installable_reproduction('case',self.old,self.unsigned,'app.bundle')

    def test_still_valid_historical_signature_is_used_without_any_replacement(self):
        with patch('export_agent_data.ROOT',self.root),patch('export_agent_data.verify_installable_profile'),\
                patch('export_agent_data.verify_identity') as identity:
            self.assertEqual(installable_reproduction('case',self.old,self.unsigned,'app.bundle'),self.old)
            identity.assert_not_called()

    def test_renewed_package_requires_recomputed_identity_and_keeps_historical_bytes(self):
        before={p:p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        with patch('export_agent_data.verify_identity',return_value={'renewed_signed_sha256':self.digest}) as identity:
            self.assertEqual(self.check(),self.new)
        self.assertEqual(identity.call_args.args[:4],(self.unsigned,self.old,self.new,'app.bundle'))
        self.assertEqual(before,{p:p.read_bytes() for p in self.root.rglob('*') if p.is_file()})

    def test_no_launch_receipt_means_no_export_even_if_the_renewed_file_exists(self):
        (self.folder/'smoke.json').unlink()
        with self.assertRaisesRegex(ValueError,'fresh launch'):self.check()

    def test_foreign_bundle_stale_launch_or_modified_build_is_rejected(self):
        for field,value in [('foreground_bundle','other.bundle'),('signed_sha256','another-package'),('pids',[])]:
            self.put('smoke.json',{'status':'PASS','signed_sha256':self.digest,'foreground_bundle':'app.bundle','pids':[42],field:value})
            with self.subTest(field=field),self.assertRaises(ValueError):self.check()
        self.put('smoke.json',{'status':'PASS','signed_sha256':self.digest,'foreground_bundle':'app.bundle','pids':[42]})
        self.unsigned.write_bytes(b'different business build')
        with self.assertRaises(ValueError):self.check()

    def test_same_signature_flags_cannot_hide_a_business_or_permission_change(self):
        with patch('export_agent_data.verify_identity',side_effect=ValueError('changed business identity')):
            with self.assertRaisesRegex(ValueError,'changed business'):self.check()
