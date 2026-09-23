"""Common helpers for driving the HarmonyOS device over hdc.

Everything here is intentionally dependency-free (stdlib only) so the runner
works on a bare macOS + command-line-tools setup.
"""
import json
import os
import re
import subprocess
import time

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HDC = os.path.expanduser('~/.local/bin/command-line-tools/sdk/default/openharmony/toolchains/hdc')
BUNDLE = json.load(open(os.path.join(REPO, 'tools', '.sign_material.json')))['bundle']

_screen = None


def hdc(*args, timeout=60, check=False):
    r = subprocess.run([HDC, *args], capture_output=True, text=True, timeout=timeout)
    if check and r.returncode != 0:
        raise RuntimeError(f'hdc {args} failed: {r.stdout} {r.stderr}')
    return (r.stdout + r.stderr).strip()


def shell(cmd, timeout=60):
    return hdc('shell', cmd, timeout=timeout)


def uninstall(b=None):
    b = b or BUNDLE
    shell(f'bm uninstall -n {b}')


def install(hap_path, replace=True):
    args = ['install', '-r' if replace else '-n', hap_path]
    out = hdc(*args, timeout=300)
    ok = 'successfully' in out.lower() or 'install bundle successfully' in out.lower()
    if not ok:
        raise RuntimeError(f'install failed: {out}')
    return out


def screen_size():
    global _screen
    if _screen is None:
        out = shell('hidumper -s RenderService -a screen')
        m = re.search(r'activeMode:\s*(\d+)x(\d+)', out) or re.search(r'(\d+)x(\d+)', out)
        _screen = (int(m.group(1)), int(m.group(2))) if m else (1260, 2844)
    return _screen


def ability_of(host_dir):
    """Return the launcher ability name parsed from any module.json5."""
    cands = []
    for root, dirs, files in os.walk(host_dir):
        dirs[:] = [d for d in dirs if d not in ('oh_modules', 'node_modules', '.git', 'build', 'ohosTest')]
        if 'module.json5' in files and 'ohosTest' not in root:
            cands.append(os.path.join(root, 'module.json5'))
    entry = [c for c in cands if '/entry/' in c] or cands
    if not entry:
        raise RuntimeError(f'no module.json5 under {host_dir}')
    txt = open(entry[0]).read()
    m = re.search(r'"mainElement"\s*:\s*"([^"]+)"', txt)
    if not m:
        m = re.search(r'"name"\s*:\s*"(EntryAbility|[^"]*Ability)"', txt)
    if not m:
        raise RuntimeError(f'no mainElement in {entry[0]}')
    return m.group(1)


def launch(ability=None, bundle=None):
    ability = ability or 'EntryAbility'
    return shell(f'aa start -a {ability} -b {bundle or BUNDLE}')


def force_stop(bundle=None):
    shell(f'aa force-stop {bundle or BUNDLE}')


def pid(bundle=None):
    out = shell(f'pidof {bundle or BUNDLE}')
    m = re.search(r'\d+', out)
    return int(m.group()) if m else None


def wait_pid(timeout=20, bundle=None):
    t0 = time.time()
    while time.time() - t0 < timeout:
        p = pid(bundle)
        if p:
            return p
        time.sleep(0.5)
    return None


def dump_layout(path='/data/local/tmp/layout.json', bundle=None):
    shell(f'rm -f {path}; uitest dumpLayout -p {path}')
    local = '/tmp/ohb_layout.json'
    hdc('file', 'recv', path, local)
    try:
        return json.load(open(local))
    except Exception:
        return None


def _iter_nodes(node):
    yield node
    for c in node.get('children') or []:
        yield from _iter_nodes(c)


def find_nodes(root, text=None, contains=None, type_=None, id_=None, clickable=None, bounds=None):
    """Find widget nodes matching given attributes. `bounds` filters to nodes
    whose center is inside given (l,t,r,b)."""
    if root is None:
        return []
    out = []
    for n in _iter_nodes(root):
        a = n.get('attributes', n)
        if text is not None and a.get('text') != text:
            continue
        if contains is not None and contains not in (a.get('text') or '') + (a.get('originalText') or '') + (a.get('description') or '') + (a.get('hint') or ''):
            continue
        if type_ is not None and a.get('type') != type_:
            continue
        if id_ is not None and id_ not in (a.get('id') or ''):
            continue
        if clickable is not None and str(a.get('clickable')).lower() != ('true' if clickable else 'false'):
            continue
        out.append(n)
    if bounds:
        l, t, r, b = bounds
        out = [n for n in out if _center(n) and l <= _center(n)[0] <= r and t <= _center(n)[1] <= b]
    return out


def _bounds(n):
    a = n.get('attributes', n)
    b = a.get('bounds') or ''
    m = re.match(r'\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]', b)
    if not m:
        return None
    return tuple(int(x) for x in m.groups())


