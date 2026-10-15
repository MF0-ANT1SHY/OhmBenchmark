"""Prove a renewed reproduction signature did not change the measured app.

This does not transfer or modify performance acceptance. Historical signed HAPs
and their exact capture bindings stay immutable. A fresh launch is still needed.
"""
import hashlib
import json
import zipfile

from hap_profile_validity import read_signed_profile, verify_profile


def entries(path):
    with zipfile.ZipFile(path) as package:
        names = package.namelist()
        if len(names) != len(set(names)):
            raise ValueError('duplicate HAP entries cannot prove business identity')
        return {name:hashlib.sha256(package.read(name)).hexdigest() for name in names}


def verify_business_entries(unsigned, measured, renewed):
    original, before, after = entries(unsigned), entries(measured), entries(renewed)
    # The SDK adds .pages.info when code signing. Require that even this
    # signing-generated entry is identical to the historical measured HAP.
    if before != after or not original.keys() <= before.keys():
        raise ValueError('renewed HAP changed historical package entries')
    if (before.keys()-original.keys()) - {'.pages.info'}:
        raise ValueError('unexpected signing-only package entries')
    if any(before[name] != digest for name,digest in original.items()):
        raise ValueError('signed business bytes differ from the audited unsigned build')
    return {'business_entries':len(original),'unchanged_signing_only_entries':sorted(before.keys()-original.keys())}


def verify_identity(unsigned, measured, renewed, bundle, sign_tool, now=None):
    result = verify_business_entries(unsigned, measured, renewed)
    old_profile, old_chain = read_signed_profile(measured, sign_tool)
    new_profile, new_chain = read_signed_profile(renewed, sign_tool)
    validity = verify_profile(new_profile, bundle, now)
    old_identity = {key:value for key,value in old_profile.items() if key != 'validity'}
    new_identity = {key:value for key,value in new_profile.items() if key != 'validity'}
    if old_identity != new_identity or old_chain != new_chain:
        raise ValueError('renewal changed signing identity, permissions or other provisioning fields')
    result.update(status='BUSINESS_AND_PROVISIONING_IDENTITY_VERIFIED_LAUNCH_PENDING',
                  unsigned_sha256=hashlib.sha256(unsigned.read_bytes()).hexdigest(),
                  measured_signed_sha256=hashlib.sha256(measured.read_bytes()).hexdigest(),
                  renewed_signed_sha256=hashlib.sha256(renewed.read_bytes()).hexdigest(),
                  profile_identity_sha256=hashlib.sha256(json.dumps(new_identity,sort_keys=True).encode()).hexdigest(),
                  certificate_chain_sha256=hashlib.sha256(new_chain).hexdigest(),
                  historical_profile_validity=old_profile['validity'],renewed_profile_validity=validity,
                  historical_performance_evidence_changed=False,fresh_launch_verified=False)
    return result
