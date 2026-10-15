"""Observe normal Interview search-history persistence outside the app."""
import hashlib
import time
import xml.etree.ElementTree as ET

from system_pss import start_ticks

BUNDLE = 'com.itcast.pass_interview'
PREFERENCES = '/data/app/el2/100/base/'+BUNDLE+'/haps/phone/preferences/historyStore'


def keywords(raw):
    root=ET.fromstring(raw)
    if root.tag!='preferences' or root.attrib not in ({}, {'version':'1.0'}):
        raise ValueError('not a plain native history preference document')
    result=[]
    for child in root:
        if child.tag!='string' or set(child.attrib)!={'key'} or child.attrib['key']!=child.text or len(child):
            raise ValueError('unexpected data in dedicated history preferences')
        result.append(child.attrib['key'])
    if len(set(result))!=len(result):
        raise ValueError('duplicate history preference keys')
    return result


def empty_preferences(raw):
    keywords(raw)
    root=ET.fromstring(raw)
    for child in list(root):
        root.remove(child)
    return ET.tostring(root,encoding='utf-8',xml_declaration=True)


def read_state(shell):
    start=time.monotonic();pid=shell('pidof '+BUNDLE).strip()
    if not pid.isdigit():raise ValueError('one live Interview app process is required')
    stat=shell('cat /proc/'+pid+'/stat');command=shell('cat /proc/'+pid+'/cmdline')
    raw=shell('cat '+PREFERENCES);after=shell('cat /proc/'+pid+'/stat')
    if command.split('\x00',1)[0].strip()!=BUNDLE or start_ticks(stat,int(pid))!=start_ticks(after,int(pid)):
        raise ValueError('history observation process identity changed')
    return {'pid':int(pid),'raw_stat':stat,'raw_stat_after':after,'raw_cmdline':command,
            'raw_preferences':raw,'started_monotonic':start,'ended_monotonic':time.monotonic()}


def verify_observation(before,after,values):
    if (not isinstance(values,list) or not values or len(set(values))!=len(values) or
            any(not isinstance(value,str) or not value for value in values)):
        raise ValueError('distinct expected history submissions required')
    identities=[]
    for state in (before,after):
        pid=state['pid'];ticks=start_ticks(state['raw_stat'],pid)
        if (state['raw_cmdline'].split('\x00',1)[0].strip()!=BUNDLE or
                ticks!=start_ticks(state['raw_stat_after'],pid) or
                not 0 < state['started_monotonic'] <= state['ended_monotonic']):
            raise ValueError('invalid history process observation')
        identities.append((pid,ticks))
    if identities[0]!=identities[1] or before['ended_monotonic']>=after['started_monotonic']:
        raise ValueError('history observations do not bracket one process')
    if keywords(before['raw_preferences']) or set(keywords(after['raw_preferences']))!=set(values):
        raise ValueError('empty-to-exact-submissions history persistence is not proven')
    return {'persisted_keywords':len(values),'final_preferences_sha256':hashlib.sha256(after['raw_preferences'].encode()).hexdigest(),
            'method':'existing dedicated native preferences; no app instrumentation',
            'individual_flush_count_verified':False}


def verify_capture(observation,start,end,pids):
    values=observation['values']
    if values!=['question'+str(i) for i in range(20)]:
        raise ValueError('original twenty distinct search queries are required')
    result=verify_observation(observation['before'],observation['after'],values)
    if (pids!=[observation['before']['pid']] or not 0<start<end or
            observation['before']['ended_monotonic']>start or
            observation['after']['started_monotonic']<start or observation['after']['ended_monotonic']>end or
            observation.get('progress')!=result):
        raise ValueError('real history updates were not verified inside the CPU capture')
    return result
