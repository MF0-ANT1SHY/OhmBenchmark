import json
import copy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import sdk_signing


class SDKSigningDeviceBindingTest(unittest.TestCase):
    def test_invalid_explicit_binding_fails_before_signing_or_device_queries(self):
        for value in ('','123','a'*64,'A'*63,42):
            with self.subTest(value=value),patch('sdk_signing.ks') as key,patch('sdk_signing.udid') as device:
                with self.assertRaises(ValueError):sdk_signing.sign('in','out','app.bundle',device_udid=value)
                key.assert_not_called();device.assert_not_called()

    def test_renewal_can_retain_verified_binding_without_any_live_device_access(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);(root/'app.pem').write_text('public certificate')
            (root/'UnsgnedDebugProfileTemplate.json').write_text(json.dumps({
                'bundle-info':{},'debug-info':{},'acls':{},'validity':{}}))
            inp=root/'unsigned.hap'
            with zipfile.ZipFile(inp,'w') as package:package.writestr('module.json',json.dumps({'module':{'requestPermissions':[]}}))
            with patch('sdk_signing.WORK',root),patch('sdk_signing.lib',return_value=root),\
                    patch('sdk_signing.ks',return_value=root/'key.p12'),patch('sdk_signing.leaf_pem',return_value='same public certificate'),\
                    patch('sdk_signing.run',return_value='OK'),patch('sdk_signing.udid',side_effect=AssertionError('live device must not be touched')):
                sdk_signing.sign(inp,root/'signed.hap','app.bundle',device_udid='A'*64)
            profile=json.loads((root/'app.bundle.profile.json').read_text())
            self.assertEqual(profile['debug-info']['device-ids'],['A'*64])
            self.assertEqual(profile['bundle-info']['development-certificate'],'same public certificate')

    def test_measured_profile_changes_only_validity_not_legacy_acl_or_other_fields(self):
        measured={'type':'debug','bundle-info':{'bundle-name':'app.bundle','development-certificate':'same public certificate'},
                  'debug-info':{'device-ids':['A'*64]},'acls':{'allowed-acls':['']},
                  'validity':{'not-before':1,'not-after':2},'original-extra-field':{'preserve':True}}
        original=copy.deepcopy(measured)
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);(root/'app.pem').write_text('public certificate');inp=root/'unsigned.hap'
            with zipfile.ZipFile(inp,'w') as package:package.writestr('module.json',json.dumps({'module':{'requestPermissions':[]}}))
            with patch('sdk_signing.WORK',root),patch('sdk_signing.lib',return_value=root),\
                    patch('sdk_signing.ks',return_value=root/'key.p12'),patch('sdk_signing.leaf_pem',return_value='same public certificate'),\
                    patch('sdk_signing.run',return_value='OK'),patch('sdk_signing.udid',side_effect=AssertionError('no live device access')):
                sdk_signing.sign(inp,root/'signed.hap','app.bundle',device_udid='A'*64,measured_profile=measured)
            profile=json.loads((root/'app.bundle.profile.json').read_text())
            self.assertNotEqual(profile['validity'],measured['validity'])
            self.assertEqual({k:v for k,v in profile.items() if k!='validity'},{k:v for k,v in measured.items() if k!='validity'})
            self.assertEqual(measured,original)

    def test_measured_profile_cannot_select_another_development_certificate(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);(root/'app.pem').write_text('public certificate')
            profile={'type':'debug','bundle-info':{'bundle-name':'app.bundle','development-certificate':'other certificate'},'debug-info':{'device-ids':['A'*64]}}
            with patch('sdk_signing.WORK',root),patch('sdk_signing.ks',return_value=root/'key.p12'),\
                    patch('sdk_signing.leaf_pem',return_value='same certificate'),patch('sdk_signing.run') as signer:
                with self.assertRaisesRegex(ValueError,'provisioning identity'):
                    sdk_signing.sign('unused','unused','app.bundle',device_udid='A'*64,measured_profile=profile)
                signer.assert_not_called()
