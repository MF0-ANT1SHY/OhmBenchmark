const fs=require('fs');
const path=require('path');
const root=path.resolve(__dirname,'..');
const originalPath=process.argv[2],candidatePath=process.argv[3],fixturePath=process.argv[4];
if(!originalPath||!candidatePath||!fixturePath)throw Error('original source, candidate source and ordinary fixture directory are required');
const ts=require(path.join(root,'toolchain/command-line-tools/hvigor/hvigor/node_modules/typescript'));
function load(file){
 const source=fs.readFileSync(file,'utf8').replace(/^import .*;\n/,'');
 const output=ts.transpileModule(source,{compilerOptions:{target:ts.ScriptTarget.ES2020,module:ts.ModuleKind.CommonJS}}).outputText;
 const module={exports:{}};new Function('exports','module','Feed','Article','FeedGroup',output)(module.exports,module,class Feed {constructor(url,title){this.url=url;this.title=title;}},class Article {},class FeedGroup {});return module.exports.FeedParser;
}
const original=load(originalPath);const candidate=load(candidatePath);
const rows=[
 ['<title>普通标题</title>','title'],['<TITLE>Mixed</TiTlE>','title'],
 ['<title class="wide">value</title >','title'],['<titleX>wrong</titleX><title>correct</title>','title'],
 ['<description><![CDATA[<html><p>文章</p></html>]]></description>','description'],
 ['<content:encoded> <![CDATA[First]]> <![CDATA[Second]]> </CONTENT:ENCODED>','content:encoded'],
 ['<author>None</author>','title'],['<title>unclosed','title'],
 ['<title><![CDATA[incomplete</title>','title'],
 ['<title>first</TITLE><title>second</title>','title'],
 ['<title>before <![CDATA[one]]> between <![CDATA[two]]> after</title>','title']
];
let count=0;
for(const [xml,tag] of rows){if(candidate.extractTag(xml,tag)!==original.extractTag(xml,tag))throw Error('Different extraction: '+xml);count++;}
for(let i=0;i<2000;i++){
 const tag=['title','description','pubDate','content:encoded'][i%4];
 const spelling=[tag,tag.toUpperCase(),tag[0].toUpperCase()+tag.slice(1)][i%3];
 const body='<p>Reading &amp; notes 世界 '+i+'</p>'.repeat(i%30);
 const xml='<ignored>value</ignored><'+spelling+' key="value">\n<![CDATA['+body+']]>\n</'+spelling+' >';
 if(candidate.extractTag(xml,tag)!==original.extractTag(xml,tag))throw Error('Different generated extraction '+i);count++;
}
let articles=0;
function normalize(value){return JSON.parse(JSON.stringify(value,(key,item)=>key==='fetched'?undefined:item));}
for(let i=1;i<=10;i++){
 const xml=fs.readFileSync(path.join(fixturePath,'feed-'+i+'.xml'),'utf8');
 const url='http://127.0.0.1:18491/feeds/'+i+'.xml';
 const first=original.parse(xml,url),last=candidate.parse(xml,url);
 if(!first||!last||JSON.stringify(normalize(first))!==JSON.stringify(normalize(last)))throw Error('Different full RSS parse for feed '+i);
 if(last.articles.length!==100)throw Error('Missing ordinary articles');
 articles+=last.articles.length;
}
console.log(JSON.stringify({extraction_comparisons:count,ordinary_feeds:10,ordinary_articles:articles,full_parse_equal:true,performance_verified:false}));
