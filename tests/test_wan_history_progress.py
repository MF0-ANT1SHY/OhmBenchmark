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
    def test_title_before_page_end_is_also_a_complete_unambiguous_load(self):
        x=self.observation();lines=x['after']['raw_logs'].splitlines()
        for i in range(0,len(lines),3):
            lines[i+1],lines[i+2]=lines[i+2].replace('.000000002 ','.000000001 '),lines[i+1].replace('.000000001 ','.000000002 ')
        x['after']['raw_logs']='\n'.join(lines)
        self.assertEqual(verify_observation(x)['completed_visits'],5)
    def test_multiple_real_title_updates_are_not_extra_page_visits(self):
        x=self.observation()
        x['after']['raw_logs']+='\n14.000000003 123 123 I A00000/org.example.wan.ohos/WebPage: onTitleReceive title: Article 0'
        self.assertEqual(verify_observation(x)['completed_visits'],5)
    def test_unchanged_urls_do_not_permit_payload_corruption(self):
        import xml.etree.ElementTree as ET
        for field,value,index in [('title','Replaced',1),('time','2026/10/15 00:00:00',1),('sticky',True,1),('title','Wrong loaded title',0)]:
            x=self.observation();root=ET.fromstring(x['after']['raw_xml']);entries=json.loads(root[0].text)
            entries[index][field]=value;root[0].text=json.dumps(entries);x['after']['raw_xml']=ET.tostring(root,encoding='unicode')
            with self.subTest(field=field,index=index),self.assertRaises(ValueError):verify_observation(x)
    def test_overlapping_loads_and_orphan_titles_are_not_success(self):
        for mode in ('overlap','orphan'):
            x=self.observation();lines=x['after']['raw_logs'].splitlines()
            if mode=='overlap':lines.insert(1,'10.000000000 123 123 I A00000/org.example.wan.ohos/WebPage: onPageBegin url: https://example.com/1')
            else:lines[0],lines[2]=lines[2].replace('.000000002 ','.000000000 '),lines[0].replace('.000000000 ','.000000002 ')
            x['after']['raw_logs']='\n'.join(lines)
            with self.subTest(mode=mode),self.assertRaises(ValueError):verify_observation(x)
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

    def checkpointed(self):
        observation=self.observation();lines=observation['after']['raw_logs'].splitlines()
        observation['during']=[{**observation['after'],'raw_logs':'\n'.join(lines[:3*(i+1)]),
            'started_monotonic':3+i*2,'ended_monotonic':3.5+i*2} for i in range(5)]
        observation['after'].update(raw_logs='\n'.join(lines[3:]),started_monotonic=14.,ended_monotonic=15.)
        return observation

    def test_native_checkpoints_retain_first_load_when_final_log_buffer_rotates(self):
        observation=self.checkpointed()
        self.assertEqual(verify_observation(observation)['completed_visits'],5)
        observation.pop('during')
        with self.assertRaises(ValueError):verify_observation(observation)

    def test_checkpoint_count_does_not_replace_actual_five_page_callback_evidence(self):
        observation=self.checkpointed()
        for state in observation['during']:state['raw_logs']='\n'.join(state['raw_logs'].splitlines()[3:])
        with self.assertRaises(ValueError):verify_observation(observation)

    def test_stale_foreign_or_corrupt_native_checkpoints_are_rejected(self):
        for kind in ('missing','pid','ticks','clock','duplicate'):
            observation=self.checkpointed()
            if kind=='missing':observation['during'].pop()
            if kind=='pid':observation['during'][0]['pid']=456
            if kind=='ticks':observation['during'][0]['start_ticks']=8
            if kind=='clock':observation['during'][0]['started_monotonic']=1
            if kind=='duplicate':observation['during'][0]['raw_logs']+='\n'+observation['during'][0]['raw_logs'].splitlines()[0]
            with self.subTest(kind=kind),self.assertRaises(ValueError):verify_observation(observation)
