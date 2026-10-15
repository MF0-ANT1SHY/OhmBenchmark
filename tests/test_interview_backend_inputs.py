import base64
import copy
import hashlib
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from interview_backend_inputs import URL, verify_snapshot, verify_bracket, verify_native_sizes, verify_rendered_stems


def snapshot(start=1,end=2,stem='question'):
    body=json.dumps({'code':10000,'success':True,'data':{'rows':[{'id':'1','stem':stem}]}}).encode()
    return {'url':URL,'http_status':200,'started_monotonic':start,'ended_monotonic':end,
            'body_base64':base64.b64encode(body).decode(),'sha256':hashlib.sha256(body).hexdigest(),'bytes':len(body)}


class BackendInputTest(unittest.TestCase):
    def test_only_identical_successful_bodies_bracketing_actual_trial_match(self):
        self.assertEqual(verify_bracket(snapshot(),snapshot(5,6),3,4)['response_bytes'],snapshot()['bytes'])
        for after in (snapshot(3,4),snapshot(5,6,'changed')):
            with self.assertRaises(ValueError):verify_bracket(snapshot(),after,3,4)
        bad=copy.deepcopy(snapshot());bad['sha256']='0'*64
        with self.assertRaises(ValueError):verify_snapshot(bad)

    def test_native_success_count_size_and_process_identity_are_mandatory(self):
        def logs(size=100,code=0,pid=20,count=5):
            return '\n'.join(f'100.{i:09} {pid} 21 I app/NETSTACK: [http_exec.cpp:499] taskid={i}, size:{size}, errCode:{code}, RespCode:200, method:GET' for i in range(count))
        result=verify_native_sizes('',logs(),20,100)
        self.assertFalse(result['actual_app_body_hash_verified'])
        self.assertEqual(result['native_transfer_bytes'],100)
        for raw in (logs(99),logs(code=2300006),logs(pid=21),logs(count=4)):
            with self.assertRaises(ValueError):verify_native_sizes('',raw,20,100)
        with self.assertRaises(ValueError):verify_native_sizes(logs(),logs(),20,100)
        # The actual sampled wire body can be smaller than decoded JSON. Do
        # not compare the native curl transfer counter to decoded body length.
        self.assertEqual(verify_native_sizes('',logs(size=873),20,873)['native_transfer_bytes'],873)
        with self.assertRaises(ValueError):verify_native_sizes('',logs(size=873),20,4397)

    def test_actual_app_projection_cannot_come_from_another_window_or_partial_list(self):
        layout={'attributes':{'bundleName':'com.itcast.pass_interview'},'children':[{'attributes':{'text':'question'}}]}
        self.assertEqual(verify_rendered_stems(layout,snapshot())['rendered_stems_verified'],1)
        layout['attributes']['bundleName']='other'
        with self.assertRaises(ValueError):verify_rendered_stems(layout,snapshot())
