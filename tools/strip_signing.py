#!/usr/bin/env python3
"""Strip HarmonyOS signing configs from build-profile.json5 for headless builds.

Usage: python3 strip_signing.py <path-to-build-profile.json5>
Sets app.signingConfigs to [] and removes signingConfig references in
products/targets. Build-config only; does not touch app code.
"""
import re
import sys

def main(path: str) -> None:
    t = open(path).read()
    t2 = re.sub(r'"signingConfigs"\s*:\s*\[.*?\]\s*,\s*\n\s*"products"',
                '"signingConfigs": [],\n    "products"', t, flags=re.S)
    t2 = re.sub(r'"signingConfig"\s*:\s*"[^"]*"\s*,\s*\n', '', t2)
    t2 = re.sub(r',\s*\n(\s*)\]', r'\n\1]', t2)  # trailing comma cleanup
    open(path, 'w').write(t2)
    print(f"stripped signing from {path}")

if __name__ == '__main__':
    main(sys.argv[1])
