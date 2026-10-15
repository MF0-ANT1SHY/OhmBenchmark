import base64
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from interview_backend_inputs import URL, verify_snapshot, verify_bracket, verify_native_sizes, verify_rendered_stems, verify_native_correspondence, verify_rendered_stem_frames, verify_capture_inputs


def snapshot(start=1,end=2,stem='question'):
    body=json.dumps({'code':10000,'success':True,'data':{'rows':[{'id':'1','stem':stem}]}}).encode()
    return {'url':URL,'http_status':200,'started_monotonic':start,'ended_monotonic':end,
            'body_base64':base64.b64encode(body).decode(),'sha256':hashlib.sha256(body).hexdigest(),'bytes':len(body)}


class BackendInputTest(unittest.TestCase):
    def test_cpu_input_receipt_rejects_raw_tampering_and_cross_window_projection(self):
        from interview_response_progress import verify_observation
        stat = '20 (interview) '+' '.join(['S']+['0']*18+['999']+['0']*5)
        before = {'pid':20,'raw_stat':stat,'raw_stat_after':stat,'raw_cmdline':'com.itcast.pass_interview',
                  'raw_logs':'','started_monotonic':2,'ended_monotonic':3}
        business = '\n'.join(f'{100+i*10}.010000000 20 21 I A0FF09/com.itcast.pass_interview/PASS_INTERVIEW_LOGGER: '
                             f'{URL}, {{"code":10000}}' for i in range(5))
        after = dict(before,raw_logs=business,started_monotonic=5,ended_monotonic=6)
        observation = {'before':before,'after':after}
        observation['progress'] = verify_observation(observation)
        sampled = snapshot(.5,1)
        wire = base64.b64decode(sampled['body_base64'])
        native = '\n'.join(f'{100+i*10}.000000000 20 21 I NETSTACK: [http_exec.cpp:499] size:{len(wire)}, errCode:0, RespCode:200' for i in range(5)).encode()
        stream = {'app_pid':20,'app_stat':stat,'logger_owner_gone':True,'ready_monotonic':1.5,'ended_monotonic':8}
        for name, raw in (('stdout',native),('stderr',b'')):
            stream[name+'_sha256'] = hashlib.sha256(raw).hexdigest()
            stream[name+'_bytes'] = len(raw)
        inputs = {'before':sampled,'after':snapshot(12,13), 'native_stream':stream,
                  'encoded':{'encoding':'identity','transfer_bytes':len(wire),'wire_sha256':sampled['sha256'],'decoded_sha256':sampled['sha256']},
                  'render_stat':stat,'render':{'started_monotonic':9,'ended_monotonic':10,'frames':[
                      {'attributes':{'bundleName':'com.itcast.pass_interview'},'children':[{'attributes':{'text':'question'}}]}]}}
        receipt = {'action_start_monotonic':4,'action_end_monotonic':7,'pids':[20],
                   'interview_responses':observation,'interview_inputs':inputs}
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);(folder/'native-stream').mkdir()
            (folder/'native-stream/stdout.bin').write_bytes(native);(folder/'native-stream/stderr.bin').write_bytes(b'')
            (folder/'encoded-backend.bin').write_bytes(wire)
            self.assertEqual(verify_capture_inputs(receipt,folder)['native_http']['successful_native_http_results'],5)
            for mutation in ('projection_window','logger_window','pid','body'):
                bad=copy.deepcopy(receipt)
                if mutation=='projection_window':bad['interview_inputs']['render']['started_monotonic']=6
                if mutation=='logger_window':bad['interview_inputs']['native_stream']['ready_monotonic']=4
                if mutation=='pid':bad['interview_inputs']['native_stream']['app_pid']=21
                if mutation=='body':bad['interview_inputs']['encoded']['decoded_sha256']='0'*64
                with self.subTest(mutation=mutation), self.assertRaises(ValueError):verify_capture_inputs(bad,folder)
            (folder/'native-stream/stdout.bin').write_bytes(native+b'changed')
            with self.assertRaises(ValueError):verify_capture_inputs(receipt,folder)

    def test_scrolled_projection_requires_every_stem_visible_in_the_app(self):
        record = snapshot()
        body = json.loads(base64.b64decode(record['body_base64']))
        body['data']['rows'].append({'id':'two','stem':'second question'})
        raw = json.dumps(body).encode()
        record.update(body_base64=base64.b64encode(raw).decode(), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
        def frame(text, bundle='com.itcast.pass_interview', visible='true'):
            return {'attributes':{'bundleName':bundle},'children':[{'attributes':{'text':text,'visible':visible}}]}
        frames = [frame('question'), frame('second question')]
        self.assertEqual(verify_rendered_stem_frames(frames,record)['rendered_stems_verified'],2)
        for bad in (frames[:1], [frames[0],frame('second question','other')],
                    [frames[0],frame('second question',visible='false')]):
            with self.assertRaises(ValueError):verify_rendered_stem_frames(bad,record)

    def test_continuous_native_results_match_each_actual_business_callback_not_old_backfill(self):
        stat = '20 (interview) '+' '.join(['S']+['0']*18+['999']+['0']*5)
        before = {'pid':20,'raw_stat':stat,'raw_stat_after':stat,'raw_cmdline':'com.itcast.pass_interview',
                  'raw_logs':'','started_monotonic':1,'ended_monotonic':2}
        business = '\n'.join(f'{100+i*10}.010000000 20 21 I A0FF09/com.itcast.pass_interview/PASS_INTERVIEW_LOGGER: '
                             f'{URL}, {{"code":10000}}' for i in range(5))
        after = dict(before,raw_logs=business,started_monotonic=3,ended_monotonic=4)
        observation = {'before':before,'after':after}
        def result(epoch, pid=20, size=873):
            return f'{epoch}.000000000 {pid} 21 I NETSTACK: [http_exec.cpp:499] size:{size}, errCode:0, RespCode:200'
        native = '\n'.join([result(50), *[result(100+i*10) for i in range(5)]])
        proof = verify_native_correspondence(native, observation, 873)
        self.assertEqual(proof['successful_native_http_results'],5)
        self.assertFalse(proof['actual_app_body_hash_verified'])
        for kind in ('missing','duplicate','foreign','size','clock'):
            text = native
            if kind == 'missing': text = '\n'.join(native.splitlines()[:-1])
            if kind == 'duplicate': text += '\n'+native.splitlines()[-1]
            if kind == 'foreign': text = text.replace(' 20 21 ', ' 99 21 ')
            if kind == 'size': text = text.replace('size:873', 'size:4397')
            if kind == 'clock': text = text.replace('140.000000000', '145.000000000')
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                verify_native_correspondence(text, observation, 873)

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
