#!/usr/bin/env python3
"""Compress old hitrace artifacts without breaking paths in proof.jsonl.

Each verified .chtrace.gz replaces the raw .chtrace with a symlink of the
original name. analyze.open_trace detects gzip content through that symlink.
Only finished case directories should be passed while a proof run is active.

Usage: python3 tools/device/compress_traces.py <case_id> [case_id ...]
"""
import argparse
import gzip
import hashlib
import os
from pathlib import Path

RESULTS = Path(__file__).resolve().parents[2] / 'results'


def digest_copy(src, dst):
    digest = hashlib.sha256()
    with src.open('rb') as source, gzip.open(dst, 'wb', compresslevel=3) as target:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
            target.write(chunk)
    return digest.digest()


def digest_gzip(path):
    digest = hashlib.sha256()
    with gzip.open(path, 'rb') as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.digest()


def compress(src):
    if src.is_symlink():
        return None
    dst = src.with_name(src.name + '.gz')
    if dst.exists():
        raise RuntimeError(f'compressed peer already exists: {dst}')
    temp = src.with_name(src.name + f'.gz.part.{os.getpid()}')
    link = src.with_name(src.name + f'.link.part.{os.getpid()}')
    raw_bytes = src.stat().st_size
    try:
        expected = digest_copy(src, temp)
        if digest_gzip(temp) != expected:
            raise RuntimeError(f'gzip verification failed: {src}')
        os.replace(temp, dst)
        link.symlink_to(dst.name)
        os.replace(link, src)
    finally:
        if temp.exists():
            temp.unlink()
        if link.exists() or link.is_symlink():
            link.unlink()
    return raw_bytes, dst.stat().st_size


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('cases', nargs='+')
    p.add_argument('--min-mb', type=int, default=50)
    args = p.parse_args()
    for case in args.cases:
        folder = RESULTS / case
        if not folder.is_dir():
            raise SystemExit(f'unknown case result directory: {folder}')
        for src in sorted(folder.glob('*.chtrace')):
            if src.is_symlink() or src.stat().st_size < args.min_mb * 1024 * 1024:
                continue
            raw, packed = compress(src)
            print(f'{case}/{src.name}: {raw:,} -> {packed:,} bytes')


if __name__ == '__main__':
    main()
