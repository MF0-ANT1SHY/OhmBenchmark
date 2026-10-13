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
from export_agent_data import app_report,reproduction_script,export


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
                    patch('export_agent_data.subprocess.check_output',return_value='tree\n'),\
                    patch('export_agent_data.subprocess.run') as archive:
                destination=root/'export'
                export(cid,destination,'slow launch',1)
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


if __name__ == '__main__':
    unittest.main()