def _center(n):
    b = _bounds(n)
    if not b:
        return None
    return ((b[0] + b[2]) // 2, (b[1] + b[3]) // 2)


def tap(x, y):
    shell(f'uitest uiInput click {int(x)} {int(y)}')


def tap_node(n):
    c = _center(n)
    if not c:
        raise RuntimeError('node without bounds')
    tap(*c)
    return c


def tap_text(text=None, contains=None, type_=None, timeout=15, root_refresh=None, **kw):
    """Dump layout until a matching widget appears, tap it, return the node."""
    t0 = time.time()
    while time.time() - t0 < timeout:
        root = root_refresh() if root_refresh else dump_layout()
        nodes = find_nodes(root, text=text, contains=contains, type_=type_, **kw)
        if nodes:
            tap_node(nodes[0])
            return nodes[0]
        time.sleep(1)
    raise TimeoutError(f'widget text={text} contains={contains} not found in {timeout}s')


def input_text_at(x, y, text):
    """Type `text` at (x, y). Works from any state: with the IME already up a
    bare `inputText` re-click cancels editing, so tap to focus then `uiInput
    text` into the focused node; from a clean state the tap just refocuses."""
    tap(x, y)
    time.sleep(0.8)
    shell(f'uitest uiInput text {text}')


def key(code):
    shell(f'uitest uiInput keyEvent {code}')


def swipe(x1, y1, x2, y2, velocity=600):
    shell(f'uitest uiInput swipe {int(x1)} {int(y1)} {int(x2)} {int(y2)} {velocity}')


def fling_up(velocity=2000, step=None):
    w, h = screen_size()
    step = f' {step}' if step else ''
    shell(f'uitest uiInput dircFling 2 {velocity}{step}')


def fling_down(velocity=2000, step=None):
    w, h = screen_size()
    step = f' {step}' if step else ''
    shell(f'uitest uiInput dircFling 3 {velocity}{step}')


def screenshot(local_path):
    shell('uitest screenCap -p /data/local/tmp/ohb_cap.png')
    hdc('file', 'recv', '/data/local/tmp/ohb_cap.png', local_path)


def hitrace_start(categories, seconds, remote='/data/local/tmp/ohb.chtrace', buffering=None):
    """Async hitrace: launch in background on device, returns immediately.
    Uses `hitrace -t <sec> ...` which self-terminates."""
    cmd = f'hitrace -t {seconds} {" ".join(categories)} -o {remote}'
    subprocess.Popen([HDC, 'shell', cmd], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(0.5)


def hitrace_wait_pull(remote, local, timeout=180):
    t0 = time.time()
    while time.time() - t0 < timeout:
        out = shell(f'ls -l {remote}')
        if re.search(r'\d{6,}', out):  # file larger than ~100KB? just check exists+mtime stable
            time.sleep(1)
            out2 = shell(f'ls -l {remote}')
            if out == out2:
                break
        time.sleep(2)
    hdc('file', 'recv', remote, local)
    return local


def hilog(bundle=None, lines=200):
    return shell(f'hilog -x | grep -i "{bundle or BUNDLE}" | tail -{lines}')[0:100]


def clean_appdata():
    shell(f'bm clean -n {BUNDLE} -d')


def device_ready():
    return bool(re.search(r'^[0-9A-F]{20,}$', hdc('list', 'targets'), re.M))


_MONTHS = {'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6,
           'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12}

_REAL_TIME = {'date': None}


def device_date():
    """Return device (year, month, day, hh, mm, ss)."""
    out = shell('date')
    m = re.search(r'\w{3} (\w{3}) +(\d+) (\d{2}):(\d{2}):(\d{2}).*?(\d{4})', out)
    if not m:
        raise RuntimeError(f'cannot parse device date: {out!r}')
    return (int(m.group(6)), _MONTHS[m.group(1)], int(m.group(2)),
            int(m.group(3)), int(m.group(4)), int(m.group(5)))


def set_device_date(days_ago=0, keep_real=False):
    """Rewrite the device date (hdc shell is root) keeping time-of-day.
    keep_real=True snapshots the real date for a later restore()."""
    y, mo, d, hh, mm, ss = device_date()
    if keep_real:
        _REAL_TIME['date'] = (y, mo, d, hh, mm, ss)
    import datetime
    dt = datetime.datetime(y, mo, d) - datetime.timedelta(days=days_ago)
    shell(f'date {dt.month:02d}{dt.day:02d}{hh:02d}{mm:02d}{dt.year}.{ss}')
    return shell('date')


def restore_device_date():
    if not _REAL_TIME['date']:
        return set_device_date(0)
    y, mo, d, hh, mm, ss = _REAL_TIME['date']
    shell(f'date {mo:02d}{d:02d}{hh:02d}{mm:02d}{y}.{ss}')
    return shell('date')


def run_uitest(suite_method, timeout=300):
    """Run a Hypium UI test on device, e.g. run_uitest('ActsOhbBrowser#seed6').
    The test runner relaunches the ability, so force-stop first to guarantee a
    clean single-instance state (dialogs/tab state do not survive). Blocking;
    returns combined stdout (contains OHB markers + OHOS_REPORT)."""
    force_stop()
    time.sleep(1)
    module = 'entry_test'
    out = hdc('shell', 'aa test -b ' + BUNDLE + f' -m {module} -s unittest '
              f'/ets/testrunner/OpenHarmonyTestRunner -s class {suite_method} '
              f'-s timeout {timeout * 1000}', timeout=timeout + 60)
    return out
