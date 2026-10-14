import json,sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import test_pss_evidence as fixtures
from accept_pss_evidence import accept
from capture_wan_cold_cache_pss import capture
class ColdCacheSupplementTest(unittest.TestCase):
    def test_supplement_cannot_be_reused_as_full_case_pss(self):
        source=fixtures.PSSEvidenceTest();source.setUp();self.addCleanup(source.doCleanups)
        p=source.root/'artifacts/clean'/source.cid/'unfixed/pss-captures/round-1/capture.json'
        r=json.loads(p.read_text());r['status']='SUPPLEMENT_CAPTURED';r['supplementary_only']=True;p.write_text(json.dumps(r))
        with patch('accept_pss_evidence.ROOT',source.root),self.assertRaisesRegex(ValueError,'provenance'):accept(source.cid,write=False)
    def test_unknown_variant_or_round_rejected_before_any_remote_operation(self):
        for variant,round_no in [('other',1),('unfixed',0),('fixed',4)]:
            with self.subTest(variant=variant,round=round_no),self.assertRaises(ValueError):capture(None,variant,round_no,Path('/unused'))
