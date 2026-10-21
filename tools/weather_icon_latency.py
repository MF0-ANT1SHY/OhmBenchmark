"""Recompute conservative complete-icon latency from original native frames."""
import hashlib
from pathlib import Path
from urllib.parse import parse_qs,urlsplit
from weather_icon_pixels import matches,icon_boxes,BUNDLE
from weather_service_fixture import same_instance


def bounds_from_frames(record):
    start=record['launch_start'];frames=record['frames'];baseline=record['baseline']
    if (not 0<baseline['start']<=baseline['end']<start<=record['launch_command_end']
            or baseline['ready'] or not frames or not frames[-1]['ready']
            or any(f['ready'] for f in frames[:-1])):
        raise ValueError('complete-icon transition is not observed')
    previous=record['launch_command_end']
    for frame in frames:
        if not previous<=frame['start']<=frame['end']:raise ValueError('native frame times overlap or precede launch')
        previous=frame['end']
    return {'lower_s':max(0,frames[-2]['start']-start) if len(frames)>1 else 0,
            'upper_s':frames[-1]['end']-start}


def verify_requests(record):
    forecasts=[];icons=[]
    for request in record['requests']:
        p=urlsplit(request['path']);q=parse_qs(p.query)
        if not record['launch_start']<=request['start']<=request['end']<=record['action_end_monotonic']:
            raise ValueError('ordinary request lies outside the business action')
        if p.path=='/v3/weather/weatherInfo':
            if q.get('extensions')!=['all']:raise ValueError('forecast type differs')
            forecasts.append(q.get('city'))
        elif p.path.startswith('/weather/'):
            if request['end']-request['start']<4.0:raise ValueError('declared image response delay not present')
            icons.append(p.path)
        else:raise ValueError('unrelated request in the ordinary launch')
    if sorted(forecasts)!=[['440100'],['440300']]:raise ValueError('both ordinary city forecasts are required')
    expected=['/weather/'+n+'.img' for n in ('sunny','cloudy','overcast','rain')]
    if (record['variant']=='unfixed' and sorted(icons)!=sorted(expected)) or (record['variant']=='fixed' and icons):
        raise ValueError('native cold launch did not use the expected image source')


def verify_capture(record,folder,reference):
    from scheduler_cpu import compute,window_from_markers
    folder=Path(folder)
    if record.get('status')!='CAPTURED' or record['variant'] not in ('unfixed','fixed'):
        raise ValueError('incomplete native icon capture')
    for frame in [record['baseline'],*record['frames']]:
        path=folder/frame['file']
        if path.parent!=folder or hashlib.sha256(path.read_bytes()).hexdigest()!=frame['sha256']:
            raise ValueError('original native screenshot changed')
        if matches(path,reference)!=frame['ready']:raise ValueError('icon readiness differs from original pixels')
    if icon_boxes(record['layout'])!=reference['boxes']:raise ValueError('forecast or icon layout changed')
    bounds=bounds_from_frames(record)
    if bounds!=record['latency_bounds']:raise ValueError('latency summary differs from original frames')
    before,after=record['process_before'],record['process_after']
    if (before!=after or record['pids']!=[before['pid']] or before['start_ticks']<=0
            or before['command'].split('\0',1)[0].strip()!=BUNDLE):raise ValueError('native application identity differs')
    if (record['online_cpus_before']!=record['online_cpus_after'] or record['clock_before']!=record['clock_after']
            or '[boot]' not in record['clock_before'] or record['buffer_size_kb_before']!=record['buffer_size_kb_after']):
        raise ValueError('native diagnostic conditions changed')
    if (record['action_start_monotonic']!=record['launch_start']
            or record['action_end_monotonic']<record['frames'][-1]['end']
            or 'success' not in record['cache_cleanup'].lower()):raise ValueError('complete cold-launch window is not proven')
    if record.get('fixture_before_anchor'):
        import json
        link=record['fixture_before_anchor'];path=Path(link['capture'])
        if hashlib.sha256(path.read_bytes()).hexdigest()!=link['sha256'] or link['field']!='fixture_after':
            raise ValueError('continuous service anchor changed')
        prior=json.loads(path.read_text())
        if prior['action_end_monotonic']>=record['launch_start'] or prior['fixture_after']!=record['fixture_before']:
            raise ValueError('service anchor does not precede this action')
        original=folder/'native-capture-original.json'
        if hashlib.sha256(original.read_bytes()).hexdigest()!=record['recovery']['native_original_sha256']:
            raise ValueError('recovered original native receipt changed')
        if any(record.get(k)!=v for k,v in json.loads(original.read_text()).items()):
            raise ValueError('recovery changed original native evidence')
    elif (folder/'fixture-before.json').exists():
        import json
        if json.loads((folder/'fixture-before.json').read_text())!=record['fixture_before']:
            raise ValueError('persisted before-capture service check differs')
    same_instance(record['fixture_before'],record['fixture_after'])
    if record['fixture_before']['icon_delay_s']!=4.0:raise ValueError('declared network condition changed')
    verify_requests(record)
    trace=folder/'trace.htrace';start,end=window_from_markers(trace,record['marker_token'],record['pids'])
    raw=compute(trace,record['pids'],start,end,record['online_cpus_before'])
    if raw!=record['scheduler_cpu'] or (end-start)/1e9<record['action_end_monotonic']-record['launch_start']:
        raise ValueError('native diagnostic trace does not enclose the complete action')
    return bounds,raw
