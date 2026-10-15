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

class QuerySequenceTest(unittest.TestCase):
    def ui(self, final='question19', releases=20):
        calls=[]
        def shell(command):
            calls.append(command)
            return 'you raised the key 2054\n'*releases
        ui=UI(shell,'app.bundle');states=iter([{'text':'old','bounds':'[0,0][10,10]'},{'text':final}]);ui.find=lambda selector:next(states)
        return ui,calls

    def test_all_submits_use_normal_keys_without_per_query_layout_round_trips(self):
        ui,calls=self.ui();ui.submit_queries({},['question'+str(i) for i in range(20)])
        self.assertEqual(len(calls),2)
        self.assertTrue(calls[1].startswith('uinput -K '))
        self.assertEqual(calls[1].count('-d 2054 -u 2054'),20)
        self.assertEqual(calls[1].count('-d 2072 -d 2017 -u 2017 -u 2072 -d 2055 -u 2055'),20)

    def test_missing_submit_and_wrong_final_text_are_not_success(self):
        for final,releases in [('question18',20),('question19',19)]:
            ui,calls=self.ui(final,releases)
            with self.assertRaises(RuntimeError):ui.submit_queries({},['question'+str(i) for i in range(20)])

    def test_invalid_sequence_is_rejected_before_any_input(self):
        for values,interval,pause in [([],50,150),(['x;reboot'],50,150),(['x'],True,150),(['x'],50,-1)]:
            ui,calls=self.ui()
            with self.assertRaises(ValueError):ui.submit_queries({},values,interval,pause)
            self.assertEqual(calls,[])
