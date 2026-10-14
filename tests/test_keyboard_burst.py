import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from ui_driver import UI

class KeyboardBurstTest(unittest.TestCase):
    def ui(self, final='music', initial=''):
        calls=[]
        def shell(command):
            calls.append(command)
            return ''.join(f'you raised the key {key}\n' for key in (2029,2037,2035,2025,2019))
        ui=UI(shell,'app.bundle')
        states=iter([{'text':initial,'bounds':'[0,0][10,10]'}, {'text':final}])
        ui.find=lambda selector:next(states)
        return ui,calls
    def test_single_device_command_without_intermediate_ui_replacement(self):
        ui,calls=self.ui();ui.run([{'op':'type_keys','selector':{'hint':'Search'},'value':'music','interval_ms':50}])
        self.assertEqual(len(calls),2)
        self.assertEqual(calls[1],'uinput -K -d 2029 -u 2029 -i 50 -d 2037 -u 2037 -i 50 -d 2035 -u 2035 -i 50 -d 2025 -u 2025 -i 50 -d 2019 -u 2019')
    def test_rejects_unsafe_or_invalid_keys_before_injection(self):
        for value,interval in [('x;reboot',50),('',50),('Music',50),('music',True),('music',0)]:
            ui,calls=self.ui()
            with self.subTest(value=value,interval=interval),self.assertRaises(ValueError):ui.type_keys({},value,interval)
            self.assertEqual(calls,[])
    def test_nonempty_input_and_mismatched_result_are_not_success(self):
        ui,calls=self.ui(initial='old')
        with self.assertRaisesRegex(RuntimeError,'empty input'):ui.type_keys({},'music')
        self.assertEqual(calls,[])
        ui,calls=self.ui(final='musi')
        with self.assertRaisesRegex(RuntimeError,'does not match'):ui.type_keys({},'music')
