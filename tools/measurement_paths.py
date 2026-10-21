"""Keep revised measurements separate from immutable earlier raw trials."""
import re


def capture_root(folder, case, metric):
    name = {'app_pss_bytes': 'pss-captures', 'hiperf_instructions': 'cpu-captures',
            'trace_cpu_ms': 'trace-captures', 'startup_refresh_elapsed_s': 'trace-captures'}[metric]
    root = folder/name
    revision = case.get('measurement_revision')
    if revision is not None:
        if not isinstance(revision, str) or not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,63}', revision):
            raise ValueError('measurement revision must be a safe directory name')
        root = root/revision
    return root
