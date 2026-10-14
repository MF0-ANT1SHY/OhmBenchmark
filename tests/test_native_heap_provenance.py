import copy,hashlib,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import test_native_heap_events as native_fixture
from native_heap_provenance import verify,verify_device_clock_span
class NativeHeapProvenanceTest(unittest.TestCase):
    def setUp(self):
        self.source=native_fixture.NativeHeapEventTest();self.source.setUp();self.addCleanup(self.source.doCleanups)
        self.source.write([native_fixture.event(3,1,128)])
        def process(pid,name,parent=1):
            fields=['S',str(parent)]+['0']*17+['7']+['0']*4
            stat=f'{pid} (process) '+' '.join(fields)
            return {'pid':pid,'raw_cmdline':name+'\x00','raw_stat_before':stat,'raw_stat_after':stat}
        self.r={'error':None,'performance_accepted':False,'pid':100,'application':process(100,'app.test'),
                'profiler':process(101,'/system/bin/hiprofilerd',201),'native_daemon':process(102,'/system/bin/native_daemon',202),
                'owned':[{'pid':201},{'pid':202}], 'observer_library_sha256':'library',
                'profiler_maps':'/data/local/tmp/snapshot.so','app_maps_before':'/system/lib64/libc.so','app_maps_after':'/system/lib64/libc.so',
                'activation_receipt':'hiprofilerd-only SHA256_Final snapshot; ABI=112\n',
                'cleanup':{'hiprofilerd':'','native_daemon':'','hiprofiler_cmd':''},'owned_sockets_removed':True,
                'trace_sha256':hashlib.sha256(self.source.path.read_bytes()).hexdigest()}
    def check(self,r):return verify(r,self.source.path,'app.test','/data/local/tmp/snapshot.so','library')
    def test_provenance_is_not_performance_acceptance(self):
        result=self.check(self.r);self.assertTrue(result['collection_provenance_verified']);self.assertFalse(result['performance_accepted'])
    def test_application_injection_wrong_library_or_unowned_daemon_rejected(self):
        for change in ('app','library','owner','cleanup','socket','trace','pid'):
            r=copy.deepcopy(self.r)
            if change=='app':r['app_maps_after']+='/data/local/tmp/snapshot.so'
            if change=='library':r['observer_library_sha256']='other'
            if change=='owner':r['owned']=[]
            if change=='cleanup':r['cleanup']['native_daemon']='102'
            if change=='socket':r['owned_sockets_removed']=False
            if change=='trace':r['trace_sha256']='other'
            if change=='pid':r['application']['raw_cmdline']='another.app'
            with self.subTest(change=change),self.assertRaises(ValueError):self.check(r)

    def test_device_clock_span_rejects_host_clock_or_missing_boundary(self):
        result={'first_event_ns':100,'last_event_ns':200}
        self.assertEqual(verify_device_clock_span({'collection_clock_before_ns':90,'collection_clock_after_ns':210},result)['clock'],'CLOCK_MONOTONIC')
        for before,after in [(True,210),(210,90),(101,210),(90,199),(90,None)]:
            with self.subTest(before=before,after=after),self.assertRaises(ValueError):
                verify_device_clock_span({'collection_clock_before_ns':before,'collection_clock_after_ns':after},result)
