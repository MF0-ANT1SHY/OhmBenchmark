import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from music_service_fixture import prepare,same_instance


class MusicFixtureTest(unittest.TestCase):
    def test_online_data_cannot_claim_to_prepare_local_audio_workload(self):
        class Remote:
            def python(self,*args,**kwargs):raise AssertionError('must not access server')
        with self.assertRaisesRegex(ValueError,'not input preparation'):
            prepare(Remote(),{'id':'cloudmusic_play_time_high_frequency_update',
                             'host_app':{'bundle_name':'cc.chenlvin.cloudmusic'}})

    def test_same_data_after_service_restart_does_not_prove_continuity(self):
        before={'sha256':'data','source_sha256':'source','base_url':'url','service_pid':12,'service_start_ticks':100}
        same_instance(before,dict(before))
        for key,value in [('service_pid',13),('service_start_ticks',200),('sha256','other'),('source_sha256',None)]:
            with self.subTest(key=key),self.assertRaises(ValueError):
                same_instance(before,{**before,key:value})


if __name__=='__main__':unittest.main()
