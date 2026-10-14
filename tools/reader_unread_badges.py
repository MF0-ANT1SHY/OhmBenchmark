"""Read ordinary per-feed unread badges from the native accessibility tree."""
import re
import time

BUNDLE = 'com.sheafreader.hm'
CASE = 'sheafreader_unread_counts_n_plus_1'


def badge_rows(layout):
    def walk(node, inherited=None):
        attrs = node.get('attributes', {})
        bundle = attrs.get('bundleName') or inherited
        if attrs.get('type') == 'Row' and bundle == BUNDLE and attrs.get('visible') != 'false':
            # SidebarView has title/count Text siblings directly in its Row.
            # Article cards also show the feed title, but pair it with an age
            # (e.g. 13d) and are not unread badges.
            texts = [child.get('attributes', {}).get('text', '') for child in node.get('children', [])
                     if child.get('attributes', {}).get('type') == 'Text'
                     and (child.get('attributes', {}).get('bundleName') or bundle) == BUNDLE
                     and child.get('attributes', {}).get('visible') != 'false']
            feeds = [x for x in texts if re.fullmatch(r'Journal (?:[1-9]|10)', x)]
            values = [int(x) for x in texts if x.isdigit()]
            if len(feeds) == 1 and values:
                yield feeds[0], values
        for child in node.get('children', []):
            yield from walk(child, bundle)
    yield from walk(layout)


def verify_layout(layout):
    observed = {}
    for feed, values in badge_rows(layout):
        if values != [100]:
            raise ValueError('ordinary feed badge does not show its 100 unread articles')
        if feed in observed:
            raise ValueError('ambiguous duplicate feed badge')
        observed[feed] = values[0]
    expected = {f'Journal {i}': 100 for i in range(1, 11)}
    if observed != expected:
        raise ValueError('all ten ordinary feed unread badges are not visible')
    return observed


def complete_badges(ui, timeout=120):
    started = time.monotonic()
    layout = ui.layout()
    if not list(badge_rows(layout)):
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
