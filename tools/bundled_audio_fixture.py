"""Identify ordinary playable audio packaged in the actual clean HAP."""
import hashlib
import json
import zipfile


def identify(hap):
    files={}
    with zipfile.ZipFile(hap) as archive:
        names=archive.namelist()
        if len(names)!=len(set(names)):
            raise ValueError('ambiguous duplicate package entries')
        for name in sorted(names):
            if not name.startswith('resources/rawfile/audio/') or name.endswith('/'):
                continue
            if name.lower().rsplit('.',1)[-1] not in ('mp3','wav','flac','m4a','ogg'):
                continue
            digest=hashlib.sha256()
            with archive.open(name) as stream:
                while block:=stream.read(1024*1024):digest.update(block)
            files[name]=digest.hexdigest()
    if not files:
        raise ValueError('no bundled business audio found')
    digest=hashlib.sha256(json.dumps(files,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    return {'kind':'bundled business audio','sha256':digest,'audio_files':len(files)}


def for_case(root,case,variant,sign):
    if case['id']!='ytmusic_current_playing_timeupdate':
        raise ValueError('bundled audio fixture currently supports the actual YTMusic playback case only')
    folder=root/'artifacts/clean'/case['id']/variant
    build=json.loads((folder/'build.json').read_text())
    if sign['status']!='PASS' or not sign['audit']['passed'] or build['status']!='PASS' or not build['hap']['passed'] or sign['unsigned_sha256']!=build['hap']['sha256']:
        raise ValueError('audio package provenance does not match the signed build')
    hap=folder/'app-unsigned.hap'
    digest=hashlib.sha256()
    with hap.open('rb') as stream:
        while block:=stream.read(1024*1024):digest.update(block)
    if digest.hexdigest()!=build['hap']['sha256']:
        raise ValueError('audio package changed since build audit')
    return identify(hap)
