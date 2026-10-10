#!/usr/bin/env python3
"""Sign a HAP with the DevEco Studio debug-signing backup.

Complements sign_hap.py (OpenHarmony test credentials) for the Huawei device:
the Pura 70 Ultra trusts Huawei-issued debug profiles, and the DevEco backup
provides three complete suites. It lives outside the repository (keystores are
deliberately not committed) at

    ~/OhmBenchmark-backup/signing-assets/hap-signing-backup/

Each suite is a DevEco automatic-signing export from ~/.ohos/config:
    default_<App>_<hash>.p12   keystore (key alias: debugKey)
    default_<App>_<hash>.cer   certificate chain
    default_<App>_<hash>.p7b   debug profile, bound to one bundle-name and a
                               whitelist of device UDIDs
    default_<App>_<hash>.csr   (only needed for renewal)
    material/                  DevEco's local key material

DevEco stores the p12 passwords as encrypted strings in build-profile.json5.
They are NOT machine-bound: material/ alone decrypts them on any host.
passwords.json (same dir) maps suite -> {keyAlias, keyPassword, storePassword}
holding the *encrypted* hex strings; plaintext is recovered at runtime by
decrypt(), a port of hvigor-ohos-plugin/src/utils/decipher-util.js.

A p7b rejects any HAP whose bundleName differs from its bundle-info, so 'sign'
rewrites the HAP (module.json + pack.info) to the profile's bundle-name when
they differ; the repack is a plain rezip and installs fine.

Usage:
    python3 device-tests/sign_deveco.py suites
    python3 device-tests/sign_deveco.py passwd [--suite NAME]
    python3 device-tests/sign_deveco.py sign IN.hap OUT.hap [--suite NAME]
    python3 device-tests/sign_deveco.py install SIGNED.hap
    python3 device-tests/sign_deveco.py run IN.hap OUT.hap [--suite NAME]
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sign_hap import lib, run  # toolchain discovery + hap-sign-tool driver

BACKUP = Path.home() / 'OhmBenchmark-backup' / 'signing-assets' / 'hap-signing-backup'
# java lives at ~/.local/jre -> ~/.local/bin on this machine; make the script
# work regardless of the caller's PATH
os.environ['PATH'] = str(Path.home() / '.local' / 'bin') + os.pathsep + os.environ['PATH']
# hardcoded component from decipher-util.js
COMPONENT = bytes([49, 243, 9, 115, 214, 175, 91, 184,
                   211, 190, 177, 88, 101, 131, 192, 119])


def _one_file(d):
    fs = [f for f in Path(d).iterdir() if f.name != '.DS_Store']
    if len(fs) != 1:
        sys.exit(f'{d}: expected exactly one material file, found {len(fs)}')
    return fs[0].read_bytes()


def _gcm(key, msg):
    """decipher-util.js decrypt(): |4B content-len|iv|ciphertext|16B tag|"""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    clen = int.from_bytes(msg[:4], 'big')
    ivlen = len(msg) - 4 - clen
    return AESGCM(key).decrypt(msg[4:4 + ivlen], msg[4 + ivlen:], None)


def _work_key():
    mdir = BACKUP / 'material'
    comps = [_one_file(s) for s in (mdir / 'fd').iterdir() if s.name != '.DS_Store']
    comps.append(COMPONENT)
    x = comps[0]
    for c in comps[1:]:
        x = bytes(a ^ b for a, b in zip(x, c))
    # JS feeds Buffer.toString() (lossy utf8) into PBKDF2 -> decode+encode to match
    pw = x.decode('utf-8', errors='replace').encode('utf-8')
    root = hashlib.pbkdf2_hmac('sha256', pw, _one_file(mdir / 'ac'), 10000, 16)
    return _gcm(root, _one_file(mdir / 'ce'))


def decrypt(hex_pwd):
    return _gcm(_work_key(), bytes.fromhex(hex_pwd)).decode('utf-8')


def suites():
    out = {}
    for f in sorted(BACKUP.glob('default_*.*')):
        out.setdefault(f.name.rsplit('.', 1)[0], {})[f.suffix.lstrip('.')] = f
    return out


def _suite(name):
    s = suites()
    if name:
        hits = [k for k in s if name.lower() in k.lower()]
        if len(hits) != 1:
            sys.exit(f'--suite {name!r} matched {hits}')
        return hits[0], s[hits[0]]
    creds = json.loads((BACKUP / 'passwords.json').read_text())
    usable = [k for k in s if k in creds]
    if len(usable) == 1:
        return usable[0], s[usable[0]]
    sys.exit(f'{len(usable)} usable suites {usable}; pass --suite')


def profile_bundle(p7b):
    with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as t:
        run('verify-profile', '-inFile', str(p7b), '-outFile', t.name)
        return json.loads(Path(t.name).read_text())['content']['bundle-info']['bundle-name']


def hap_bundle(hap):
    with zipfile.ZipFile(hap) as z:
        return json.loads(z.read('module.json'))['app']['bundleName']


def repack(inp, outp, bundle):
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        with zipfile.ZipFile(inp) as z:
            names = z.namelist()
            z.extractall(td)
        for name, patch in (('module.json', lambda d: d['app']),
                            ('pack.info', lambda d: d['summary']['app'])):
            f = td / name
            d = json.loads(f.read_text())
            patch(d)['bundleName'] = bundle
            f.write_text(json.dumps(d, separators=(',', ':'), ensure_ascii=False))
        with zipfile.ZipFile(outp, 'w', zipfile.ZIP_DEFLATED) as z:
            for n in names:
                z.writestr(n, b'') if n.endswith('/') else z.write(td / n, n)


def _creds(stem):
    c = json.loads((BACKUP / 'passwords.json').read_text()).get(stem)
    if not c:
        sys.exit(f'no encrypted passwords for {stem} in passwords.json; '
                 'add keyPassword/storePassword from that project\'s build-profile.json5')
    return c.get('keyAlias', 'debugKey'), decrypt(c['keyPassword']), decrypt(c['storePassword'])


def sign(inp, outp, suite_name=None):
    stem, files = _suite(suite_name)
    alias, kp, sp = _creds(stem)
    bundle = profile_bundle(files['p7b'])
    work_in = Path(inp)
    if hap_bundle(inp) != bundle:
        print(f'  repacking: bundleName -> {bundle} (required by the p7b)')
        tmp = Path(tempfile.mkdtemp()) / 'repacked.hap'
        repack(inp, tmp, bundle)
        work_in = tmp
    print('  ' + run('sign-app', '-mode', 'localSign',
                   '-keyAlias', alias, '-keyPwd', kp,
                   '-appCertFile', str(files['cer']),
                   '-profileFile', str(files['p7b']),
                   '-inFile', str(work_in), '-signAlg', 'SHA256withECDSA',
                   '-keystoreFile', str(files['p12']), '-keystorePwd', sp,
                   '-outFile', str(outp)).splitlines()[-1])
    va = tempfile.mkdtemp()
    out = run('verify-app', '-inFile', str(outp),
              '-outCertChain', f'{va}/chain.cer',
              '-outProfile', f'{va}/prof.p7b')
    ok = [l for l in out.splitlines() if 'success' in l.lower()]
    print('  ' + (ok[-1] if ok else out.splitlines()[-1]))
    print(f'  signed -> {outp}')
    return bundle


def install(hap):
    bundle = hap_bundle(hap)
    r = subprocess.run(['hdc', 'install', '-r', str(hap)],
                       capture_output=True, text=True)
    msg = r.stdout + r.stderr
    if 'successfully' in msg:
        print(msg.strip())
        return
    # entry exists under a different signing identity -> clean install
    err = next((l for l in msg.splitlines() if 'error' in l.lower()),
               msg.strip().splitlines()[-1])
    print(f'  replace failed ({err.strip()}); reinstalling {bundle}')
    subprocess.run(['hdc', 'uninstall', bundle], capture_output=True)
    r = subprocess.run(['hdc', 'install', str(hap)], capture_output=True, text=True)
    print((r.stdout + r.stderr).strip())
    if 'successfully' not in r.stdout + r.stderr:
        sys.exit('install failed')


def cmd_suites():
    creds = json.loads((BACKUP / 'passwords.json').read_text())
    for stem, files in suites().items():
        have = 'passwords' if stem in creds else 'NO passwords'
        bundle = profile_bundle(files['p7b']) if 'p7b' in files else '?'
        print(f'{stem}\n    bundle={bundle}  [{have}]')


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    sub.add_parser('suites')
    p = sub.add_parser('passwd'); p.add_argument('--suite')
    s = sub.add_parser('sign')
    s.add_argument('input_hap'); s.add_argument('output_hap'); s.add_argument('--suite')
    i = sub.add_parser('install'); i.add_argument('hap')
    r = sub.add_parser('run')
    r.add_argument('input_hap'); r.add_argument('output_hap'); r.add_argument('--suite')
    a = ap.parse_args()
    if a.cmd == 'suites':
        cmd_suites()
    elif a.cmd == 'passwd':
        stem, _ = _suite(a.suite)
        alias, kp, sp = _creds(stem)
        print(f'{stem}\n  keyAlias={alias} keyPassword={kp} storePassword={sp}')
    elif a.cmd == 'sign':
        sign(a.input_hap, a.output_hap, a.suite)
    elif a.cmd == 'install':
        install(a.hap)
    else:
        sign(a.input_hap, a.output_hap, a.suite)
        install(a.output_hap)
    return 0


if __name__ == '__main__':
    sys.exit(main())
