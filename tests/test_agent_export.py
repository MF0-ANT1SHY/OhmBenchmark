import copy
import ast
import sys
import unittest
import tempfile
import json
import hashlib
from unittest.mock import patch
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from export_agent_data import app_report,reproduction_script,export,app_scheduler_report,app_memory_report


class AppReportTests(unittest.TestCase):
    def test_binary_only_export_has_no_source_or_evaluator_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);cid='private-case'
            (root/'tools').mkdir()
            (root/'tools/ui_driver.py').write_text((Path(__file__).resolve().parents[1]/'tools/ui_driver.py').read_text())
            folder=root/'artifacts/clean'/cid/'unfixed';folder.mkdir(parents=True)
            case_dir=root/'cases'/cid;case_dir.mkdir(parents=True)
            def put(path,data):path.write_text(json.dumps(data))
            package=b'package';digest=hashlib.sha256(package).hexdigest()
            (folder/'app-export.hap').write_bytes(package)
            (folder/'app-unsigned.hap').write_bytes(package)
            put(case_dir/'workload.json',{'description':'private-case','setup':[],'measured':[],'verify':[]})
            put(case_dir/'case.json',{'host_app':{'local_path':'repo','bundle_name':'app.bundle'},
                                     'testcase':{'workload':'workload.json'}})
            put(folder/'build.json',{'status':'PASS','hap':{'passed':True,'sha256':digest},
                                    'source':{'tree':'tree','passed':True}})
            put(folder/'sign.json',{'status':'PASS','unsigned_sha256':digest,'audit':{'passed':True,'sha256':digest}})
            capture=folder/'cpu-captures/round-1';capture.mkdir(parents=True)
            put(capture/'capture.json',{'status':'CAPTURED','signed_sha256':digest,'pids':[10],
                                       'plan_sha256':hashlib.sha256((case_dir/'workload.json').read_bytes()).hexdigest()})
            put(capture/'report.json',self.report())
            with patch('export_agent_data.ROOT',root),patch('export_agent_data.app_ref',return_value='ref'),\
                    patch('export_agent_data.require_accepted_case'),\
                    patch('export_agent_data.subprocess.check_output',return_value='tree\n'),\
                    patch('export_agent_data.verify_installable_profile'),\
                    patch('export_agent_data.subprocess.run') as archive:
                destination=root/'export'
                export(cid,destination,'slow launch',1)
                archive.assert_not_called()
                with patch('export_agent_data.verify_installable_profile',side_effect=ValueError('signed app profile is expired')):
                    with self.assertRaisesRegex(ValueError,'expired'):
                        export(cid,root/'expired-export','slow launch',1)
                self.assertFalse((root/'expired-export').exists())
                from test_trace_evidence import NativeTraceEvidenceTest
                fixture=NativeTraceEvidenceTest();fixture.setUp()
                self.addCleanup(fixture.doCleanups)
                native_folder=folder/'trace-captures/round-1';native_folder.mkdir(parents=True)
                (native_folder/'trace.htrace').write_bytes(fixture.trace.read_bytes())
                native_capture=copy.deepcopy(fixture.receipt)
                native_capture.update({'signed_sha256':digest,
                    'plan_sha256':hashlib.sha256((case_dir/'workload.json').read_bytes()).hexdigest()})
                put(native_folder/'capture.json',native_capture)
                put(case_dir/'case.json',{'host_app':{'local_path':'repo','bundle_name':'com.sheafreader.hm'},
                    'testcase':{'workload':'workload.json'},'test_oracle':{'metric':'trace_cpu_ms'}})
                trace_destination=root/'trace-export'
                export(cid,trace_destination,'slow refresh',1)
                self.assertEqual({p.name for p in trace_destination.iterdir()},
                                 {'app.hap','workload.json','reproduce.py','profile.json','symptom.txt'})
                native_profile=json.loads((trace_destination/'profile.json').read_text())
                self.assertEqual(native_profile['app_cpu_ns'],8000000)
                self.assertNotIn('marker_token',(trace_destination/'profile.json').read_text())
                archive.assert_not_called()
                from test_system_pss import ProcessMemoryTests
                memory_folder=folder/'pss-captures/round-1';memory_folder.mkdir(parents=True)
                memory_capture=ProcessMemoryTests().window()
                memory_capture.update({'status':'CAPTURED','signed_sha256':digest,
                    'plan_sha256':hashlib.sha256((case_dir/'workload.json').read_bytes()).hexdigest()})
                put(memory_folder/'capture.json',memory_capture)
                put(case_dir/'case.json',{'host_app':{'local_path':'repo','bundle_name':'app.bundle'},
                    'testcase':{'workload':'workload.json'},'test_oracle':{'metric':'app_pss_bytes'}})
                memory_destination=root/'memory-export'
                export(cid,memory_destination,'memory grows during use',1)
                self.assertEqual({p.name for p in memory_destination.iterdir()},
                                 {'app.hap','workload.json','reproduce.py','profile.json','symptom.txt'})
                memory_profile=json.loads((memory_destination/'profile.json').read_text())
                self.assertEqual(len(memory_profile['snapshots']),3)
                self.assertEqual(memory_profile['processNameMap'],{'123':'app.bundle'})
                archive.assert_not_called()
                put(folder/'sign.json',{'status':'PASS','unsigned_sha256':'other-build',
                                       'audit':{'passed':True,'sha256':digest}})
                with self.assertRaisesRegex(ValueError,'different clean build'):
                    export(cid,root/'bad-export','slow launch',1)
                self.assertFalse((root/'bad-export').exists())
            self.assertEqual({p.name for p in destination.iterdir()},
                             {'app.hap','workload.json','reproduce.py','profile.json','symptom.txt'})
            self.assertNotIn('private-case',(destination/'workload.json').read_text())

    def test_reproduction_entrypoint_has_no_evaluator_or_profiler_dependencies(self):
        source=reproduction_script()
        parsed=ast.parse(source)
        ui=next(n for n in parsed.body if isinstance(n,ast.ClassDef))
        self.assertNotIn('profiled',[n.name for n in ui.body if isinstance(n,ast.FunctionDef)])
        self.assertNotIn('remote_device',source)
        self.assertNotIn('PerfTestCase',source)
        arguments=[n for n in ast.walk(parsed) if isinstance(n,ast.List) and len(n.elts)==3]
        self.assertTrue(any(isinstance(n.elts[0],ast.Constant) and n.elts[0].value=='hdc'
            and isinstance(n.elts[1],ast.Constant) and n.elts[1].value=='shell'
            and isinstance(n.elts[2],ast.Name) and n.elts[2].id=='command' for n in arguments))

    def report(self):
        def process(pid, symbol, file_id, count):
            return {'pid': pid, 'eventCount': count, 'threads': [
                {'tid': pid, 'eventCount': count, 'sampleCount': 2,
                 'libs': [{'fileId': file_id, 'eventCount': count, 'functions': [{'symbol': symbol, 'counts': [2,count,count]}]}],
                 'CallOrder': {'symbol': -1, 'callStack': [{'symbol': symbol, 'callStack': []}]},
                 'CalledOrder': {'symbol': symbol, 'callStack': []}}]}
        return {'deviceCommandLine': 'private-evaluator-command', 'totalRecordSamples': 999,
                'processNameMap': {'10':'app.bundle','20':'sqlite3'},
                'threadNameMap': {'10':'app','20':'private-checker'},
                'symbolsFileList': ['private-checker.so','app.so','unused.so'],
                'SymbolMap': {'7':{'file':1,'symbol':'BusinessFunction'},
                              '8':{'file':0,'symbol':'PrivateOracle'},
                              '9':{'file':2,'symbol':'UnreferencedPrivateSymbol'}},
                'recordSampleInfo':[{'eventConfigName':'hw-instructions','eventCount':300,
                    'processes':[process(10,7,1,100),process(20,8,0,200)]}]}

    def test_private_processes_and_unreferenced_symbols_are_removed(self):
        raw = self.report()
        original = copy.deepcopy(raw)
        result = app_report(raw, [10], 'app.bundle')
        self.assertEqual(raw, original)
        self.assertEqual(result['processNameMap'], {'10':'app.bundle'})
        self.assertEqual(result['threadNameMap'], {'10':'app'})
        self.assertEqual(result['symbolsFileList'], ['app.so'])
        self.assertEqual(result['SymbolMap'], {'7':{'file':0,'symbol':'BusinessFunction'}})
        self.assertEqual(result['totalRecordSamples'], 2)
        self.assertNotIn('deviceCommandLine', result)
        event = result['recordSampleInfo'][0]
        self.assertEqual(event['eventCount'], 100)
        self.assertEqual(event['processes'][0]['threads'][0]['libs'][0]['fileId'], 0)
        self.assertEqual(event['processes'][0]['threads'][0]['CallOrder'], original['recordSampleInfo'][0]['processes'][0]['threads'][0]['CallOrder'])

    def test_wrong_or_missing_app_cannot_be_exported(self):
        with self.assertRaises(ValueError):
            app_report(self.report(), [20], 'app.bundle')
        raw = self.report()
        raw['recordSampleInfo'][0]['processes'] = []
        with self.assertRaises(ValueError):
            app_report(raw, [10], 'app.bundle')

    def test_unresolved_jit_frame_preserves_counts_without_inventing_name(self):
        raw = self.report()
        del raw['SymbolMap']['7']
        result = app_report(raw, [10], 'app.bundle')
        self.assertEqual(result['SymbolMap']['7'], {'file':0,'symbol':'[unresolved]'})
        self.assertEqual(result['recordSampleInfo'][0]['eventCount'], 100)

    def test_scheduler_export_contains_only_relative_app_intervals(self):
        from test_trace_evidence import NativeTraceEvidenceTest
        fixture=NativeTraceEvidenceTest()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        capture=copy.deepcopy(fixture.receipt)
        capture.update({'fixture_sha256':'private-input','remote_artifacts':'private-location',
                        'paired_ratios':[2,2,2],'case':'private-case'})
        profile=app_scheduler_report(fixture.trace,capture,'com.sheafreader.hm')
        text=json.dumps(profile)
        self.assertEqual(profile['processNameMap'],{'100':'com.sheafreader.hm'})
        self.assertEqual(sum(x['duration_ns'] for x in profile['intervals']),8000000)
        self.assertEqual({x['tid'] for x in profile['intervals']},{100,101,102})
        self.assertTrue(all(0<=x['start_ns']<6000000 for x in profile['intervals']))
        for private in ('marker_token','private-input','private-location','private-case','paired_ratios','W:'+('a'*32)):
            self.assertNotIn(private,text)
        self.assertNotIn('999',text)

    def test_scheduler_export_rejects_forged_values_and_changed_process(self):
        from test_trace_evidence import NativeTraceEvidenceTest
        fixture=NativeTraceEvidenceTest()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        capture=copy.deepcopy(fixture.receipt)
        capture['scheduler_cpu']['app_cpu_ns']=1
        with self.assertRaises(ValueError):
            app_scheduler_report(fixture.trace,capture,'com.sheafreader.hm')
        capture=copy.deepcopy(fixture.receipt)
        capture['process_after']['start_ticks']+=1
        with self.assertRaises(ValueError):
            app_scheduler_report(fixture.trace,capture,'com.sheafreader.hm')

    def test_memory_export_preserves_all_observations_without_private_metadata(self):
        from test_system_pss import ProcessMemoryTests
        record=ProcessMemoryTests().window()
        record.update({'case':'private-case','fixture_sha256':'private-input','preparation':{'path':'private-path'},
                       'paired_ratios':[2,2,2],'remote_artifacts':'private-artifacts'})
        result=app_memory_report(record,'app.bundle')
        self.assertEqual(result['processNameMap'],{'123':'app.bundle'})
        self.assertEqual([s['pss_bytes'] for s in result['snapshots']],[200*1024,500*1024,300*1024])
        self.assertEqual([s['time_ns'] for s in result['snapshots']],[0,11000000000,26000000000])
        self.assertEqual(result['workload_start_ns'],1000000000)
        for private in ('private-case','private-input','private-path','private-artifacts','paired_ratios','raw_stat'):
            self.assertNotIn(private,json.dumps(result))
        record['snapshots'][1]['pss_bytes']=1
        with self.assertRaises(ValueError):
            app_memory_report(record,'app.bundle')


if __name__ == '__main__':
    unittest.main()
