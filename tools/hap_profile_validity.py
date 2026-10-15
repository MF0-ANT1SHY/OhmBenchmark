"""Check current installability dates separately from historical HAP evidence."""
import json
import math
import subprocess
import tempfile
import time
from pathlib import Path


def verify_profile(profile, bundle, now=None):
    now = time.time() if now is None else now
    if (not isinstance(profile, dict) or not isinstance(profile.get('validity'), dict)
            or not isinstance(profile.get('bundle-info'), dict)
            or type(now) not in (int, float)):
        raise ValueError('invalid signed profile or validity clock')
    validity = profile.get('validity', {})
    before, after = validity.get('not-before'), validity.get('not-after')
    if (type(before) is not int or type(after) is not int or
            not 0 <= before < after or not math.isfinite(now)):
        raise ValueError('invalid signed profile validity interval')
    if profile.get('bundle-info', {}).get('bundle-name') != bundle:
        raise ValueError('signed profile belongs to a different bundle')
    if now < before:
        raise ValueError('signed app profile is not yet valid')
    if now >= after:
        raise ValueError('signed app profile is expired; refusing an uninstallable export')
    return {'bundle': bundle, 'not_before': before, 'not_after': after,
            'checked_at': now}


def verify_installable_profile(hap, bundle, sign_tool, now=None):
    # The SDK verify-app command verifies HAP digests but, on the installed
    # SDK, accepts an expired provisioning profile. Explicitly check its dates.
    with tempfile.TemporaryDirectory(prefix='hap-profile-') as temporary:
        root = Path(temporary)
        result = subprocess.run([
            'java', '-jar', str(sign_tool), 'verify-app', '-inFile', str(hap),
            '-outCertChain', str(root/'chain.cer'), '-outProfile', str(root/'profile.p7b')],
            capture_output=True, timeout=120)
        if result.returncode or not (root/'profile.p7b').is_file():
            raise ValueError('HAP signature/profile extraction failed')
        result = subprocess.run([
            'openssl', 'cms', '-verify', '-noverify', '-inform', 'DER',
            '-in', str(root/'profile.p7b'), '-out', str(root/'profile.json')],
            capture_output=True, timeout=30)
        if result.returncode:
            raise ValueError('signed provisioning profile CMS verification failed')
        profile = json.loads((root/'profile.json').read_bytes())
        return verify_profile(profile, bundle, now)
