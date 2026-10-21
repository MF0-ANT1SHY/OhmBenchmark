import hashlib,unittest
from ytsearch_data_service import response
from ytsearch_progress import verify_requests
class PayloadTest(unittest.TestCase):
    def record(self,variant,queries):
        rows=[]
        for q in queries:
            path='/search?keyword='+q;body=response(path)[2];rows.append(dict(path=path,start=2,end=3,status=200,error=None,body_bytes=len(body),sent_bytes=len(body),body_sha256=hashlib.sha256(body).hexdigest()))
        return dict(variant=variant,action_start_monotonic=1,action_end_monotonic=4,requests=rows)
    def test_completed_payload_reduction(self):
        u=self.record('unfixed',['electronic'[:n] for n in range(1,11)]+['electronic']);f=self.record('fixed',['electronic']*2)
        self.assertEqual(verify_requests(u)['search_response_body_bytes']/verify_requests(f)['search_response_body_bytes'],5.5)
    def test_partial_write_rejected(self):
        r=self.record('fixed',['electronic']);r['requests'][0]['sent_bytes']-=1
        with self.assertRaises(ValueError):verify_requests(r)
    def test_fixed_prefix_is_not_success(self):
        with self.assertRaises(ValueError):verify_requests(self.record('fixed',['electro','electronic']))
    def test_old_request_is_not_counted(self):
        r=self.record('fixed',['electronic']);r['requests'][0]['start']=0
        with self.assertRaises(ValueError):verify_requests(r)
