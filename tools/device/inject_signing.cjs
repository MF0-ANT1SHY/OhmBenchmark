#!/usr/bin/env node
/*
 * Inject debug signing config + unified bundle name into a host project.
 * Usage: node inject_signing.cjs <host_dir> [<sign_material.json>]
 *
 * - build-profile.json5: adds app.signingConfigs[default] (HarmonyOS debug
 *   material) and wires every product's signingConfig to "default".
 * - AppScope/app.json5: sets bundleName to the profile's bundle.
 * Revert with: git checkout -- build-profile.json5 AppScope/app.json5
 */
'use strict';
const fs = require('fs');
const path = require('path');
const json5 = require('/Users/syang/.local/bin/command-line-tools/hvigor/hvigor-ohos-plugin/node_modules/json5');

const hostDir = path.resolve(process.argv[2]);
const matPath = path.resolve(process.argv[3] || path.join(__dirname, '..', '.sign_material.json'));
const mat = JSON.parse(fs.readFileSync(matPath, 'utf8'));

const bpPath = path.join(hostDir, 'build-profile.json5');
const bp = json5.parse(fs.readFileSync(bpPath, 'utf8'));
bp.app = bp.app || {};
bp.app.signingConfigs = [
  {
    name: 'default',
    type: 'HarmonyOS',
    material: {
      certpath: mat.certpath,
      storePassword: mat.storePasswordEnc,
      keyAlias: mat.keyAlias,
      keyPassword: mat.keyPasswordEnc,
      profile: mat.profile,
      signAlg: mat.signAlg || 'SHA256withECDSA',
      storeFile: mat.storeFile,
    },
  },
];
(bp.app.products || []).forEach((p) => { p.signingConfig = 'default'; });
fs.writeFileSync(bpPath, JSON.stringify(bp, null, 2) + '\n');

const appJsonPath = path.join(hostDir, 'AppScope', 'app.json5');
if (fs.existsSync(appJsonPath)) {
  const appFile = json5.parse(fs.readFileSync(appJsonPath, 'utf8'));
  const app = appFile.app || appFile;
  const old = app.bundleName;
  app.bundleName = mat.bundle;
  // hosts ship different versionCodes; a shared bundle name needs one value or
  // host-to-host switches fail with "install version downgrade"
  app.versionCode = 1000000;
  delete appFile.bundleName; // in case an earlier bad run wrote it top-level
  fs.writeFileSync(appJsonPath, JSON.stringify(appFile, null, 2) + '\n');
  console.log(`bundleName: ${old} -> ${mat.bundle} (versionCode=1000000)`);
} else {
  // FA model or unusual layout: fail loudly so we notice.
  console.error('WARN: AppScope/app.json5 not found at ' + appJsonPath);
}

// Module-level compatibility for real-phone debug installs:
//  - add "phone" to deviceTypes (some hosts declare tablet/2in1 only)
//  - drop restricted permissions a normal debug profile cannot be granted
//    (SYSTEM_FLOAT_WINDOW = desktop-lyrics feature; not exercised by cases)
const RESTRICTED = new Set(['ohos.permission.SYSTEM_FLOAT_WINDOW']);
function walk(dir) {
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) walk(p);
    else if (e.name === 'module.json5') {
      const m = json5.parse(fs.readFileSync(p, 'utf8'));
      let changed = [];
      const mod = m.module || m;
      if (Array.isArray(mod.deviceTypes) && !mod.deviceTypes.includes('phone')) {
        mod.deviceTypes.push('phone');
        changed.push('+phone');
      }
      if (Array.isArray(mod.requestPermissions)) {
        const before = mod.requestPermissions.length;
        mod.requestPermissions = mod.requestPermissions.filter(
          (r) => !RESTRICTED.has(r.name));
        if (mod.requestPermissions.length !== before) changed.push('-SYSTEM_FLOAT_WINDOW');
      }
      if (changed.length) {
        fs.writeFileSync(p, JSON.stringify(m, null, 2) + '\n');
        console.log(`module.json5 ${p.replace(hostDir, '')}: ${changed.join(' ')}`);
      }
    }
  }
}
walk(path.join(hostDir, 'entry'));
const productsDir = path.join(hostDir, 'products');
if (fs.existsSync(productsDir)) walk(productsDir);
const featuresDir = path.join(hostDir, 'features');
if (fs.existsSync(featuresDir)) walk(featuresDir);
console.log('signing config injected into ' + bpPath);
