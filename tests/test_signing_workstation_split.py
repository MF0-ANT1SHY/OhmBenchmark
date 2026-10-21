import hashlib
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from sign_clean_cases import sign_case


class SigningWorkstationSplitTest(unittest.TestCase):
    def test_unverified_cached_binding_cannot_override_requested_device(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);folder=root/'case'/'fixed';folder.mkdir(parents=True)
            case={'id':'case','host_app':{'bundle_name':'app'}}
            (folder/'build.json').write_text(json.dumps({'status':'PASS','source':{'passed':True},'hap':{'passed':True,'sha256':'unsigned'}}))
            with zipfile.ZipFile(folder/'app-unsigned.hap','w') as package:
                package.writestr('module.json',json.dumps({'module':{}}))
            sign={'status':'PASS','unsigned_sha256':'unsigned','allowed_acls':[],
                  'signed_hap':'/work/case/fixed/app.hap','audit':{'sha256':'signed'}}
            path=folder/'sign.json';path.write_text(json.dumps(sign));remote=Mock()
            with self.assertRaisesRegex(ValueError,'device binding'):
                sign_case(remote,case,'fixed',root,'/work',device_udid='A'*64)
            remote.python.assert_not_called()
            sign['device_binding_sha256']=hashlib.sha256(('A'*64).encode()).hexdigest()
            path.write_text(json.dumps(sign))
            sign_case(remote,case,'fixed',root,'/work',device_udid='A'*64)
            remote.python.assert_called_once()

    def test_invalid_device_identity_is_rejected_before_workstation_access(self):
        for value in ('invalid',123,'A'*63,'a'*64):
            with self.subTest(value=value),self.assertRaises(ValueError):
                sign_case(Mock(),{},'fixed',Path('/unused'),device_udid=value)
