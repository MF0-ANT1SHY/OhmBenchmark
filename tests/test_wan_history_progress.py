import copy,json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from wan_history_progress import verify_observation
class WanHistoryProgressTest(unittest.TestCase):
    def observation(self):
        entries=[{'url':f'https://example.com/{i}','title':f'Article {i}','time':'2026/10/14 12:00:00','sticky':False} for i in range(100)]
        xml='<preferences><string key="historyList">'+json.dumps(entries)+'</string></preferences>'
        lines=[]
        for i in range(5):
            for j,message in enumerate(['onPageBegin url: https://example.com/0','onPageEnd url: https://example.com/0','onTitleReceive title: Article 0']):
                lines.append(f'{10+i}.{j:09d} 123 123 I A00000/org.example.wan.ohos/WebPage: {message}')
        before={'pid':123,'start_ticks':7,'raw_xml':xml,'raw_logs':'','started_monotonic':1.,'ended_monotonic':2.}
        after={**before,'raw_logs':'\n'.join(lines),'started_monotonic':3.,'ended_monotonic':4.}
        return {'before':before,'after':after,'expected_visits':5}
    def test_success_requires_all_normal_callbacks_and_preserved_history(self):
        self.assertEqual(verify_observation(self.observation())['completed_visits'],5)
    def test_error_page_end_and_title_are_not_success(self):
        x=self.observation();x['after']['raw_logs']+='\n15.000000000 123 123 E A00000/org.example.wan.ohos/WebPage: onErrorReceive url: https://example.com/0'
        with self.assertRaisesRegex(ValueError,'network error'):verify_observation(x)
    def test_missing_foreign_duplicate_or_restart_evidence_rejected(self):
        for change in ['missing','foreign','duplicate','restart','url']:
            x=self.observation()
            if change=='missing':x['after']['raw_logs']=x['after']['raw_logs'].split('\n',1)[1]
            if change=='foreign':x['after']['raw_logs']=x['after']['raw_logs'].replace('123 123 I','456 123 I')
            if change=='duplicate':x['after']['raw_logs']+='\n'+x['after']['raw_logs'].splitlines()[0]
            if change=='restart':x['after']['start_ticks']=8
            if change=='url':x['after']['raw_logs']=x['after']['raw_logs'].replace('https://example.com/0','https://another.example/a')
            with self.subTest(change=change),self.assertRaises(ValueError):verify_observation(x)
