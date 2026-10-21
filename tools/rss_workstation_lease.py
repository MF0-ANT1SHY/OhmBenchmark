"""Host ordinary RSS responses with declared server latency on either OS."""
import argparse
import hashlib
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import threading
import time

from rss_data_service import Catalogue, handler
from workstation_process import identity


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--duration', type=int, default=7200)
    p.add_argument('--delay', type=float, default=1.5)
    p.add_argument('--body-bytes', type=int, default=256)
    args = p.parse_args()
    if not 60 <= args.duration <= 7200 or not 0 <= args.delay <= 5:
        raise ValueError('invalid service lease or response delay')
    base = Path(__file__).resolve().parent
    catalogue = Catalogue('http://127.0.0.1:18491', body_bytes=args.body_bytes)
    ordinary = handler(catalogue)
    log_lock = threading.Lock()
    class Handler(ordinary):
        def do_GET(self):
            start = time.monotonic()
            if self.path.startswith('/feeds/'):
                time.sleep(args.delay)
            try:
                super().do_GET()
            finally:
                row = {'path': self.path, 'start': start, 'end': time.monotonic()}
                with log_lock, (base / 'requests.jsonl').open('a', encoding='utf8') as log:
                    log.write(json.dumps(row) + '\n')
    # Bind first. An occupied port fails without stopping the existing server.
    server = ThreadingHTTPServer(('127.0.0.1', 18491), Handler)
    source = base / 'rss_data_service.py'
    launcher = Path(__file__).resolve()
    record = {'pid': os.getpid(), 'source': str(source), 'launcher': str(launcher),
              'launcher_sha256': hashlib.sha256(launcher.read_bytes()).hexdigest(),
              'base_url': catalogue.base, 'feeds': 10, 'articles_per_feed': 100,
              'body_bytes': args.body_bytes, 'network_delay_s': args.delay,
              'identity': identity(os.getpid()), 'hosting': 'bounded foreground SSH lease'}
    (base / 'process.json').write_text(json.dumps(record, indent=2), encoding='utf8')
    timer = threading.Timer(args.duration, server.shutdown)
    timer.daemon = True; timer.start()
    print('Owned RSS source ready', flush=True)
    try:
        server.serve_forever()
    finally:
        timer.cancel(); server.server_close()


if __name__ == '__main__':
    main()
