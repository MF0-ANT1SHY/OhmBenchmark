import hashlib
from pathlib import Path
import struct
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from native_heap_events import compute


def integer(value):
    result=bytearray()
    while value>=128:
        result.append((value&127)|128);value>>=7
    return bytes(result)+bytes([value])


def field(number,value):
    return integer(number*8+(2 if isinstance(value,bytes) else 0))+(integer(len(value))+value if isinstance(value,bytes) else integer(value))


def event(kind,address,size=0,pid=100,second=10):
    payload=field(1,pid)+field(2,101)+field(3,address)
    if kind==3:payload+=field(4,size)
    return field(1,second)+field(kind,payload)


class NativeHeapEventTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'trace.htrace'
        self.config_fields={1:100,9:1,16:1,17:1,23:b'mono'}
        self.config=b''.join(field(k,v) for k,v in self.config_fields.items())

    def write(self,events,config=None):
        messages=[field(1,b'nativehook_config')+field(3,self.config if config is None else config),
                  field(1,b'nativehook')+field(3,b''.join(field(1,e) for e in events))]
        payload=b''.join(struct.pack('<I',len(message))+message for message in messages)
        header=bytearray(1024);struct.pack_into('<QQII',header,0,0x464F5250534F484F,1024+len(payload),0x10000,2*len(messages))
        header[24:56]=hashlib.sha256(payload).digest();self.path.write_bytes(header+payload)

    def test_exact_address_matching_reuse_and_preexisting_frees(self):
        self.write([event(4,777,second=9),event(3,1,128),event(3,2,256),
                    event(4,1,second=11),event(3,1,64,second=12)])
        result=compute(self.path,100)
        self.assertEqual(result['retained_bytes'],320)
        self.assertEqual(result['matched_frees'],1)
        self.assertEqual(result['preexisting_unmatched_frees'],1)
        self.assertFalse(result['performance_accepted'])

    def test_truncated_corrupt_and_incomplete_container_rejected(self):
        self.write([event(3,1,128)]);original=self.path.read_bytes()
        for kind in ('truncate','corrupt','segments','datatype'):
            blob=bytearray(original)
            if kind=='truncate':blob.pop()
            if kind=='corrupt':blob[-1]^=1
            if kind=='segments':struct.pack_into('<I',blob,20,6)
            if kind=='datatype':struct.pack_into('<I',blob,56,1000)
            self.path.write_bytes(blob)
            with self.subTest(kind=kind),self.assertRaises(ValueError):compute(self.path,100)

    def test_foreign_pid_duplicate_live_address_and_aggregate_records_rejected(self):
        for events in ([event(3,1,128,pid=200)], [event(3,1,128),event(3,1,128)],
                       [event(15,1)], [event(4,1),event(4,1)]):
            self.write(events)
            with self.assertRaises(ValueError):compute(self.path,100)

    def test_sampling_filtering_wrong_clock_or_nonaccurate_config_rejected(self):
        for number,value in ((24,4096),(4,4096),(17,0),(23,b'realtime'),(23,b'monotonic')):
            changed={**self.config_fields,number:value}
            self.write([event(3,1,128)],b''.join(field(k,v) for k,v in changed.items()))
            with self.subTest(number=number),self.assertRaises(ValueError):compute(self.path,100)
