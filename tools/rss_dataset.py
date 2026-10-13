"""Ordinary RSS article sizes, declared outside the application."""
import json
from pathlib import Path

DEFAULT = {'body_bytes': 32768}


def normalize(dataset=None):
    result = dict(DEFAULT if dataset is None else dataset)
    if set(result) != {'body_bytes'}:
        raise ValueError('RSS dataset must declare only its ordinary article body size')
    size = result['body_bytes']
    if type(size) is not int or not 1 <= size <= 40000:
        raise ValueError('RSS article size must fit the ordinary 100-article HTTP response limit')
    return result


def for_fixture(fixture):
    path = Path(fixture).with_suffix('.dataset.json')
    return normalize(json.loads(path.read_text()) if path.exists() else None)
