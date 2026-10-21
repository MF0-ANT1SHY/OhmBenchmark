from pathlib import Path
import sys,tempfile,unittest
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from weather_icon_pixels import region_hashes,matches,icon_boxes,BUNDLE

class WeatherPixelTests(unittest.TestCase):
    def test_every_region_must_match(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'frame.png';image=Image.new('RGB',(30,30),(100,150,200));image.save(p)
            boxes=[[x,y,x+10,y+10] for x in (0,10,20) for y in (0,10,20)];reference={'boxes':boxes,'pixels':region_hashes(p,boxes)}
            self.assertTrue(matches(p,reference));image.putpixel((29,29),(0,0,0));image.save(p);self.assertFalse(matches(p,reference))

    def test_outside_frame_is_not_accepted(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'frame.png';Image.new('RGB',(5,5)).save(p)
            with self.assertRaises(ValueError):region_hashes(p,[[0,0,6,5]])

    def test_native_regions_require_complete_forecast(self):
        layout={'attributes':{'bundleName':BUNDLE},'children':[{'attributes':{'type':'Image','bounds':f'[{x},0][{x+1},1]'}} for x in range(9)]+[{'attributes':{'type':'Text','text':t}} for t in ('深圳市','近期天气','晴 28° 至 23°','东南风1-3级')]}
        self.assertEqual(len(icon_boxes(layout)),9);layout['children'].pop()
        with self.assertRaises(ValueError):icon_boxes(layout)
