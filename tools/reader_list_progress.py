"""Verify normal reader launch and article rendering, without app probes."""
import re
import time

from ui_driver import UI

CASE = 'sheafreader_article_list_foreach'
BUNDLE = 'com.sheafreader.hm'
ARTICLE = r'Journal (?:[1-9]|10) article (?:[1-9][0-9]?|100)'
COUNT = r'300 (?:篇|articles)'


def observe(ui):
    started = time.monotonic()
    pid = ui.shell('pidof ' + BUNDLE).strip()
    if not pid.isdigit():
        raise ValueError('one live reader process is required')
    return {'pid': int(pid), 'layout': ui.layout(), 'started_monotonic': started,
            'ended_monotonic': time.monotonic()}


def verify_render(state):
    if not 0 < state['started_monotonic'] <= state['ended_monotonic']:
        raise ValueError('invalid article rendering observation window')
    texts = [n.get('text', '') for n in UI.nodes(state['layout'])
             if n.get('bundleName') == BUNDLE and n.get('visible') != 'false']
    if not any(re.fullmatch(COUNT, t) for t in texts):
        raise ValueError('normal loaded page of 300 articles is not visible')
    articles = [t for t in texts if re.fullmatch(ARTICLE, t)]
    if not articles:
        raise ValueError('ordinary article titles are not rendered')
    return {'loaded_articles': 300, 'visible_article_titles': sorted(set(articles))}


def complete_render(ui, before, timeout=120):
    ui.find({'text': COUNT, 'match': 'regex'}, timeout)
    ui.find({'text': ARTICLE, 'match': 'regex'}, timeout)
    after = observe(ui)
    observation = {'before': before, 'after': after}
    observation['progress'] = verify_observation(observation)
    return observation


def verify_observation(observation):
    before, after = observation['before'], observation['after']
    verify_render(before)
    rendered = verify_render(after)
    if before['pid'] == after['pid'] or before['ended_monotonic'] >= after['started_monotonic']:
        raise ValueError('fresh normal reader launch is not proven')
    return {'method': 'fresh app process renders the ordinary 300-article first page', **rendered}


def verify_capture(observation, started, ended, pids):
    progress = verify_observation(observation)
    if (observation['before']['ended_monotonic'] > started
            or observation['after']['started_monotonic'] < started
            or observation['after']['ended_monotonic'] > ended
            or observation['after']['pid'] not in pids):
        raise ValueError('new reader process rendering is outside the attributed capture')
    if observation.get('progress') != progress:
        raise ValueError('render summary differs from raw native UI evidence')
    return progress
