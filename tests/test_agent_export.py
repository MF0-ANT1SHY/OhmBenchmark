import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from export_agent_data import app_report


class AppReportTests(unittest.TestCase):
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
