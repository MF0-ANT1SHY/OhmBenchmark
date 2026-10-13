"""Immutable, versioned production source references for clean case variants."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def source_entry(case, variant):
    host = case['host_app']['local_path'].split('/')[-1]
    metadata = json.loads((ROOT/'hosts_patches/host-reconstruction.json').read_text())
    return metadata['hosts'][host]['case_tags'][f"case/{case['id']}/{variant}"]


def app_ref(case, variant):
    return source_entry(case,variant).get('app_ref',f"clean-app/{case['id']}/{variant}")
