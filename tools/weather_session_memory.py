"""Recheck ordinary forecast work and observed kernel PSS growth windows."""
import hashlib,json,math,statistics
from collections import Counter
from pathlib import Path
from urllib.parse import parse_qs,urlsplit
from system_pss import pss_bytes,start_ticks,verify_window
from weather_icon_pixels import icon_boxes
from weather_session_data_service import CITIES,response
BUNDLE='com.alatus.futureweather'
MIB=1024*1024

def growth_bounds(before,after):
    if len(before)!=3 or len(after)!=3 or any(type(x) is not int or x<=0 for x in [*before,*after]):raise ValueError('three positive kernel totals per observation window are required')
    return {'lower_bytes':min(after)-max(before),'upper_bytes':max(after)-min(before),'median_bytes':statistics.median(after)-statistics.median(before)}

def gate(unfixed,fixed):
    lower=unfixed['lower_bytes'];upper=fixed['upper_bytes'];denominator=max(upper,MIB)
    return {'passed':lower>=5*MIB and lower>=3*denominator and lower-upper>=5*MIB,'noise_bounded_ratio':lower/denominator,'excess_growth_bytes':lower-upper,'fixed_denominator_bytes':denominator}

def verify_extra(sample,pid,ticks):
    if sample['pid']!=pid or sample['bundle']!=BUNDLE or sample['process_start_ticks']!=ticks:raise ValueError('extra PSS sample process differs')
    for key in ('raw_cmdline_before','raw_cmdline_after'):
        if sample[key].split('\0',1)[0].strip()!=BUNDLE:raise ValueError('extra kernel sample belongs to another app')
    for key in ('raw_stat_before','raw_stat_after'):
        if start_ticks(sample[key],pid)!=ticks:raise ValueError('process restarted during growth observations')
    if sample['pss_bytes']!=pss_bytes(sample['raw_smaps_rollup']) or sample['pss_bytes']<=0:raise ValueError('growth sample differs from raw kernel total')
    if not all(math.isfinite(sample[k]) for k in ('read_start_monotonic','monotonic')) or not 0<sample['read_start_monotonic']<=sample['monotonic']:raise ValueError('invalid kernel observation interval')

def verify_requests(record,count=15):
    counts=Counter()
    for row in record['requests']:
        if not record['action_start_monotonic']<=row['start']<=row['end']<=record['action_end_monotonic']:raise ValueError('forecast request outside ordinary measured work')
        status,body=response(row['path'])
        if status!=200 or row['status']!=200 or row['error'] is not None or row['body_bytes']!=len(body) or row['sent_bytes']!=len(body) or row['body_sha256']!=hashlib.sha256(body).hexdigest():raise ValueError('forecast response incomplete or changed')
        query=parse_qs(urlsplit(row['path']).query);counts[query['city'][0]]+=1
    if dict(counts)!={city:count for city in CITIES}:raise ValueError('complete declared ten-city refreshes are required')
    return dict(counts)

def verify_capture(record,folder):
    revision=record.get('measurement_revision')
    if revision not in ('growth-v4','growth-v5'):raise ValueError('unknown prospective memory contract')
    count=15 if revision=='growth-v4' else 60
    contract_path=Path(__file__).resolve().parents[1]/('validation/weather-sessions-'+revision+'-contract.json')
    if hashlib.sha256(contract_path.read_bytes()).hexdigest()!=record.get('contract_sha256'):
        raise ValueError('prospective memory contract differs from captured bytes')
    contract=json.loads(contract_path.read_text())
    expected={'measurement_revision':revision,'warmup_returns':10,'measured_returns':count,
              'required_successful_forecasts_per_trial':10*count,'paired_rounds':3,
              'required_ratio_each_pair_and_median':3.0,'fixed_growth_denominator_floor_bytes':MIB,
              'minimum_unfixed_lower_growth_bytes':5*MIB,'minimum_excess_growth_bytes':5*MIB}
    if any(contract.get(k)!=v for k,v in expected.items()):raise ValueError('frozen memory gate changed')
    if record.get('status')!='CAPTURED' or record.get('warmup_count')!=10 or len(record['steps'])!=count:raise ValueError('incomplete warmed refresh trial')
    verify_window(record,BUNDLE);baseline=record['baseline_samples'];post=record['post_samples'];window=record['snapshots'];pid=window[0]['pid'];ticks=window[0]['process_start_ticks']
    if len(baseline)!=3 or len(post)!=3 or window[0]!=baseline[-1] or window[-1]!=post[-1]:raise ValueError('growth windows are not bound to native periodic samples')
    previous=0
    for sample in [*baseline,*window[1:-1],*post]:
        verify_extra(sample,pid,ticks)
        if sample['read_start_monotonic']<previous:raise ValueError('kernel observations overlap')
        previous=sample['monotonic']
    if any(s['phase']!='before' or s['monotonic']>record['action_start_monotonic'] for s in baseline) or any(s['phase']!='after' or s['read_start_monotonic']<record['action_end_monotonic'] for s in post):raise ValueError('growth observations do not bracket the work')
    bounds=growth_bounds([s['pss_bytes'] for s in baseline],[s['pss_bytes'] for s in post])
    if bounds!=record['growth_bounds']:raise ValueError('growth summary differs from original kernel totals')
    icon_boxes(record['initial_layout'])
    for number,step in enumerate(record['steps'],1):
        if step['number']!=number:raise ValueError('native refresh step order differs')
        icon_boxes(step['layout'])
    verify_requests(record,count)
    if record['fixture_before']!=record['fixture_after'] or json.loads((Path(folder)/'fixture-before.json').read_text())!=record['fixture_before']:raise ValueError('ordinary forecast service changed')
    root=Path(__file__).resolve().parent
    for field,name in (('source','weather_session_data_service.py'),('launcher','weather_session_workstation_lease.py')):
        if hashlib.sha256((root/name).read_bytes()).hexdigest()!=record['fixture_before'][field+'_sha256']:raise ValueError('ordinary source differs from recorded instance')
    return bounds
