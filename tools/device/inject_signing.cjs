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
  delete appFile.bundleName; // in case an earlier bad run wrote it top-level
  fs.writeFileSync(appJsonPath, JSON.stringify(appFile, null, 2) + '\n');
  console.log(`bundleName: ${old} -> ${mat.bundle}`);
} else {
  // FA model or unusual layout: fail loudly so we notice.
  console.error('WARN: AppScope/app.json5 not found at ' + appJsonPath);
}
console.log('signing config injected into ' + bpPath);
