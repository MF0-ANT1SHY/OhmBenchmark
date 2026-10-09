#!/usr/bin/env python3
"""Sign a HAP for the test device using the OpenHarmony SDK test credentials.

The original recipe (device-tests/sign.ps1) referenced a per-user workspace
(`C:\\Users\\30422\\...\\work\\signing`) holding dev.p12 / chain.cer / browser.json.
That account and those files are NOT on this machine, so the recipe as written
cannot run. The SDK test material that IS present works instead:

    $SDK_LIB/OpenHarmony.p12                 keystore (keyPwd/keystorePwd 123456)
    $SDK_LIB/OpenHarmonyProfileDebug.pem     profile-signing cert
    $SDK_LIB/UnsgnedDebugProfileTemplate.json
    $SDK_LIB/hap-sign-tool.jar

Two steps, mirroring sign.ps1:
  1. sign-profile  - fill the debug profile template with the bundle name, sign it -> .p7b
  2. sign-app      - sign the unsigned HAP with that profile                -> signed .hap

Usage:
    python3 device-tests/sign_hap_wsl.py UNSIGNED.hap SIGNED.hap BUNDLE_NAME [--sdk-lib DIR]
"""
import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

DEFAULT_SDK_LIB = Path('/mnt/c/Users/research/hdc/lib')
PWD = '123456'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('input_hap')
    ap.add_argument('output_hap')
    ap.add_argument('bundle')
    ap.add_argument('--sdk-lib', default=str(DEFAULT_SDK_LIB))
    ap.add_argument('--compatible-version', default='18')
    ap.add_argument('--keep', action='store_true', help='keep the generated profile next to the output')
    args = ap.parse_args()

    lib = Path(args.sdk_lib)
    tool = lib / 'hap-sign-tool.jar'
    keystore = lib / 'OpenHarmony.p12'
    prof_cert = lib / 'OpenHarmonyProfileDebug.pem'
    template = lib / 'UnsgnedDebugProfileTemplate.json'
    for f in (tool, keystore, prof_cert, template):
        if not f.exists():
            sys.exit(f'missing SDK signing file: {f}')

    work = Path(args.output_hap).parent
    work.mkdir(parents=True, exist_ok=True)
    prof_json = work / (Path(args.output_hap).stem + '.profile.json')
    prof_p7b = work / (Path(args.output_hap).stem + '.p7b')

    doc = json.loads(template.read_text(encoding='utf-8'))
    doc.setdefault('bundle-info', {})['bundle-name'] = args.bundle
    # The template already carries the debug type and the SDK test app-signing cert;
    # only the bundle name is per-app.
    prof_json.write_text(json.dumps(doc, indent=2), encoding='utf-8')

    def run(*cmd):
        p = subprocess.run(['java', '-jar', str(tool), *cmd], capture_output=True, text=True)
        out = (p.stdout + p.stderr).strip()
        if p.returncode != 0:
            print(out)
            raise SystemExit(f'{" ".join(cmd[:2])} failed (rc={p.returncode})')
        return out

    print('1/2 sign-profile')
    print('   ' + run('sign-profile', '-mode', 'localSign',
                      '-keyAlias', 'openharmony application profile debug',
                      '-keyPwd', PWD,
                      '-profileCertFile', str(prof_cert),
                      '-inFile', str(prof_json),
                      '-signAlg', 'SHA256withECDSA',
                      '-keystoreFile', str(keystore),
                      '-keystorePwd', PWD,
                      '-outFile', str(prof_p7b))[:200])

    print('2/2 sign-app')
    print('   ' + run('sign-app', '-mode', 'localSign',
                      '-keyAlias', 'openharmony application release',
                      '-keyPwd', PWD,
                      '-appCertFile', str(lib / 'OpenHarmonyApplication.pem')
                      if (lib / 'OpenHarmonyApplication.pem').exists() else str(prof_cert),
                      '-profileFile', str(prof_p7b),
                      '-inFile', args.input_hap,
                      '-signAlg', 'SHA256withECDSA',
                      '-keystoreFile', str(keystore),
                      '-keystorePwd', PWD,
                      '-outFile', args.output_hap,
                      '-compatibleVersion', args.compatible_version)[:200])

    print(f'signed -> {args.output_hap}')
    if not args.keep:
        prof_json.unlink(missing_ok=True)
        prof_p7b.unlink(missing_ok=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
