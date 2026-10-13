"""Restore identical ordinary reader data and pin its external RSS source."""
import hashlib
import json
from pathlib import Path
import uuid

from install_sqlite_fixture import install
from rss_database_fixture import inspect
from rss_service_fixture import prepare as service, same_instance
from snapshot_reader_database import snapshot

CASES = {'sheafreader_extract_tag_tolowercase', 'sheafreader_insert_duplicate_exception',
         'sheafreader_refresh_feeds_sequential', 'sheafreader_unread_counts_n_plus_1',
         'sheafreader_article_list_foreach'}
ROOT = Path(__file__).resolve().parents[1]


def audit_device(remote):
    path = ROOT / 'artifacts/fixtures/rss-audits' / (uuid.uuid4().hex + '.db')
    receipt = snapshot(remote, path)
    receipt['local_archive'] = str(path)
    path.with_suffix('.json').write_text(json.dumps(receipt, indent=2) + '\n')
    return receipt


def identity(database, source):
    return hashlib.sha256(json.dumps({
        'database_semantic_sha256': database['semantic_sha256'],
        'rss_payload_sha256': source['sha256'],
    }, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def prepare(remote, case, fixture):
    if (case['id'] not in CASES
            or case['host_app']['bundle_name'] != 'com.sheafreader.hm'):
        raise ValueError('reader fixture provided to an unsupported case')
    expected = inspect(fixture)
    source = service(remote, case)
    installed = install(remote, case['host_app']['bundle_name'],
                        case['testcase']['module'], 'sheaf_reader.db', fixture)
    actual = audit_device(remote)
    if actual['ordinary_data']['semantic_sha256'] != expected['semantic_sha256']:
        raise RuntimeError('device reader data differs from the prepared ordinary database')
    return {'sha256': identity(expected, source), 'database': expected,
            'device_snapshot': actual, 'installation': installed, 'service': source,
            'functional_read_verified': True,
            'method': 'ordinary UI-populated database restored outside profiling and all article bodies verified'}


def finish(remote, case, before):
    after_source = service(remote, case)
    same_instance(before['service'], after_source)
    actual = audit_device(remote)
    if actual['ordinary_data']['semantic_sha256'] != before['database']['semantic_sha256']:
        raise RuntimeError('reader contents changed or were incomplete after the workload')
    if identity(actual['ordinary_data'], after_source) != before['sha256']:
        raise RuntimeError('reader/RSS input identity changed')
    return {'sha256': before['sha256'], 'service': after_source,
            'device_snapshot': actual, 'functional_read_verified': True}
