import copy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from export_agent_data import require_accepted_case


class AgentExportAcceptanceTest(unittest.TestCase):
    def setUp(self):
        self.case={'test_oracle':{'metric':'hiperf_instructions','evidence':{
            'status':'measured_clean','unfixed':[200]*3,'fixed':[100]*3}}}
        self.results={v:{'status':'PASS','rounds':3,'metric':'hiperf_instructions','samples':[n]*3}
                      for v,n in [('unfixed',200),('fixed',100)]}

    def test_full_evidence_is_recomputed_readonly_before_export(self):
        original=copy.deepcopy(self.case)
        with patch('export_agent_data.validate_cpu',return_value=self.results) as validate:
            require_accepted_case('case',self.case,1)
        validate.assert_called_once_with('case',write=False)
        self.assertEqual(self.case,original)

    def test_pending_negative_and_user_skips_are_excluded_before_raw_processing(self):
        for status in ('pending_clean_measurement','measured_clean_failed','negative_screen_failed'):
            case=copy.deepcopy(self.case);case['test_oracle']['evidence']['status']=status
            with self.subTest(status=status),patch('export_agent_data.validate_cpu') as validate:
                with self.assertRaisesRegex(ValueError,'pending and negative'):require_accepted_case('case',case,1)
                validate.assert_not_called()
        case=copy.deepcopy(self.case);case['disposition']={'status':'skipped_by_user'}
        with self.assertRaises(ValueError):require_accepted_case('case',case,1)

    def test_partial_positive_flags_or_metadata_not_matching_raw_cannot_authorize_export(self):
        for kind in ('partial','failure','wrong-metric','wrong-case-summary'):
            result=copy.deepcopy(self.results);case=copy.deepcopy(self.case)
            if kind=='partial':result['unfixed'].update(rounds=1,samples=[200])
            if kind=='failure':result['unfixed']['status']='FAIL'
            if kind=='wrong-metric':result['fixed']['metric']='trace_cpu_ms'
            if kind=='wrong-case-summary':case['test_oracle']['evidence']['fixed']=[1]*3
            with self.subTest(kind=kind),patch('export_agent_data.validate_cpu',return_value=result),self.assertRaises(ValueError):
                require_accepted_case('case',case,1)

    def test_round_outside_the_accepted_set_cannot_be_selected(self):
        for number in (0,4,True):
            with self.subTest(number=number),self.assertRaises(ValueError):require_accepted_case('case',self.case,number)

    def test_trace_and_memory_use_their_full_raw_validators(self):
        for metric,validator in [('trace_cpu_ms','validate_trace'),('app_pss_bytes','validate_pss')]:
            case=copy.deepcopy(self.case);case['test_oracle']['metric']=metric
            result=copy.deepcopy(self.results)
            for row in result.values():row['metric']=metric
            with self.subTest(metric=metric),patch('export_agent_data.'+validator,return_value=result) as validate:
                require_accepted_case('case',case,3)
                validate.assert_called_once_with('case',write=False)
