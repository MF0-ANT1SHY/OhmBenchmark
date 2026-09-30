from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path
import json
from run_harness import run,B
cases=sorted(p.name for p in (B/'blind').glob('C*'))
with ThreadPoolExecutor(max_workers=3) as pool:
    tasks=[pool.submit(run,h,c) for c in cases for h in ['opencode','claude','dsh']]
    for f in as_completed(tasks):
        try:f.result()
        except Exception as e:print(type(e).__name__,str(e)[:300],flush=True)
print('Matrix finished',flush=True)
