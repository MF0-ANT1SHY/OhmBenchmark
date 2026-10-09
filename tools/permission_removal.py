#!/usr/bin/env python3
"""Remove an entry from a HarmonyOS `requestPermissions` array, safely.

Cutting the entry by matching braces is necessary because JSON5 spacing defeats a fixed regex -
a rigid pattern silently failed to match on one case and the permission stayed in place. The
comma handling is what a naive brace cut gets wrong: the separator can sit before or after the
entry, and leaving either produces invalid JSON5.

Used by both cloudmusic instrumenters so the two cannot drift.
"""
import re


def remove_request_permission(text: str, name: str) -> str:
    """Return `text` with the requestPermissions entry named `name` removed."""
    key = f'"{name}"'
    i = text.find(key)
    if i == -1:
        return text

    start = text.rfind('{', 0, i)
    if start == -1:
        return text
    depth = 0
    end = None
    for j in range(start, len(text)):
        if text[j] == '{':
            depth += 1
        elif text[j] == '}':
            depth -= 1
            if depth == 0:
                end = j + 1
                break
    if end is None:
        return text

    # consume a following comma, and any whitespace that preceded the entry, so no stray
    # separator is left behind
    after = text[end:]
    m = re.match(r'[ \t]*,[ \t]*\n?', after)
    if m:
        end += m.end()
    else:
        # no trailing comma: the comma must be before the entry
        before = text[:start]
        m2 = re.search(r',[ \t]*\n?[ \t]*$', before)
        if m2:
            start = m2.start()
            # keep the line break that separated the entries
            start = start + (1 if text[start:start + 1] == ',' else 0)

    out = text[:start] + text[end:]
    # collapse any ',]' or ',}' that the removal exposed
    out = re.sub(r',(\s*[\]}])', r'\1', out)
    return out
