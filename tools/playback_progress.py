"""Validate ordinary player progress from external accessibility snapshots."""
import math

from ui_driver import UI


def check_progress(start_layout, end_layout, bundle, elapsed_s):
    def position(layout):
        sliders = [n for n in UI.nodes(layout)
                   if n.get('bundleName') == bundle and n.get('type') == 'Slider'
                   and n.get('visible') != 'false']
        if len(sliders) != 1:
            raise ValueError('a unique app playback slider is required')
        value = float(sliders[0]['text'])
        if not math.isfinite(value) or value < 0:
            raise ValueError('invalid playback position')
        return value

    if not math.isfinite(elapsed_s) or elapsed_s < 20:
        raise ValueError('playback observation is too short')
    start, end = position(start_layout), position(end_layout)
    advance = end - start
    if not elapsed_s * 700 <= advance <= elapsed_s * 1300 + 5000:
        raise ValueError('playback progress did not advance with elapsed time')
    return {'start_position_ms': start, 'end_position_ms': end,
            'elapsed_s': elapsed_s, 'advanced_ms': advance}
