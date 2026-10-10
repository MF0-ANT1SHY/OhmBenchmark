import json,glob,os
for d in sorted(glob.glob('measurements-staging/*/')):
    cid=os.path.basename(d.rstrip('/'))
    try:
        c=json.load(open(f'cases/{cid}/case.json'))
        st=c['test_oracle']['evidence']['status']
    except Exception as e:
        st='NO-CASE'
    n=len(glob.glob(d+'**/perf-stat.txt',recursive=True))
    r=len(glob.glob(d+'**/result.json',recursive=True))
    print(f'{st:<11} perf-stat={n:<3} result={r:<3} {cid}')
