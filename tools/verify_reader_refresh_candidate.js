// External regression test. This file is never compiled into the app.
const fs = require('fs'), path = require('path'), assert = require('assert');
const ts = require(path.resolve(__dirname, '../toolchain/command-line-tools/hvigor/hvigor/node_modules/typescript'));
const source = fs.readFileSync(process.argv[2], 'utf8').replace(/^import .*;\r?\n/gm, '');
const code = ts.transpileModule(source, {compilerOptions: {
  target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS
}}).outputText;
let feeds = [];
const database = {async getAllFeeds() { return feeds; }};
const mod = {exports: {}};
new Function('exports', 'module', 'DatabaseManager', 'RefreshOutcome', 'ScopeFilter', 'FetchSchedule', code)(
  mod.exports, mod, {getInstance() { return database; }},
  class { constructor() { this.inserted = 0; this.notified = []; } },
  {contains(ids, id) { return ids.includes(id); }},
  {due(frequency, fetched, now) { return fetched + frequency * 60000 <= now; }}
);
const service = mod.exports.FeedService.getInstance();
async function run(count, scoped = null, scheduled = false) {
  feeds = Array.from({length: count}, (_, i) => ({id: i + 1, fetchFrequency: 60,
    lastFetched: i % 2 ? Date.now() : 1, isServiceManaged() { return false; }}));
  let active = 0, peak = 0; const seen = [], progress = [];
  service.refreshFeed = async id => {
    active++; peak = Math.max(peak, active); seen.push(id);
    await new Promise(resolve => setTimeout(resolve, (5 - id % 4) * 2));
    active--; return id;
  };
  const result = await service.refreshAllFeeds((done, total) => progress.push([done, total]), scheduled, scoped);
  const expected = feeds.filter(f => (!scoped || scoped.includes(f.id)) && (!scheduled || f.id % 2));
  assert.deepStrictEqual(seen.sort((a, b) => a - b), expected.map(f => f.id));
  assert.equal(result.inserted, expected.reduce((sum, f) => sum + f.id, 0), 'concurrent completions lost inserted counts');
  assert.equal(peak, Math.min(4, expected.length));
  assert.deepStrictEqual(progress, expected.map((_, i) => [i + 1, expected.length]));
  assert.equal(service.isFetching(), false);
}
(async () => {
  await run(10); await run(0); await run(10, [2, 5, 8]); await run(10, null, true);
  console.log('PASS: out-of-order completion totals, four-worker bound, scope, schedule, progress, empty input');
})().catch(error => { console.error(error); process.exitCode = 1; });
