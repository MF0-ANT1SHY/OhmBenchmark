#!/usr/bin/env python3
"""Prepare ordinary InterviewApp preferences for an identical search history.

The two production versions use different storage representations. These files
represent their state after the same sequence of normal search submissions;
they do not add counters, app hooks, schema fields or diagnostic values.
Device installation and real UI verification are separate steps.
"""
import argparse
import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path


def preferences_bytes(values):
    root=ET.Element('preferences')
    for key,value in values.items():
        ET.SubElement(root,'string',key=key).text=value
    return ET.tostring(root,encoding='utf-8',xml_declaration=True)


def production_states(submissions):
    unlimited={}
    recent=[]
    for keyword in submissions:
        if not isinstance(keyword,str) or not keyword or len(keyword.encode())>1024:
            raise ValueError('invalid ordinary search keyword')
        unlimited[keyword]=keyword
        recent=[keyword]+[old for old in recent if old!=keyword]
        recent=recent[:20]
    return {'unfixed':preferences_bytes(unlimited),
            'fixed':preferences_bytes({'keywords':json.dumps(recent,ensure_ascii=False)})}


def seed(destination,count=1000):
    if count<1:
        raise ValueError('history must contain submissions')
    if destination.exists():
        raise FileExistsError('fixture destination must be fresh')
    submissions=[f'面试题 {i}' for i in range(1,count+1)]
    identity=json.dumps(submissions,ensure_ascii=False,separators=(',',':')).encode()
    states=production_states(submissions)
    destination.mkdir(parents=True)
    (destination/'submissions.json').write_bytes(identity)
    variants={}
    for variant,blob in states.items():
        (destination/f'{variant}.xml').write_bytes(blob)
        variants[variant]={'file':f'{variant}.xml','sha256':hashlib.sha256(blob).hexdigest()}
    receipt={'fixture_sha256':hashlib.sha256(identity).hexdigest(),
             'submissions':count,'variants':variants,
             'format_source':'https://github.com/openharmony/distributeddatamgr_preferences/blob/OpenHarmony-v5.1.0-Release/frameworks/native/src/preferences_xml_utils.cpp',
             'storage_name':'historyStore','bundle':'com.itcast.pass_interview',
             'derivation':'ordinary production state after identical search submissions; fixed keeps the latest 20',
             'device_validation':'pending','performance_verified':False}
    (destination/'fixture.json').write_text(json.dumps(receipt,indent=2)+'\n')
    return receipt


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination',type=Path)
    parser.add_argument('--count',type=int,default=1000)
    args=parser.parse_args()
    print(json.dumps(seed(args.destination,args.count),indent=2))
