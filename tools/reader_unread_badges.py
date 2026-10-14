"""Read ordinary per-feed unread badges from the native accessibility tree."""
import re
import time

from ui_driver import UI

BUNDLE = 'com.sheafreader.hm'
CASE = 'sheafreader_unread_counts_n_plus_1'


def verify_layout(layout):
    observed = {}
    def walk(node, inherited=None):
        attrs = node.get('attributes', {})
        bundle = attrs.get('bundleName') or inherited
        if attrs.get('type') == 'Row' and bundle == BUNDLE and attrs.get('visible') != 'false':
            texts = [n.get('text', '') for child in node.get('children', [])
                     for n in UI.nodes(child, bundle)
                     if n.get('bundleName') == BUNDLE and n.get('visible') != 'false']
            feeds = [x for x in texts if re.fullmatch(r'Journal (?:[1-9]|10)', x)]
            if len(feeds) == 1:
                values = [int(x) for x in texts if x.isdigit()]
                if values != [100]:
                    raise ValueError('ordinary feed badge does not show its 100 unread articles')
                if feeds[0] in observed:
                    raise ValueError('ambiguous duplicate feed badge')
                observed[feeds[0]] = values[0]
        for child in node.get('children', []):
            walk(child, bundle)
    walk(layout)
    expected = {f'Journal {i}': 100 for i in range(1, 11)}
    if observed != expected:
        raise ValueError('all ten ordinary feed unread badges are not visible')
    return observed


def complete_badges(ui, timeout=120):
    started = time.monotonic()
    layout = ui.layout()
    names = {n.get('text') for n in UI.nodes(layout)
             if n.get('bundleName') == BUNDLE and n.get('visible') != 'false'}
    if 'Journal 1' not in names:
        # Normal F1 sidebar shortcut, verified in the host source and SDK enum.
        ui.run([{'op': 'key', 'key': 2090}])
    deadline = time.monotonic() + timeout
    while True:
        layout = ui.layout()
        try:
            counts = verify_layout(layout)
            return {'layout': layout, 'counts': counts, 'started_monotonic': started,
                    'ended_monotonic': time.monotonic()}
        except ValueError as exc:
            if time.monotonic() >= deadline:
                exc.observation = {'layout': layout}
                raise
            time.sleep(.5)
