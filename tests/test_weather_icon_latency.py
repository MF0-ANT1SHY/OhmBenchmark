from pathlib import Path
import sys,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from weather_icon_latency import bounds_from_frames

class IconTimingTests(unittest.TestCase):
    def record(self):return {'launch_start':10,'launch_command_end':10.2,'baseline':{'start':8,'end':9,'ready':False},'frames':[{'start':11,'end':11.5,'ready':False},{'start':12,'end':12.5,'ready':True}]}
    def test_conservative_bounds(self):self.assertEqual(bounds_from_frames(self.record()),{'lower_s':1,'upper_s':2.5})
    def test_first_frame_ready_has_no_positive_lower_bound(self):
        r=self.record();r['frames']=r['frames'][1:];self.assertEqual(bounds_from_frames(r)['lower_s'],0)
    def test_missing_transition_or_invalid_order_rejected(self):
        for mode in range(4):
            r=self.record()
            if mode==0:r['baseline']['ready']=True
            if mode==1:r['frames'][0]['ready']=True
            if mode==2:r['frames'][-1]['ready']=False
            if mode==3:r['frames'][-1]['start']=11
            with self.assertRaises(ValueError):bounds_from_frames(r)

class IconRequestTests(unittest.TestCase):
    def record(self,variant):
        rows=[{'path':f'/v3/weather/weatherInfo?city={city}&extensions=all','start':1,'end':1.1} for city in ('440300','440100')]
        if variant=='unfixed':rows += [{'path':'/weather/'+name+'.img','start':2,'end':6.01} for name in ('sunny','cloudy','overcast','rain')]
        return {'variant':variant,'launch_start':0,'action_end_monotonic':7,'requests':rows}

    def test_correct_cold_and_bundled_requests(self):
        from weather_icon_latency import verify_requests
        for variant in ('unfixed','fixed'):verify_requests(self.record(variant))

    def test_missing_remote_icon_or_unexpected_fixed_download_rejected(self):
        from weather_icon_latency import verify_requests
        u=self.record('unfixed');u['requests'].pop()
        f=self.record('unfixed');f['variant']='fixed'
        for record in (u,f):
            with self.assertRaises(ValueError):verify_requests(record)

    def test_shortened_delay_or_request_outside_window_rejected(self):
        from weather_icon_latency import verify_requests
        for end in (5.9,8):
            record=self.record('unfixed');record['requests'][-1]['end']=end
            with self.assertRaises(ValueError):verify_requests(record)
