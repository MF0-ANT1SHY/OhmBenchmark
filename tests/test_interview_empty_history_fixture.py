import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from interview_empty_history_fixture import verify,prepare,IDENTITY,CASE
from interview_history_progress import empty_preferences,PREFERENCES,verify_capture,verify_observation,BUNDLE
from ui_driver import UI

class EmptyHistoryFixtureTest(unittest.TestCase):
    def test_preserved_native_version_and_tamper_rejection(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);before=b'<preferences version="1.0"><string key="old">old</string></preferences>';blob=empty_preferences(before)
            (root/'before.xml').write_bytes(before);(root/'deployed.xml').write_bytes(blob)
            p={'installation_verified':True,'case':CASE,'variant':'unfixed','preferences':PREFERENCES,'preparation_dir':str(root),'sha256':IDENTITY,'before_sha256':hashlib.sha256(before).hexdigest(),'deployed_sha256':hashlib.sha256(blob).hexdigest()}
            self.assertEqual(verify(p),IDENTITY)
            (root/'deployed.xml').write_bytes(before);p['deployed_sha256']=hashlib.sha256(before).hexdigest()
            with self.assertRaises(ValueError):verify(p)
    def test_wrong_case_cannot_touch_device(self):
        with self.assertRaises(ValueError):prepare(None,{'id':'other','host_app':{'bundle_name':BUNDLE}},'unfixed')
    def test_in_window_real_twenty_keyword_state_is_required(self):
        values=['question'+str(i) for i in range(20)];stat='20 (app) S '+' '.join(['0']*18+['123']+['0']*10)
        def state(xml,start):return {'pid':20,'raw_stat':stat,'raw_stat_after':stat,'raw_cmdline':BUNDLE,'raw_preferences':xml,'started_monotonic':start,'ended_monotonic':start+.1}
        before=state('<preferences version="1.0" />',1);after=state('<preferences version="1.0">'+''.join('<string key="'+v+'">'+v+'</string>' for v in values)+'</preferences>',3)
        observation={'before':before,'after':after,'values':values,'progress':verify_observation(before,after,values)}
        self.assertEqual(verify_capture(observation,2,4,[20])['persisted_keywords'],20)
        for start,end,pids in [(2,3,[20]),(1,4,[20]),(2,4,[21])]:
            with self.assertRaises(ValueError):verify_capture(observation,start,end,pids)
    def test_optional_login_branch_does_not_hide_transport_errors(self):
        ui=UI(lambda command:'');calls=[]
        def missing(selector,timeout=15):raise RuntimeError('UI target not found: optional')
        ui.find=missing;ui.run([{'op':'if_present','selector':{},'actions':[{'op':'unknown'}]}])
        def broken(selector,timeout=15):raise RuntimeError('device disconnected')
        ui.find=broken
        with self.assertRaisesRegex(RuntimeError,'disconnected'):ui.run([{'op':'if_present','selector':{},'actions':[]}])
