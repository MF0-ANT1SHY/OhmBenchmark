"""Identify actual ordinary font assets in an audited production HAP."""
import hashlib
import json
import zipfile

from bundled_audio_fixture import audited_hap


def identify(hap):
    fonts={}
    with zipfile.ZipFile(hap) as archive:
        names=archive.namelist()
        if len(names)!=len(set(names)):
            raise ValueError('duplicate package entries')
        for name in sorted(names):
            if not name.startswith('resources/rawfile/') or not name.lower().endswith(('.ttf','.otf')):
                continue
            blob=archive.read(name)
            if blob[:4] not in (b'\x00\x01\x00\x00',b'OTTO',b'true',b'typ1'):
                raise ValueError('packaged font has an invalid font header')
            fonts[name]=hashlib.sha256(blob).hexdigest()
    required={'resources/rawfile/iconfont.ttf','resources/rawfile/DINCOROS-Regular.ttf'}
    if not required.issubset(fonts):
        raise ValueError('fonts used by the normal MainPage are missing')
    identity=hashlib.sha256(json.dumps(fonts,sort_keys=True).encode()).hexdigest()
    return {'kind':'bundled business fonts','sha256':identity,'fonts':fonts,
            'registered_font_paths':sorted(required)}


def for_case(root,case,variant,sign):
    if case['id']!='sepweather_font_register_per_page':
        raise ValueError('bundled font fixture supports the actual SepWeather font case only')
    return identify(audited_hap(root,case,variant,sign))
