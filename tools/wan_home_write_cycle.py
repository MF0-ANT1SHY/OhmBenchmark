"""External collection of real Wan load-more cycles; never accepts performance."""
import hashlib
import json
from pathlib import Path
import subprocess
import time
import urllib.request
import xml.etree.ElementTree as ET

from audit_wan_home_primary import network_progress
from native_hilog import snapshot as logs
from native_file_trace import record
from system_pss import start_ticks
from ui_driver import UI
from wan_html_inputs import transformed

BUNDLE='org.example.wan.ohos'
PREFERENCES='/data/app/el2/100/base/'+BUNDLE+'/haps/entry/files/persistent_storage'


def verify_backend_page(data,page):
    payload=data.get('data') or {}
    rows=payload.get('datas')
    if (data.get('errorCode')!=0 or payload.get('curPage')!=page+1 or payload.get('size')!=10
            or not isinstance(rows,list) or not 1<=len(rows)<=10):
        raise ValueError('successful normal page with requested size 10 and nonempty actual rows required')
    ids=[row.get('id') for row in rows]
    if any(type(i) is not int or i<=0 for i in ids) or len(set(ids))!=len(ids):
        raise ValueError('normal public article identities are invalid')
    return transformed(rows)


def backend(page, directory):
    url=f'https://www.wanandroid.com/article/list/{page}/json?page={page}&page_size=10'
    with urllib.request.urlopen(url,timeout=30) as response:
        raw=response.read()
        if response.status!=200:raise ValueError('public backend HTTP request failed')
    path=Path(directory)/'backend.json';path.write_bytes(raw);path.chmod(0o600)
    data=json.loads(raw)
    rows=verify_backend_page(data,page)
    return {'url':url,'sha256':hashlib.sha256(raw).hexdigest(),'rows':rows,
            'requested_page_size':10,'actual_articles':len(rows)}


def observe(ui,directory,label):
    directory=Path(directory)
    pid=ui.shell('pidof '+BUNDLE).strip()
    if not pid.isdigit():raise ValueError('one live Wan process required')
    stat=ui.shell('cat /proc/'+pid+'/stat')
    identity=ui.shell("stat -c '%d %i %s %u %g %a %n' "+PREFERENCES).strip()
    raw=subprocess.run(['hdc','shell','cat '+PREFERENCES],capture_output=True,timeout=60)
    if raw.returncode:raise ValueError('native preference read failed')
    after=ui.shell("stat -c '%d %i %s %u %g %a %n' "+PREFERENCES).strip()
    if identity!=after or len(raw.stdout)!=int(identity.split()[2]):
        raise ValueError('native preference file changed during its observation')
    path=directory/(label+'.preferences.bin');path.write_bytes(raw.stdout);path.chmod(0o600)
    nodes={n.attrib.get('key'):n.text for n in ET.fromstring(raw.stdout)}
    receipt=logs(int(pid),directory/'native-logs',label)
    final=ui.shell('cat /proc/'+pid+'/stat')
    if start_ticks(stat,int(pid))!=start_ticks(final,int(pid)):raise ValueError('Wan process changed during observation')
    return {'pid':int(pid),'stat':stat,'stat_after':final,'file_identity':identity,
            'preferences_file':str(path),'preferences_sha256':hashlib.sha256(raw.stdout).hexdigest(),
            'ids':{key:[row['id'] for row in json.loads(nodes[key])] for key in ('homeList','homeListCache') if key in nodes},
            'native_log_receipt':receipt,'observed_monotonic':time.monotonic()}


def collect(ui, directory, page, variant):
    if variant not in ('unfixed','fixed') or type(page) is not int or not 1<=page<=10:
        raise ValueError('original ten sequential normal load-more pages required')
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=False,mode=0o700)
    result={'status':'FAIL','page':page,'variant':variant,'app_injection':False,'performance_accepted':False}
    last=None
    try:
        source=backend(page,directory);result['backend']=source
        before=observe(ui,directory,'before');result['before']=before
        def action():
            nonlocal last
            deadline=time.monotonic()+180
            swipes=0;requested=False
            while time.monotonic()<deadline:
                if not requested:
                    if swipes==8:break
                    ui.run([{'op':'swipe','count':1}]);swipes+=1
                else:time.sleep(1)
                last=observe(ui,directory,'step-'+str(time.time_ns()))
                raw=last['native_log_receipt']['raw_logs']
                requested=('get: '+source['url']) in raw
                try:
                    progress=network_progress(before['native_log_receipt']['raw_logs'],raw,before['pid'],first_page=page)
                except ValueError:
                    continue
                if progress['requested_pages']!=[page]:raise ValueError('cycle contains a different number of normal pages')
                if last['pid']!=before['pid'] or start_ticks(last['stat'],last['pid'])!=start_ticks(before['stat'],before['pid']):
                    raise ValueError('normal load-more process changed')
                ids=[row['id'] for row in source['rows']]
                if variant=='unfixed':
                    if last['ids']['homeList']!=before['ids']['homeList']+ids:
                        continue
                elif last['ids']['homeListCache']!=before['ids']['homeListCache']:
                    raise ValueError('fixed first-page cache changed during load-more')
                layout=ui.layout()
                texts={n.get('text') for n in UI.nodes(layout) if n.get('bundleName')==BUNDLE}
                visible=[row['id'] for row in source['rows'] if row['title'] in texts]
                if not visible:
                    # One ordinary scroll exposes the newly appended page.
                    # A final network check rejects accidentally loading more.
                    ui.run([{'op':'swipe','count':1}]);swipes+=1;layout=ui.layout()
                    texts={n.get('text') for n in UI.nodes(layout) if n.get('bundleName')==BUNDLE}
                    visible=[row['id'] for row in source['rows'] if row['title'] in texts]
                if not visible:raise ValueError('new real backend page is not visible')
                final=observe(ui,directory,'after')
                if network_progress(before['native_log_receipt']['raw_logs'],final['native_log_receipt']['raw_logs'],before['pid'],first_page=page)!=progress:
                    raise ValueError('viewport verification loaded an extra page')
                return {'after':final,'progress':progress,'layout_after':layout,'visible_new_ids':visible,'swipes':swipes}
            exc=ValueError('normal next-page request did not complete within the bounded UI cycle')
            exc.observation=last
            raise exc
        capture=record(ui.shell,action,directory/'capture')
        result['capture']=capture
        if capture['status']!='NATIVE_FILE_TRACE_CAPTURED':raise ValueError(capture.get('error','native capture failed'))
        result['status']='ONE_NORMAL_PAGE_NATIVE_FILE_TRACE_CAPTURED_AUDIT_PENDING'
    except Exception as exc:
        result['error']=str(exc)
        if last is not None:result['last_observation']=last
        try:result['failure_layout']=ui.layout()
        except Exception:pass
    (directory/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    (directory/'result.json').chmod(0o600)
    return result
