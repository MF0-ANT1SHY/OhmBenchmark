#!/usr/bin/env python3
"""Sign a HAP for the test device.

Supersedes the recipe in device-tests/sign.ps1, which read dev.p12 / chain.cer /
browser.json from a Windows user profile that no longer exists. Everything here comes from
the project toolchain plus the device itself, so it is reproducible.

Signing needs FOUR things, and getting any one wrong produces a confusing error:

  1. a JRE                      (~/.local/jre, installed without root)
  2. the SDK signing material   toolchain/command-line-tools/sdk/default/openharmony/
                                toolchains/lib: OpenHarmony.p12, OpenHarmonyProfileDebug.pem,
                                UnsgnedDebugProfileTemplate.json, hap-sign-tool.jar
  3. a sign-app-capable tool    USE THE TOOLCHAIN COPY. The older hap-sign-tool.jar in
                                ~/hdc/lib fails with "Illegal base64 character 20" for every
                                input; the 5.1.0.840 copy works. This was the real blocker.
  4. an app key + issued chain  generated here, because the standalone toolchain ships no
                                OpenHarmonyApplication.pem

The certificate chain matters too: it must be issued FOR the key being used to sign
(`generate-keypair` then `generate-app-cert` with that key alias). A chain whose leaf does
not pair with the signing key fails with "verify certificate chain failed! Signature does
not match."

Deploying a rebuilt HAP also requires understanding the device's rule (observed):

  same signing identity already installed  ->  hdc install -r works
  different signing identity               ->  code:9568332 "install sign info inconsistent"

so a rebuild signed with a new certificate needs `hdc uninstall` first.

Usage:
    python3 device-tests/sign_hap.py prepare
    python3 device-tests/sign_hap.py sign UNSIGNED.hap SIGNED.hap BUNDLE
    python3 device-tests/sign_hap.py install SIGNED.hap [--replace]
"""
import argparse
import json
import re
import subprocess
import sys
import time
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TOOLCHAIN_LIB = (REPO / 'toolchain' / 'command-line-tools' / 'sdk' / 'default' /
                 'openharmony' / 'toolchains' / 'lib')
FALLBACK_LIB = Path.home() / 'OhmBenchmark-toolchain' / 'command-line-tools' / 'sdk' / \
    'default' / 'openharmony' / 'toolchains' / 'lib'
WORK = Path.home() / '.local' / 'ohsign2'
KEY_ALIAS = 'oh-bench2'
PWD = '123456'
ISSUER = 'C=CN,O=OpenHarmony,OU=OpenHarmony Team,CN=OpenHarmony Application CA'
SUBJECT = 'C=CN,O=OpenHarmony,OU=OpenHarmony Team,CN=OpenHarmony Application Release'


def lib():
    for cand in (TOOLCHAIN_LIB, FALLBACK_LIB):
        if (cand / 'hap-sign-tool.jar').exists():
            return cand
    sys.exit(f'no toolchain signing lib found; looked in {TOOLCHAIN_LIB} and {FALLBACK_LIB}')


def run(*args, tool=None, check=True):
    t = tool or (lib() / 'hap-sign-tool.jar')
    p = subprocess.run(['java', '-jar', str(t), *args], capture_output=True, text=True)
    out = (p.stdout + p.stderr).strip()
    if check and (p.returncode != 0 or 'ERROR' in out):
        raise SystemExit(f'signing step failed:\n{out}')
    return out


def ks():
    WORK.mkdir(parents=True, exist_ok=True)
    k = WORK / 'ks.p12'
    if not k.exists():
        k.write_bytes((lib() / 'OpenHarmony.p12').read_bytes())
        k.chmod(0o600)
    return k


def prepare(force=False):
    WORK.mkdir(parents=True, exist_ok=True)
    k = ks()
    app = WORK / 'app.pem'
    if app.exists() and not force:
        print(f'  signing identity already prepared: {app}')
        return
    for alias, dest in (('openharmony application root ca', 'rootCA.cer'),
                        ('openharmony application ca', 'subCA.cer')):
        subprocess.run(['keytool', '-exportcert', '-alias', alias, '-keystore', str(k),
                        '-storepass', PWD, '-storetype', 'PKCS12', '-rfc',
                        '-file', str(WORK / dest)], check=True, capture_output=True)
    print('  ' + run('generate-keypair', '-keyAlias', KEY_ALIAS, '-keyAlg', 'ECC',
                     '-keySize', 'NIST-P-256', '-keystoreFile', str(k),
                     '-keyPwd', PWD, '-keystorePwd', PWD).splitlines()[-1])
    print('  ' + run('generate-app-cert', '-keyAlias', KEY_ALIAS, '-signAlg', 'SHA256withECDSA',
                     '-issuer', ISSUER, '-issuerKeyAlias', 'openharmony application ca',
                     '-issuerKeyPwd', PWD, '-subject', SUBJECT,
                     '-keystoreFile', str(k), '-keystorePwd', PWD, '-keyPwd', PWD,
                     '-subCaCertFile', str(WORK / 'subCA.cer'),
                     '-rootCaCertFile', str(WORK / 'rootCA.cer'),
                     '-outForm', 'certChain', '-outFile', str(app),
                     '-validity', '3650').splitlines()[-1])
    print(f'  app cert chain: {app}')


