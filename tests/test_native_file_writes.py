from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from native_file_writes import returned_writes, verify_retention


def event(stamp, direction, offset, size, tail, tid=42210, ino=290353, kind='write'):
    return (f' <...>-{tid} (42096) [008] .... {stamp}: hmfs_{kind}_{direction}: '
            f'dev=260,79 ino={ino} offset={offset} size={size} {tail}')


class NativeWriteTest(unittest.TestCase):
    def test_every_online_cpu_must_retain_both_exact_native_boundaries(self):
        token='a'*32
        def marker(cpu,side,stamp):
            return f' sh-10 (9) [{cpu:03}] .... {stamp}: tracing_mark_write: F:{token}:{side}:{cpu}'
        rows=[marker(0,'begin','1.0'),marker(1,'begin','1.1'),marker(0,'end','2.0'),marker(1,'end','2.1')]
        result=verify_retention('\n'.join(rows),token,[0,1])
        self.assertEqual((result['window_begin_epoch'],result['window_end_epoch']),('1.1','2.0'))
        for bad in (rows[:-1],rows+[rows[-1]],rows+['CPU:1 [LOST 2 EVENTS]'],
                    [rows[0].replace('[000]','[001]'),*rows[1:]]):
            with self.assertRaises(ValueError):verify_retention('\n'.join(bad),token,[0,1])

    def pair(self):
        return [event('1.000001','enter',0,24,'i_size=0 entry_name=owned'),
                event('1.000002','exit',24,24,'res=24'),
                event('1.000003','enter',24,7,'i_size=24 entry_name=owned'),
                event('1.000004','exit',31,7,'res=7')]

    def verify(self, rows):
        return returned_writes('\n'.join(rows), [42210], [(260,79,290353)])

    def test_actual_returns_not_requested_sizes_or_unrelated_inodes(self):
        result = self.verify(self.pair()+[event('2.0','exit',999,999,'res=999',ino=999)])
        self.assertEqual((result['completed_writes'], result['returned_bytes']), (2,31))
        rows = [event('1.0','enter',0,24,'i_size=0 entry_name=owned'),
                event('2.0','exit',7,24,'res=7')]
        self.assertEqual(self.verify(rows)['returned_bytes'],7)

    def test_missing_duplicate_wrong_thread_and_failed_returns_are_rejected(self):
        rows = self.pair()
        bad = [rows[1:], rows[:-1], [rows[0],rows[0],*rows[1:]],
               [rows[0],rows[1].replace('res=24','res=-5')],
               [x.replace('-42210','-42211') for x in rows],
               [x.replace('hmfs_write_','hmfs_write_iter_') for x in rows],
               [rows[0],rows[1].replace('offset=24','offset=23')],
               [rows[0],rows[1].replace('res=24','res=25')],
               rows+['CPU:8 [LOST 1 EVENTS]']]
        for index, candidate in enumerate(bad):
            with self.subTest(index=index), self.assertRaises(ValueError):self.verify(candidate)

    def test_zero_is_not_evidence_of_a_complete_capture(self):
        result = self.verify([])
        self.assertEqual(result['returned_bytes'],0)
        self.assertNotIn('capture_complete',result)
