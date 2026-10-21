const fs=require('fs'),path=require('path'),assert=require('assert');
const ts=require(path.resolve(__dirname,'../toolchain/command-line-tools/hvigor/hvigor/node_modules/typescript'));
const source=fs.readFileSync(process.argv[2],'utf8');
const code=ts.transpileModule(source,{compilerOptions:{target:ts.ScriptTarget.ES2020,module:ts.ModuleKind.CommonJS}}).outputText;
const m={exports:{}};new Function('exports','module',code)(m.exports,m);const ds=new m.exports.HistoryDataSource();
const rows=Array.from({length:2000},(_,n)=>({img:'cover.png',name:'Track '+n,creator:'Artist '+n,time:180}));
const keys=rows.map((row,n)=>JSON.stringify(row,null,n%2?2:0));let history=new Set(keys),notified=0;
const listener={onDataReloaded(){notified++}};ds.registerDataChangeListener(listener);ds.registerDataChangeListener(listener);
const original=JSON.parse;let parses=0;JSON.parse=(...args)=>{parses++;return original(...args)};
try {
 ds.setHistory(history);assert.equal(parses,0);assert.equal(notified,1);assert.equal(ds.totalCount(),2000);
 const first=ds.getData(0);assert.deepStrictEqual(first.song,rows[1999]);assert.equal(first.key,keys[1999]);assert.strictEqual(ds.getData(0),first);assert.equal(parses,1);
 const second=ds.getData(1);assert.deepStrictEqual(second.song,rows[1998]);assert.equal(parses,2);
 history.delete(first.key);ds.setHistory(history);assert.equal(ds.totalCount(),1999);assert.strictEqual(ds.getData(0),second);assert.equal(parses,2);
 history.add(first.key);ds.setHistory(history);assert.deepStrictEqual(ds.getData(0).song,first.song);assert.equal(parses,3);
 ds.unregisterDataChangeListener(listener);const previous=notified;ds.setHistory(new Set());assert.equal(ds.totalCount(),0);assert.equal(notified,previous);
} finally {JSON.parse=original;}
console.log('PASS: 2000-entry order, lazy decoding, cache reuse, exact-key deletion, reinsertion, empty state, listener lifecycle');