def udid():
    out = subprocess.run(['hdc', 'shell', 'bm', 'get', '--udid'],
                         capture_output=True, text=True, timeout=60).stdout
    m = re.search(r'([0-9A-F]{64})', out)
    if not m:
        raise SystemExit(f'cannot read device UDID from {out!r}')
    return m.group(1)


def leaf_pem(chain: Path) -> str:
    blocks = re.findall(r'-----BEGIN CERTIFICATE-----\s*(.*?)\s*-----END CERTIFICATE-----',
                        chain.read_text().replace('\r', ''), re.S)
    if not blocks:
        raise SystemExit(f'no certificate in {chain}')
    b64 = re.sub(r'\s+', '', blocks[0])
    return ('-----BEGIN CERTIFICATE-----\n' +
            '\n'.join(b64[i:i + 64] for i in range(0, len(b64), 64)) +
            '\n-----END CERTIFICATE-----\n')


def sign(inp, outp, bundle, *, device_udid=None, measured_profile=None):
    if device_udid is not None and (not isinstance(device_udid,str) or not re.fullmatch(r'[0-9A-F]{64}',device_udid)):
        raise ValueError('explicit signing UDID must be 64 uppercase hexadecimal characters')
    k = ks()
    app = WORK / 'app.pem'
    if not app.exists():
        sys.exit('run `prepare` first')
    if measured_profile is None:
        tpl = json.loads((lib() / 'UnsgnedDebugProfileTemplate.json').read_text(encoding='utf-8'))
    else:
        # Reproduction renewals retain the verified historical provisioning
        # document exactly (including legacy empty ACL placeholders). This is
        # separate from configuring a newly built application's permissions.
        tpl = json.loads(json.dumps(measured_profile))
        if (tpl.get('type') != 'debug' or tpl.get('bundle-info',{}).get('bundle-name') != bundle or
                tpl['bundle-info'].get('development-certificate') != leaf_pem(app) or
                device_udid is None or tpl.get('debug-info',{}).get('device-ids') != [device_udid]):
            raise ValueError('measured provisioning identity does not match the existing signing key, bundle and device binding')
    # The SDK template has historical dates; issue a bounded current debug
    # profile using the existing certificate/key, not the template's expiry.
    now = int(time.time())
    tpl['validity'] = {'not-before': now - 300, 'not-after': now + 30 * 86400}
    if measured_profile is None:
        tpl['bundle-info']['bundle-name'] = bundle
        tpl['bundle-info']['development-certificate'] = leaf_pem(app)
        tpl['debug-info']['device-ids'] = [udid() if device_udid is None else device_udid]
    # Keep the original production manifest. The floating-lyrics feature requests
    # an ACL-controlled permission; authorize exactly that request in the device
    # debug profile rather than dropping the feature or altering app bytecode.
    with zipfile.ZipFile(inp) as package:
        module = json.loads(package.read('module.json'))['module']
    requested = {p['name'] for p in module.get('requestPermissions', [])}
    allowed = sorted(requested & {'ohos.permission.SYSTEM_FLOAT_WINDOW'})
    if measured_profile is None:
        tpl['acls']['allowed-acls'] = allowed
    prof_json = WORK / f'{bundle}.profile.json'
    prof_json.write_text(json.dumps(tpl, indent=2), encoding='utf-8')
    p7b = WORK / f'{bundle}.p7b'
    print('  ' + run('sign-profile', '-mode', 'localSign',
                     '-keyAlias', 'openharmony application profile debug', '-keyPwd', PWD,
                     '-profileCertFile', str(lib() / 'OpenHarmonyProfileDebug.pem'),
                     '-inFile', str(prof_json), '-signAlg', 'SHA256withECDSA',
                     '-keystoreFile', str(k), '-keystorePwd', PWD,
                     '-outFile', str(p7b)).splitlines()[-1])
    print('  ' + run('sign-app', '-mode', 'localSign',
                     '-keyAlias', KEY_ALIAS, '-keyPwd', PWD,
                     '-appCertFile', str(app), '-profileFile', str(p7b),
                     '-inFile', str(inp), '-signAlg', 'SHA256withECDSA',
                     '-keystoreFile', str(k), '-keystorePwd', PWD,
                     '-outFile', str(outp)).splitlines()[-1])
    print(f'  signed -> {outp}')


def install(hap, bundle=None, replace=False):
    if replace:
        subprocess.run(['hdc', 'install', '-r', str(hap)], check=False)
    else:
        if bundle:
            print('  uninstalling existing bundle (new signing identity needs a clean install)')
            subprocess.run(['hdc', 'uninstall', bundle], check=False, capture_output=True)
        subprocess.run(['hdc', 'install', str(hap)], check=False)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('prepare'); p.add_argument('--force', action='store_true')
    s = sub.add_parser('sign')
    s.add_argument('input_hap'); s.add_argument('output_hap'); s.add_argument('bundle')
    i = sub.add_parser('install')
    i.add_argument('hap'); i.add_argument('--bundle'); i.add_argument('--replace', action='store_true')
    a = ap.parse_args()
    if a.cmd == 'prepare':
        prepare(force=a.force)
    elif a.cmd == 'sign':
        sign(a.input_hap, a.output_hap, a.bundle)
    else:
        install(a.hap, a.bundle, a.replace)
    return 0


if __name__ == '__main__':
    sys.exit(main())
