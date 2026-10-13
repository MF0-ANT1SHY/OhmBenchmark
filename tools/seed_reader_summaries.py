#!/usr/bin/env python3
"""Prepare ordinary short RSS summaries in an existing normal reader schema."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tempfile

from clean_sources import app_ref
from reader_data_fixture import CASES
from rss_data_service import Catalogue
from rss_database_fixture import inspect
from rss_dataset import normalize, for_fixture

ROOT = Path(__file__).resolve().parents[1]


def generate(source_database, destination, case_id, body_bytes=256):
    if case_id not in CASES:
        raise ValueError('unsupported ordinary reader case')
    source_database, destination = Path(source_database), Path(destination)
    inspect(source_database, for_fixture(source_database))
    dataset = normalize({'body_bytes': body_bytes})
    catalogue = Catalogue('http://127.0.0.1:18491', body_bytes=body_bytes)
    case = json.loads((ROOT/'cases'/case_id/'case.json').read_text())
    ref = app_ref(case, 'unfixed')
    source = subprocess.check_output(['git', 'show', ref+':entry/src/main/ets/utils/FeedParser.ets'],
                                     cwd=ROOT/case['host_app']['local_path'], text=True)
    destination.mkdir(parents=True, exist_ok=True)
    database = destination/'reader-10-short.db'
    if database.exists():
        raise ValueError('refusing to overwrite an existing summary database')
    # Derive snippets with the actual production implementation, not a second
    # approximation of its HTML/entity rules. This host code never enters a HAP.
    javascript = r"""const fs=require('fs'),ts=require(process.argv[2]);
const text=fs.readFileSync(process.argv[3],'utf8').replace(/^import .*;\n/,'');
const output=ts.transpileModule(text,{compilerOptions:{target:ts.ScriptTarget.ES2020,module:ts.ModuleKind.CommonJS}}).outputText;
const target={exports:{}};new Function('exports','module',output)(target.exports,target);
console.log(target.exports.FeedParser.stripHtml(fs.readFileSync(process.argv[4],'utf8')));
"""
    with tempfile.TemporaryDirectory() as temp:
        temp = Path(temp)
        (temp/'parser.ets').write_text(source)
        (temp/'body.txt').write_text(catalogue.body)
        (temp/'snippet.cjs').write_text(javascript)
        snippet = subprocess.check_output(['node', str(temp/'snippet.cjs'),
            str(ROOT/'toolchain/command-line-tools/hvigor/hvigor/node_modules/typescript'),
            str(temp/'parser.ets'), str(temp/'body.txt')], text=True).rstrip('\n')
        working = temp/'reader.db'
        shutil.copyfile(source_database, working)
        with sqlite3.connect(working) as db:
            db.execute('UPDATE articles SET content=?,snippet=?', (catalogue.body, snippet))
            db.commit()
            db.execute('VACUUM')
        state = inspect(working, dataset)
        shutil.copyfile(working, database)
    database.with_suffix('.dataset.json').write_text(json.dumps(dataset, indent=2)+'\n')
    for number in range(1, 11):
        (destination/f'feed-{number}.xml').write_bytes(catalogue.feed(number))
    (destination/'subscriptions.opml').write_bytes(catalogue.opml())
    return {'status': 'ordinary_short_summary_fixture_prepared', 'performance_verified': False,
            'device_verified': False, 'dataset': dataset, 'article_body_bytes': len(catalogue.body.encode()),
            'ordinary_data': state, 'snippet_source_ref': ref,
            'snippet_source_sha256': hashlib.sha256(source.encode()).hexdigest(),
            'preparation': 'Normal UI-created schema and articles retained; bodies and production-derived snippets replaced with ordinary short RSS summaries outside the app. No evaluator fields or hooks added.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source_database', type=Path)
    parser.add_argument('destination', type=Path)
    parser.add_argument('--case', default='sheafreader_insert_duplicate_exception')
    parser.add_argument('--body-bytes', type=int, default=256)
    args = parser.parse_args()
    result = generate(args.source_database, args.destination, args.case, args.body_bytes)
    (args.destination/'fixture.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, indent=2))
