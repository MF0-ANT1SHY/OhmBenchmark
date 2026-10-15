import copy,json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from capture_external_trace import capture,WAN_CASE
from accept_trace_evidence import verify_capture
import test_trace_evidence as trace_fixture
import test_wan_history_progress as progress_fixture

class WanTraceIntegrationTest(unittest.TestCase):
    def test_offline_capture_is_rejected_before_install_or_ui(self):
        class Remote:
            def __init__(self):self.calls=[]
            def hdc(self,args):
                self.calls.append(args)
                return '0' if args[-1].endswith('tracing_on') else ''
        remote=Remote();case={'id':WAN_CASE,'test_oracle':{'metric':'trace_cpu_ms'}}
        with self.assertRaisesRegex(ValueError,'networking'):capture(remote,case,'unfixed',1,Path('/unused'))
        self.assertTrue(all(c[0]=='shell' and (c[1].startswith('pidof ') or c[1].startswith('cat ') or c[1]=='ip route show') for c in remote.calls))
    def receipt(self):
        source=trace_fixture.NativeTraceEvidenceTest();source.setUp();self.addCleanup(source.doCleanups)
        r=copy.deepcopy(source.receipt);obs=progress_fixture.WanHistoryProgressTest().observation()
        for key in ('before','after'):
            obs[key]['pid']=100;obs[key]['start_ticks']=123
            obs[key]['raw_logs']=obs[key]['raw_logs'].replace('123 123 I','100 100 I')
        obs['after']['started_monotonic']=5;obs['after']['ended_monotonic']=6
        r['case']=WAN_CASE;r['wan_history']=obs;r.pop('reader_refresh')
        for key in ('process_before','process_after'):r[key]['command']='org.example.wan.ohos\x00'
        return r,source.trace
    def test_wan_trace_recomputes_only_native_app_cpu(self):
        r,trace=self.receipt();self.assertEqual(verify_capture(r,trace)['app_cpu_ms'],8)
    def test_wrong_callback_process_and_late_completion_rejected(self):
        for change in ('pid','clock_window','error'):
            r,trace=self.receipt()
            if change=='pid':
                for state in r['wan_history'].values():
                    if isinstance(state,dict):state['start_ticks']=124
            if change=='clock_window':r['wan_history']['after']['ended_monotonic']=8
            if change=='error':r['wan_history']['after']['raw_logs']+='\n15.000000000 100 100 E A00000/org.example.wan.ohos/WebPage: onErrorReceive url: https://example.com/0'
            with self.subTest(change=change),self.assertRaises(ValueError):verify_capture(r,trace)

    def test_native_callback_checkpoints_must_be_inside_the_profile_window(self):
        receipt,trace=self.receipt();observation=receipt['wan_history']
        template=observation['after'];observation['during']=[{**template,
            'started_monotonic':3.1+i*.3,'ended_monotonic':3.2+i*.3} for i in range(5)]
        self.assertEqual(verify_capture(receipt,trace)['app_cpu_ms'],8)
        observation['during'][0].update(started_monotonic=2.5,ended_monotonic=2.6)
        with self.assertRaisesRegex(ValueError,'inside the measured window'):verify_capture(receipt,trace)
