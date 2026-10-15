import copy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from reproduction_hap_identity import verify_business_entries,verify_identity


class ReproductionHAPIdentityTest(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory();self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name)
        self.unsigned=self.root/'unsigned.hap';self.old=self.root/'old.hap';self.new=self.root/'new.hap'
        self.business={'ets/modules.abc':b'business code','module.json':b'unchanged permissions'}
        self.signed={**self.business,'.pages.info':b'original SDK page metadata'}
        self.write(self.unsigned,self.business);self.write(self.old,self.signed);self.write(self.new,self.signed)
        self.profile={'bundle-info':{'bundle-name':'app.bundle','development-certificate':'same certificate'},
                      'permissions':[],'validity':{'not-before':1,'not-after':100}}

    def write(self,path,entries):
        with zipfile.ZipFile(path,'w') as package:
            for name,data in entries.items():package.writestr(name,data)

    def check(self,old,new,chains=(b'certificate-chain',b'certificate-chain')):
        with patch('reproduction_hap_identity.read_signed_profile',side_effect=[(old,chains[0]),(new,chains[1])]):
            return verify_identity(self.unsigned,self.old,self.new,'app.bundle',self.root/'sign.jar',150)

    def test_exact_business_and_security_identity_allows_only_dates_and_keeps_launch_pending(self):
        new=copy.deepcopy(self.profile);new['validity']={'not-before':100,'not-after':200}
        before={p:p.read_bytes() for p in (self.unsigned,self.old,self.new)}
        result=self.check(self.profile,new)
        self.assertEqual(result['business_entries'],2)
        self.assertFalse(result['fresh_launch_verified'])
        self.assertFalse(result['historical_performance_evidence_changed'])
        self.assertEqual(before,{p:p.read_bytes() for p in before})

    def test_business_code_resources_and_signing_metadata_cannot_change(self):
        for name in self.signed:
            changed={**self.signed,name:b'changed'};self.write(self.new,changed)
            with self.subTest(name=name),self.assertRaises(ValueError):verify_business_entries(self.unsigned,self.old,self.new)

    def test_unexpected_extra_entry_is_rejected_even_if_added_to_both_signed_packages(self):
        changed={**self.signed,'hidden-probe.so':b'not permitted'}
        self.write(self.old,changed);self.write(self.new,changed)
        with self.assertRaisesRegex(ValueError,'unexpected'):verify_business_entries(self.unsigned,self.old,self.new)

    def test_new_permissions_or_certificate_cannot_reuse_old_performance_identity(self):
        new=copy.deepcopy(self.profile);new['validity']={'not-before':100,'not-after':200}
        changed=copy.deepcopy(new);changed['permissions']=['new-permission']
        with self.assertRaisesRegex(ValueError,'permissions'):self.check(self.profile,changed)
        with self.assertRaisesRegex(ValueError,'identity'):self.check(self.profile,new,(b'old',b'new'))

    def test_expired_new_signature_is_rejected_despite_business_identity(self):
        with self.assertRaisesRegex(ValueError,'expired'):self.check(self.profile,self.profile)
