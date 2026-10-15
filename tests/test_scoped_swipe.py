from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from ui_driver import UI


class ScopedSwipeTest(unittest.TestCase):
    def test_refresh_gesture_stays_inside_native_component(self):
        calls = []
        ui = UI(calls.append)
        with patch.object(ui, 'find', return_value={'bounds':'[0,1728][1260,2580]'}) as find, patch('ui_driver.time.sleep'):
            ui.run([{'op':'swipe','direction':'down','selector':{'type':'Refresh','match':'exact'}}])
        find.assert_called_once_with({'type':'Refresh','match':'exact'})
        self.assertEqual(calls, ['uitest uiInput swipe 630 1984 630 2393 1000'])

    def test_existing_fullscreen_swipe_is_unchanged(self):
        calls = []
        ui = UI(calls.append)
        with patch.object(ui, 'layout', return_value={'attributes':{'bounds':'[0,0][1260,2844]'}}), patch('ui_driver.time.sleep'):
            ui.run([{'op':'swipe'}])
        self.assertEqual(calls, ['uitest uiInput swipe 630 2218 630 853 1000'])

    def test_degenerate_component_cannot_produce_a_fake_gesture(self):
        ui = UI(lambda command: self.fail('must not send a gesture'))
        with patch.object(ui, 'find', return_value={'bounds':'[0,1728][1260,1728]'}), self.assertRaises(ValueError):
            ui.run([{'op':'swipe','selector':{'type':'Refresh'}}])
