"""Read-only necessary-condition rejection of native whole-file write traffic.

An early rejection cannot accept performance, erase passing PSS measurements,
or claim exclusive attribution to one key in the shared preferences file.
"""
import argparse
import json
from pathlib import Path

from audit_wan_home_primary import audit as primary_audit
from audit_wan_home_write_pages import audit as file_audit


def upper_bound(unfixed_bytes,fixed_prefix_bytes,unfixed_pages,fixed_pages):
    if (any(type(v) is not int for v in (unfixed_bytes,fixed_prefix_bytes,unfixed_pages,fixed_pages))
            or unfixed_pages!=10 or not 1<=fixed_pages<=10 or unfixed_bytes<=0 or fixed_prefix_bytes<=0):
        raise ValueError('complete unfixed ten pages and positive verified fixed prefix required')
    if unfixed_bytes>=3*fixed_prefix_bytes:
        raise ValueError('necessary threefold criterion has not been disproven; continue original work')
    return {'unfixed_complete_ten_page_bytes':unfixed_bytes,'fixed_verified_prefix_bytes':fixed_prefix_bytes,
            'unfixed_pages_completed':unfixed_pages,'fixed_prefix_pages_completed':fixed_pages,
            'remaining_fixed_bytes_lower_bound':0,'maximum_possible_unfixed_to_fixed_ratio':unfixed_bytes/fixed_prefix_bytes,
            'required_ratio':3,'necessary_criterion_failed':True,
            'reason':'Any complete valid fixed ten-page run includes this nonnegative prefix. Even zero bytes on every remaining fixed page cannot reach 3x.'}


def screen(path):
    result=file_audit(path,require_complete=False)
    if set(result['variants'])!={'unfixed','fixed'}:raise ValueError('both real variants required')
    u,f=(result['variants'][name] for name in ('unfixed','fixed'))
    if not u['endpoint_inode_traffic_complete'] or not f['endpoint_inode_traffic_complete']:
        raise ValueError('unbound persistent-file versions prevent a necessary-condition decision')
    if [p['backend_sha256'] for p in u['pages'][:len(f['pages'])]]!=[p['backend_sha256'] for p in f['pages']]:
        raise ValueError('the original verified fixed prefix used different backend inputs')
    bound=upper_bound(u['file_returned_bytes'],f['file_returned_bytes'],len(u['pages']),len(f['pages']))
    primary=primary_audit(3)
    if not primary['primary_criterion_met']:raise ValueError('preserve/reconcile the original primary result before disposition')
    case=json.loads(Path('cases/wanharmony_persisted_home_list_growth/case.json').read_text())
    mechanism=case['test_oracle']['mechanism_oracle']
    if mechanism['metric']!='persistent_write_bytes_per_loadmore' or '>= 3x' not in mechanism['comparison']:
        raise ValueError('the declared native-write criterion changed')
    return {'case':case['id'],'status':'NECESSARY_NATIVE_FILE_WRITE_CRITERION_FAILED',
            'performance_accepted':False,'primary_pss_criterion_met':True,'primary_paired_rounds':3,
            'primary_samples':primary['samples'],'primary_paired_ratios':primary['paired_ratios'],
            'declared_mechanism_criterion':mechanism,'negative_bound':bound,'file_audit':result,
            'full_fixed_ten_page_run_completed':len(f['pages'])==10,
            'exclusive_home_list_bytes_verified':False,'app_writer_thread_attribution_claimed':False,
            'measurement_scope':'Actual complete persistent_storage file write returns in normal home load-more cycles; shared cookie/inactive-cache traffic is retained, not subtracted or estimated.',
            'legacy_instrumented_counters_reused':False}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('proof',type=Path);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    if args.output.exists():raise FileExistsError('preserve previous mechanism evidence')
    result=screen(args.proof);args.output.write_text(json.dumps(result,indent=2)+'\n');print(result['status'],result['negative_bound']['maximum_possible_unfixed_to_fixed_ratio'])
