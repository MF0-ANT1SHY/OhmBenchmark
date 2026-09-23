#!/usr/bin/env python3
"""Publish results artifacts to a GitHub Release, rewrite their record URLs,
verify the uploaded assets, then remove the local copies.

Requires an authenticated `gh` CLI and an existing Release tag. The tracked
proof/device JSONL files stay in results; binary captures, screenshots, layout
snapshots and run logs are uploaded as individual assets. Trace and log files
are gzip-compressed for transfer.

Usage: python3 publish_release_artifacts.py --tag device-proof-YYYY-MM-DD
       python3 publish_release_artifacts.py --tag TAG --case CASE_ID
"""
import argparse
import gzip
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
RESULTS = REPO / 'results'
COMPRESS_SUFFIXES = {'.chtrace', '.hilog', '.log'}
def run(args, *, capture=True):
    p = subprocess.run(args, cwd=REPO, check=True, text=True,
                       stdout=subprocess.PIPE if capture else None,
                       stderr=subprocess.PIPE if capture else None)
    return p.stdout.strip() if capture else ''


def release_data(tag):
    slug_url = run(['git', 'config', '--get', 'remote.origin.url'])
    m = re.search(r'github\.com[:/]([^/]+/[^/.]+?)(?:\.git)?$', slug_url)
    if not m:
        raise RuntimeError(f'cannot parse GitHub repository from origin: {slug_url}')
    slug = m.group(1)
    data = json.loads(run(['gh', 'api', f'repos/{slug}/releases/tags/{tag}']))
    return slug, data


def candidates(cases):
    all_paths = set()
    if cases:
        for case in cases:
            folder = RESULTS / case
            if folder.is_dir():
                all_paths.update(p for p in folder.rglob('*') if p.is_file())
            all_paths.update(p for p in RESULTS.glob(f'{case}.*') if p.is_file())
    else:
        all_paths.update(p for p in RESULTS.rglob('*') if p.is_file())
    all_paths = {p for p in all_paths if p.suffix != '.jsonl'}
    # A compressed trace is exposed through its original .chtrace symlink.
    # Publish that logical file once, and remove both names after verification.
    linked_targets = {p.resolve() for p in all_paths
                      if p.suffix == '.chtrace' and p.is_symlink()}
    publish_paths = sorted(p for p in all_paths
                           if p.is_symlink() or p.resolve() not in linked_targets)
    purge_paths = sorted(all_paths)
    return publish_paths, purge_paths


def make_asset(src, out):
    h = hashlib.sha256()
    compressed_by_type = src.suffix in COMPRESS_SUFFIXES
    with src.open('rb') as inp:
        magic = inp.read(2)
        inp.seek(0)
        already_gz = magic == b'\x1f\x8b'
        should_gzip = compressed_by_type and not already_gz
        with out.open('wb') as raw_target:
            if should_gzip:
                target = gzip.GzipFile(fileobj=raw_target, mode='wb',
                                       compresslevel=6, mtime=0)
            else:
                target = raw_target
            if should_gzip:
                with target:
                    while chunk := inp.read(1024 * 1024):
                        h.update(chunk)
                        target.write(chunk)
            else:
                while chunk := inp.read(1024 * 1024):
                    h.update(chunk)
                    target.write(chunk)
    digest = h.hexdigest()
    asset_sha = hashlib.sha256()
    with out.open('rb') as f:
        while chunk := f.read(1024 * 1024):
            asset_sha.update(chunk)
    return digest, asset_sha.hexdigest(), should_gzip or already_gz


def asset_name(src, digest, gzipped):
    rel = src.relative_to(RESULTS).as_posix()
    name = rel + ('.gz' if gzipped else '')
    suffix = ''.join(Path(name).suffixes[-2:]) if gzipped else Path(name).suffix
    stem = name[:-len(suffix)] if suffix else name
    safe = re.sub(r'[^A-Za-z0-9._-]+', '-', stem)
    return f'{safe}--{digest[:12]}{suffix}'


def api_assets(slug, tag):
    data = json.loads(run(['gh', 'api', f'repos/{slug}/releases/tags/{tag}']))
    return {a['name']: a for a in data.get('assets', [])}


