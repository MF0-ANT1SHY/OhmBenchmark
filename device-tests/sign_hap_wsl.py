#!/usr/bin/env python3
"""Sign a HAP for the test device using the OpenHarmony SDK test credentials.

The original recipe (device-tests/sign.ps1) referenced a per-user workspace holding
dev.p12 / chain.cer / browser.json. That account and those files do not exist on this
machine, so this script rebuilds the equivalent from the SDK material that IS present:

    $LIB/OpenHarmony.p12                 SDK test keystore, password 123456
    $LIB/OpenHarmonyProfileDebug.pem     profile-signing certificate
    $LIB/UnsgnedDebugProfileTemplate.json

The four documented steps (see the OpenHarmony hapsigner guide):

  1. generate-keypair   - an app signing key, stored in a PRIVATE COPY of the keystore
  2. generate-app-cert  - that key's cert chain, issued by the keystore's intermediate CA
  3. sign-profile       - the debug profile, pointed at the bundle and this device's UDID,
                          embedding the app signing certificate
  4. sign-app           - sign the unsigned HAP

`prepare` (steps 1-2) only needs running once; its output is cached under
~/.local/ohsign. Subsequent runs reuse it, so signing a HAP is steps 3-4 only.

Usage:
    python3 device-tests/sign_hap_wsl.py prepare
    python3 device-tests/sign_hap_wsl.py sign UNSIGNED.hap SIGNED.hap BUNDLE
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

SDK_LIB = Path('/mnt/c/Users/research/hdc/lib')
WORK = Path.home() / '.local' / 'ohsign'
KEY_ALIAS = 'oh-bench-key-v1'
PWD = '123456'
ISSUER = 'C=CN,O=OpenHarmony,OU=OpenHarmony Team,CN=OpenHarmony Application CA'
SUBJECT = 'C=CN,O=OpenHarmony,OU=OpenHarmony Team,CN=OpenHarmony Application Release'


def tool():
    return SDK_LIB / 'hap-sign-tool.jar'


def run(*args):
    p = subprocess.run(['java', '-jar', str(tool()), *args], capture_output=True, text=True)
    out = (p.stdout + p.stderr).strip()
    if p.returncode != 0 or 'ERROR' in out:
        raise SystemExit(f'signing step failed:\n{out}')
    return out.splitlines()[-1] if out else ''


def keystore():
    ks = WORK / 'OpenHarmony.p12'
    if not ks.exists():
        WORK.mkdir(parents=True, exist_ok=True)
        ks.write_bytes((SDK_LIB / 'OpenHarmony.p12').read_bytes())
        ks.chmod(0o600)
    return ks


def prepare():
    WORK.mkdir(parents=True, exist_ok=True)
    ks = keystore()
    for alias, dest in (('openharmony application root ca', 'rootCA.cer'),
                        ('openharmony application ca', 'subCA.cer')):
        subprocess.run(['keytool', '-exportcert', '-alias', alias, '-keystore', str(ks),
                        '-storepass', PWD, '-storetype', 'PKCS12', '-rfc',
                        '-file', str(WORK / dest)], check=True, capture_output=True)
    print('  ' + run('generate-keypair', '-keyAlias', KEY_ALIAS, '-keyAlg', 'ECC',
                    '-keySize', 'NIST-P-256', '-keystoreFile', str(ks),
                    '-keyPwd', PWD, '-keystorePwd', PWD))
    print('  ' + run('generate-app-cert', '-keyAlias', KEY_ALIAS, '-signAlg', 'SHA256withECDSA',
                    '-issuer', ISSUER, '-issuerKeyAlias', 'openharmony application ca',
                    '-issuerKeyPwd', PWD, '-subject', SUBJECT,
                    '-keystoreFile', str(ks), '-keystorePwd', PWD, '-keyPwd', PWD,
                    '-subCaCertFile', str(WORK / 'subCA.cer'),
                    '-rootCaCertFile', str(WORK / 'rootCA.cer'),
                    '-outForm', 'certChain', '-outFile', str(WORK / 'app-signing.pem'),
                    '-validity', '3650'))
    print(f'  cert chain: {WORK / "app-signing.pem"}')


def device_udid():
    out = subprocess.run(['hdc', 'shell', 'bm', 'get', '--udid'],
                         capture_output=True, text=True, timeout=60).stdout
    m = re.search(r'([0-9A-F]{64})', out)
    if not m:
        raise SystemExit(f'could not read device UDID from: {out!r}')
    return m.group(1)


def sign(inp, outp, bundle, profile_signed=True):
    ks = keystore()
    chain = WORK / 'app-signing.pem'
    if not chain.exists():
        raise SystemExit('run `prepare` first')

    leaf = ''.join(re.findall(r'-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----',
                              chain.read_text(), re.S)[:1])
    template = json.loads((SDK_LIB / 'UnsgnedDebugProfileTemplate.json').read_text(encoding='utf-8'))
    template['bundle-info']['bundle-name'] = bundle
    template['bundle-info']['development-certificate'] = leaf
    template['debug-info']['device-ids'] = [device_udid()]
    prof = WORK / f'{bundle}.profile.json'
    prof.write_text(json.dumps(template, indent=2), encoding='utf-8')
    p7b = WORK / f'{bundle}.p7b'
    print('  ' + run('sign-profile', '-mode', 'localSign',
                     '-keyAlias', 'openharmony application profile debug', '-keyPwd', PWD,
                     '-profileCertFile', str(SDK_LIB / 'OpenHarmonyProfileDebug.pem'),
                     '-inFile', str(prof), '-signAlg', 'SHA256withECDSA',
                     '-keystoreFile', str(ks), '-keystorePwd', PWD, '-outFile', str(p7b)))
    print('  ' + run('sign-app', '-mode', 'localSign',
                     '-keyAlias', KEY_ALIAS, '-keyPwd', PWD,
                     '-appCertFile', str(chain), '-profileFile', str(p7b),
                     '-inFile', str(inp), '-signAlg', 'SHA256withECDSA',
                     '-keystoreFile', str(ks), '-keystorePwd', PWD, '-outFile', str(outp)))
    print(f'  signed -> {outp}')


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)
    sub.add_parser('prepare')
    s = sub.add_parser('sign')
    s.add_argument('input_hap')
    s.add_argument('output_hap')
    s.add_argument('bundle')
    args = ap.parse_args()
    if args.cmd == 'prepare':
        prepare()
    else:
        sign(args.input_hap, args.output_hap, args.bundle)
    return 0


if __name__ == '__main__':
    sys.exit(main())
