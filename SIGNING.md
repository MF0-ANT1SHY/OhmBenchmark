# Signing and installing test HAPs

This records how a built HAP gets signed and installed on the measurement device, and
exactly which pieces still exist. It matters because the original signing recipe points at
files that are **not** in this repository and are **not** on the current machine.

## What is in the repository

| Item | Status |
| --- | --- |
| `device-tests/sign.ps1` | **tracked** — the original signing recipe |
| `tools/strip_signing.py` | **tracked** — removes local signing configs so headless builds work |
| `hosts_patches/*/0001-build-strip-local-signing-configs*.patch` | **tracked** — the same strip applied to the host trees |
| Signing keys / certificates / profiles | **not tracked, and not present on this machine** |
| Signed HAPs | **not tracked**, but present in the data directory (see below) |

Every host's `build-profile.json5` has `"signingConfigs": []`, and the hosts build
`*-unsigned.hap`. Installing an unsigned HAP fails with:

```
error: failed to install bundle. code:9568320 error: no signature file.
```

## What `device-tests/sign.ps1` expects — and why it cannot run as-is

```powershell
$signWork = 'C:\Users\30422\Documents\Codex\2026-10-01\goal-project-git-pura-70-case\work\signing'
```

That recipe needs, from `$signWork`:

- `dev.p12` — keystore (`keystorePwd 123456`), aliases
  `openharmony application profile debug` and `openharmony application release`
- `chain.cer` — app-signing certificate chain
- `browser.json` — the profile template, patched per bundle name into `current.json`

and from the SDK, `hap-sign-tool.jar` plus `OpenHarmonyProfileDebug.pem`.

**None of `dev.p12`, `chain.cer` or `browser.json` exist on this machine.** The Windows
account `C:\Users\30422` does not exist here either (the only user is `research`), so the
recipe references a different workstation. This is the one part of the toolchain that was
not carried over.

## What DOES exist and works

1. **The signed HAPs for the measured cases**, under
   `/home/research/OhmBenchmark-data/<measurements|experiments>/<case>/<variant>/app.hap`
   (47 files). These are the exact builds that were measured, and they are the ones
   currently installed on the device.

2. **They still install.** Verified on 2026-10-09 against the attached device:

   ```
   hdc install -r measurements/browser_history_delete_no_transaction/unfixed/app.hap
   -> install bundle successfully.
   ```

   The device reports fingerprint
   `0F380F62A4FC8481B0E57EDE154DFBBDD86AB1347C7B4E40404DDA61447DBB07`,
   unchanged from the original measurement session — so the key that signed them is still
   trusted by this device.

3. **The OpenHarmony SDK test signing material**, at `C:\Users\research\hdc\lib`:

   ```
   OpenHarmony.p12                     keystore, password 123456
   OpenHarmonyProfileDebug.pem         profile-signing certificate
   OpenHarmonyProfileRelease.pem
   UnsgnedDebugProfileTemplate.json    profile template to fill in per bundle
   UnsgnedReleasedProfileTemplate.json
   hap-sign-tool.jar  app_packing_tool.jar  app_unpacking_tool.jar  app_check_tool.jar
   ```

   Copies with SHA-256 checksums are preserved outside the repository at
   `/home/research/OhmBenchmark-backup/signing-assets/` (see `SHA256SUMS` there). They are
   deliberately **not** committed: they are SDK test credentials, not project secrets, and
   committing keystores is bad practice.

   `device-tests/sign_hap_wsl.py` implements the two-step recipe against these files
   (`sign-profile` then `sign-app`).

## The blocker for signing new builds

`hap-sign-tool.jar` is a Java program, and **there is no Java runtime on this machine** —
neither on the WSL `PATH` nor under `C:\Program Files`. So:

- the 47 already-signed HAPs **can** be installed, so cases can be **re-measured** with the
  harnesses as they were built;
- a **newly built** HAP (needed if a probe/harness is edited) **cannot be signed here**
  until a JRE is available.

## Recovery paths, in order of preference

1. **Install a JRE** (e.g. `sudo apt-get install -y default-jre-headless` in WSL, or any
   JDK 8+ on Windows). Then `device-tests/sign_hap_wsl.py` can sign with the SDK test
   credentials. Confirm the resulting fingerprint matches
   `0F380F62A4FC8481B0E57EDE154DFBBDD86AB1347C7B4E40404DDA61447DBB07` before trusting it.
2. **Recover `dev.p12` / `chain.cer` / `browser.json`** from the original workstation
   (`C:\Users\30422\...\work\signing`) or from a Codex session backup. This restores the
   exact original signing identity.
3. **DevEco Studio automatic signing** on a Huawei developer account — regenerates a debug
   certificate and profile for each bundle name; the device must trust the new profile.

## Verifying a signed HAP before installing

```bash
# signature present and bundle name correct
java -jar hap-sign-tool.jar verify-app -inFile app.hap -outCertChain out.cer -outProfile out.p7b

# install
hdc install -r app.hap
```

## Note for the record

The repository is intentionally reproducible without the signing material: `hosts_patches/`
plus `hosts_patches/host-reconstruction.json` rebuild every measured source state exactly
(see `hosts_patches/REPRODUCE.md`). Signing is only needed to get those builds onto a
physical device.