def rewrite_records(path_map):
    for path in sorted(RESULTS.glob('*.jsonl')):
        rows = []
        changed = False
        with path.open(encoding='utf-8') as f:
            for line in f:
                if not line.strip():
                    continue
                obj = json.loads(line)

                def visit(value):
                    nonlocal changed
                    if isinstance(value, dict):
                        for key, child in list(value.items()):
                            if isinstance(child, str) and child in path_map:
                                value[key] = path_map[child]
                                changed = True
                            else:
                                visit(child)
                    elif isinstance(value, list):
                        for child in value:
                            visit(child)

                visit(obj)
                rows.append(json.dumps(obj, ensure_ascii=False))
        if changed:
            path.write_text('\n'.join(rows) + '\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tag', required=True)
    parser.add_argument('--case', action='append', default=[])
    args = parser.parse_args()

    publish_paths, purge_paths = candidates(args.case)
    if not publish_paths:
        raise SystemExit('no untracked results artifacts found to publish')
    empty_paths = [p for p in publish_paths if p.stat().st_size == 0]
    publish_paths = [p for p in publish_paths if p.stat().st_size > 0]
    slug, rel = release_data(args.tag)
    existing = {a['name']: a for a in rel.get('assets', [])}
    expected = []
    path_info = {}
    with tempfile.TemporaryDirectory(prefix='ohm-release-assets-') as td:
        temp = Path(td)
        to_upload = []
        for index, src in enumerate(publish_paths):
            out = temp / f'artifact-{index}'
            original_sha, asset_sha, gzipped = make_asset(src, out)
            name = asset_name(src, original_sha, gzipped)
            out.rename(temp / name)
            out = temp / name
            size = out.stat().st_size
            info = {'source': str(src), 'relative_path': src.relative_to(RESULTS).as_posix(),
                    'asset_name': name, 'source_size': src.stat().st_size,
                    'source_sha256': original_sha, 'asset_size': size,
                    'asset_sha256': asset_sha}
            if name in existing:
                remote = existing[name]
                if remote['size'] != size:
                    raise RuntimeError(f'remote asset size mismatch for {name}')
            else:
                to_upload.append(out)
            expected.append(info)
            path_info[str(src)] = info
        if to_upload:
            run(['gh', 'release', 'upload', args.tag,
                 *[str(p) for p in to_upload]], capture=False)

        current_assets = api_assets(slug, args.tag)
        for info in expected:
            remote = current_assets.get(info['asset_name'])
            if not remote or remote['size'] != info['asset_size']:
                raise RuntimeError(f'release verification failed for {info["asset_name"]}')
            digest = remote.get('digest')
            if digest and digest != f'sha256:{info["asset_sha256"]}':
                raise RuntimeError(f'GitHub digest mismatch for {info["asset_name"]}: {digest}')
            info['asset_url'] = remote['browser_download_url']

        doc_dir = REPO / 'docs' / 'device-artifacts'
        doc_dir.mkdir(parents=True, exist_ok=True)
        doc = doc_dir / f'{args.tag}.json'
        if doc.exists():
            manifest = json.loads(doc.read_text(encoding='utf-8'))
        else:
            manifest = {'repository': slug, 'release_tag': args.tag,
                        'artifacts': [], 'omitted_artifacts': []}
        known = {x.get('asset_name') for x in manifest.get('artifacts', [])}
        manifest.setdefault('artifacts', []).extend(
            i for i in expected if i['asset_name'] not in known)
        omitted = {x.get('relative_path') for x in manifest.get('omitted_artifacts', [])}
        manifest.setdefault('omitted_artifacts', []).extend(
            {'relative_path': p.relative_to(RESULTS).as_posix(), 'source_size': 0,
             'reason': 'empty source file; GitHub Releases does not accept zero-byte assets'}
            for p in empty_paths if p.relative_to(RESULTS).as_posix() not in omitted)
        manifest['updated_at_utc'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        manifest['source_commit'] = run(['git', 'rev-parse', 'HEAD'])
        doc.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n',
                       encoding='utf-8')

        # Keep an identical, timestamped manifest with the Release assets.
        manifest_asset = f'{args.tag}-manifest-{int(time.time())}.json'
        manifest_upload = temp / manifest_asset
        shutil.copyfile(doc, manifest_upload)
        run(['gh', 'release', 'upload', args.tag, str(manifest_upload)], capture=False)
        current_assets = api_assets(slug, args.tag)
        remote_manifest = current_assets.get(manifest_asset)
        if not remote_manifest or remote_manifest['size'] != manifest_upload.stat().st_size:
            raise RuntimeError('release manifest verification failed')

        path_map = {source: info['asset_url'] for source, info in path_info.items()}
        rewrite_records(path_map)
        for proof in (RESULTS / 'proof.jsonl',):
            if not proof.exists():
                continue
            for line in proof.read_text(encoding='utf-8').splitlines():
                row = json.loads(line)
                for variant in ('unfixed', 'fixed'):
                    for artifact in row.get(f'artifacts_{variant}', []):
                        for field in ('trace', 'hilog'):
                            value = artifact.get(field)
                            if value and not value.startswith(('http://', 'https://')):
                                raise RuntimeError(f'unpublished proof artifact reference: {value}')

        # Only purge after every data asset and the manifest are visible and
        # have the expected sizes (and API SHA-256 digests when provided).
        removed_bytes = 0
        for path in purge_paths:
            if path.exists() or path.is_symlink():
                if not path.is_symlink():
                    removed_bytes += path.stat().st_size
                path.unlink()
        for directory in sorted({p.parent for p in purge_paths}, key=lambda p: len(p.parts), reverse=True):
            try:
                directory.rmdir()
            except OSError:
                pass

    print(json.dumps({'release': f'https://github.com/{slug}/releases/tag/{args.tag}',
                      'published_artifacts': len(expected),
                      'new_assets': len(to_upload) + 1,
                      'omitted_empty_artifacts': len(empty_paths),
                      'removed_local_files': len(purge_paths),
                      'removed_regular_bytes': removed_bytes,
                      'manifest': str(doc)}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
