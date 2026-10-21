import json,unittest
from ytsearch_data_service import response,CATALOGUE
class SearchServiceTest(unittest.TestCase):
    def test_prefixes_are_real_searches(self):
        for n in range(1,11):
            status,kind,body=response('/search?keyword='+ 'electronic'[:n]);self.assertEqual(status,200);self.assertEqual(json.loads(body),CATALOGUE)
    def test_no_oracle_routes(self):
        for path in ('/status','/metrics','/search?keyword=electronic&variant=fixed','/search?keyword=a&keyword=b'):
            self.assertEqual(response(path)[0],404)
    def test_unmatched_query_is_empty(self):self.assertEqual(json.loads(response('/search?keyword=nonexistent')[2]),[])
