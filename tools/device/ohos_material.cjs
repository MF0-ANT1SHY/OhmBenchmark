#!/usr/bin/env node
/* hvigor signing-material password encrypt/decrypt (AES-128-GCM, per ~/.ohos
 * config/material). Reimplementation of hvigor-ohos-plugin DecipherUtil.
 *
 * Usage:
 *   node ohos_material.cjs decrypt <materialDir> <hexCiphertext>
 *   node ohos_material.cjs encrypt <materialDir> <plaintext>   -> hex ciphertext
 */
'use strict';
const crypto = require('crypto');
const fs = require('fs');
const path = require('path');

const COMPONENT = new Int8Array([49, 243, 9, 115, 214, 175, 91, 184, 211, 190, 177, 88, 101, 131, 192, 119]);

function readDirBytes(dir) {
  const e = fs.readdirSync(dir).filter((x) => x !== '.DS_Store');
  if (e.length !== 1) throw new Error('dir ' + dir + ' has ' + e.length + ' files');
  return new Int8Array(fs.readFileSync(path.join(dir, e[0])));
}

function readFd(fd) {
  const subs = fs.readdirSync(fd).filter((x) => x !== '.DS_Store');
  if (subs.length !== 3) throw new Error('fd has ' + subs.length + ' entries');
  return subs.map((s) => readDirBytes(path.join(fd, s)));
}

function decrypt(key, r) {
  const ctLen = ((r[0] & 255) << 24) | ((r[1] & 255) << 16) | ((r[2] & 255) << 8) | (r[3] & 255);
  const ivLen = r.length - 4 - ctLen;
  const iv = r.slice(4, 4 + ivLen);
  const d = crypto.createDecipheriv('aes-128-gcm', key, iv);
  d.setAuthTag(Buffer.from(r.slice(r.length - 16)));
  return Buffer.concat([d.update(Buffer.from(r.slice(4 + ivLen, r.length - 16))), d.final()]);
}

function encrypt(key, pt) {
  // hvigor blobs use a 16-byte IV; the BE prefix = ctLen + 16 so that
  // decrypt's derived ivLen (total-4-e) equals 16.
  const iv = crypto.randomBytes(16);
  const c = crypto.createCipheriv('aes-128-gcm', key, iv);
  const ct = Buffer.concat([c.update(Buffer.from(pt, 'utf8')), c.final()]);
  const tag = c.getAuthTag();
  const len = Buffer.alloc(4);
  len.writeUInt32BE(ct.length + 16);
  return Buffer.concat([len, iv, ct, tag]);
}

function xorAll(arrs) {
  let e = arrs[0];
  for (let i = 1; i < arrs.length; i++) {
    const t = new Int8Array(e.length);
    for (let j = 0; j < e.length; j++) t[j] = e[j] ^ arrs[i][j];
    e = t;
  }
  return Buffer.from(e);
}

function getKey(matRoot) {
  const fd = readFd(path.join(matRoot, 'fd'));
  const salt = readDirBytes(path.join(matRoot, 'ac'));
  const xored = xorAll(fd.concat([COMPONENT]));
  const rootKey = new Int8Array(crypto.pbkdf2Sync(xored.toString(), salt, 10000, 16, 'sha256'));
  const work = readDirBytes(path.join(matRoot, 'ce'));
  return new Int8Array(decrypt(rootKey, work));
}

const mode = process.argv[2];
const matRoot = process.argv[3];
const data = process.argv[4];
if (mode === 'decrypt') {
  console.log(decrypt(getKey(matRoot), new Int8Array(Buffer.from(data, 'hex'))).toString('utf8'));
} else if (mode === 'encrypt') {
  const key = getKey(matRoot);
  const enc = encrypt(key, data).toString('hex').toUpperCase();
  const back = decrypt(key, new Int8Array(Buffer.from(enc, 'hex'))).toString('utf8');
  if (back !== data) throw new Error('round-trip failed');
  console.log(enc);
} else {
  console.error('usage: ohos_material.cjs decrypt|encrypt <materialDir> <data>');
  process.exit(1);
}
