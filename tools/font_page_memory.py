"""Validate real city-manager pages, immutable fonts, and native PSS samples."""
import hashlib,json,re
from pathlib import Path
from ui_driver import UI
from system_pss import verify_window
from weather_icon_pixels import region_hashes
BUNDLE='cn.seayj.sepweather'

def page_content(layout):
    nodes=[n for n in UI.nodes(layout) if n.get('bundleName')==BUNDLE and n.get('visible')!='false']
    titles=[n for n in nodes if n.get('text')=='城市管理']
    texts=sorted({n.get('text') for n in nodes if n.get('text')})
    if len(titles)!=1 or '北京' not in texts or '\ue66a' not in texts:raise ValueError('ordinary city-manager content missing')
    return {'texts':texts,'title_box':list(map(int,re.findall(r'-?\d+',titles[0]['bounds'])))}

def verify_capture(record,folder,reference):
    if record.get('status')!='CAPTURED' or record['warmup_count']!=1 or len(record['steps'])!=40:raise ValueError('forty normal page visits after warmup are required')
    value=verify_window(record,BUNDLE);content=reference['page_content']
    for number,row in enumerate(record['steps'],1):
        if row['number']!=number or page_content(row['layout'])!=content:raise ValueError('ordinary city content changed between page visits')
    if {f['step'] for f in record['frames']}!={1,40}:raise ValueError('first and last native title frames required')
    for frame in record['frames']:
        path=Path(folder)/frame['file']
        if path.parent!=Path(folder) or hashlib.sha256(path.read_bytes()).hexdigest()!=frame['sha256']:raise ValueError('original title screenshot changed')
        if region_hashes(path,[content['title_box']])!=reference['title_pixels']:raise ValueError('native title pixels differ from the verified CJK font rendering')
    nodes=list(UI.nodes(record['final_layout']))
    if not any(n.get('id')=='AddAddressBtn' and n.get('bundleName')==BUNDLE and n.get('visible')!='false' for n in nodes):raise ValueError('normal return to the main page missing')
    return value
