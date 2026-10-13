import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from playback_progress import check_progress


def layout(position, bundle='player'):
    return {'attributes':{'bundleName':bundle},'children':[
        {'attributes':{'type':'Slider','text':str(position),'visible':'true'}}]}


class PlaybackProgressTest(unittest.TestCase):
    def test_real_playback_and_inherited_bundle(self):
        proof=check_progress(layout(2000),layout(62500),'player',60)
        self.assertEqual(proof['advanced_ms'],60500)

    def test_stopped_seeking_invalid_and_wrong_app_rejected(self):
        for end,bundle in [(2000,'player'),(180000,'player'),('nan','player'),(62000,'other')]:
            with self.subTest(end=end,bundle=bundle),self.assertRaises(ValueError):
                check_progress(layout(2000),layout(end,bundle),'player',60)

    def test_multiple_sliders_rejected(self):
        end=layout(62000)
        end['children']*=2
        with self.assertRaises(ValueError):
            check_progress(layout(2000),end,'player',60)


if __name__=='__main__':
    unittest.main()
