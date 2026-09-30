import gzip,json,pathlib,subprocess,sys,time
root=pathlib.Path(__file__).resolve().parents[1]
hdc=r'C:\Program Files (x86)\commandline-tools-windows-x64-5.1.1.840\command-line-tools\sdk\default\openharmony\toolchains\hdc.exe'
variant=sys.argv[1];bundle='com.example.nanvision';case='browser_eager_history_load'
base=f'/data/app/el2/100/base/{bundle}/haps/entry/files'
def sh(cmd):return subprocess.check_output([hdc,'shell',cmd],timeout=90).decode('utf-8',errors='replace')
def recv(remote,local):subprocess.run([hdc,'file','recv',remote,str(local)],check=True,stdout=subprocess.DEVNULL)
# Populate the same 10,000 history records once, outside all captured launches.
sh(f'aa force-stop {bundle}');sh(f'aa start -a EntryAbility -b {bundle}');time.sleep(12)
sh(f'rm -f {base}/ohm-status.json {base}/ohm-go')
sh(f'aa start -a EntryAbility -b {bundle} --ps bench {case}')
for i in range(240):
    s=sh(f'cat {base}/ohm-status.json')
    if '"ready"' in s:break
    if '"error"' in s:raise RuntimeError(s)
    time.sleep(.5)
else:raise TimeoutError('seed')
sh(f'touch {base}/ohm-go');time.sleep(1)
for n in range(1,4):
    out=root/'measurements'/case/variant/f'run{n}';out.mkdir(parents=True,exist_ok=True)
    sh(f'aa force-stop {bundle}');time.sleep(2)
    capture=[sh('hitrace --trace_begin -b 65536 app sched disk distributeddatamgr ark ace')]
    rec=subprocess.Popen([hdc,'shell',f'hiperf record --app {bundle} -d 12 -f 1000 -e sw-cpu-clock -s fp -o /data/local/tmp/ohm-perf.data'],stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    stat=subprocess.Popen([hdc,'shell',f'hiperf stat --app {bundle} -d 12 -e hw-cpu-cycles,hw-instructions,sw-task-clock,sw-context-switches'],stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    time.sleep(.5)
    capture.append(sh(f'aa start -a EntryAbility -b {bundle}'))
    pid=int(sh(f'pidof {bundle}').strip().split()[0]);time.sleep(11)
    capture.append(sh('hitrace --trace_finish -o /data/local/tmp/ohm-trace.txt'))
    capture.append(rec.communicate(timeout=60)[0].decode('utf-8',errors='replace'))
    (out/'perf-stat.txt').write_text(stat.communicate(timeout=30)[0].decode('utf-8',errors='replace'),encoding='utf-8')
    recv('/data/local/tmp/ohm-perf.data',out/'perf.data');recv('/data/local/tmp/ohm-trace.txt',out/'trace.txt')
    with (out/'trace.txt').open('rb') as f,gzip.open(out/'trace.txt.gz','wb') as z:z.write(f.read())
    (out/'trace.txt').unlink()
    sh('snapshot_display -f /data/local/tmp/ohm-screen.jpeg');recv('/data/local/tmp/ohm-screen.jpeg',out/'ui-after.jpeg')
    sh('uitest dumpLayout -p /data/local/tmp/ohm-layout.json');recv('/data/local/tmp/ohm-layout.json',out/'ui-after.json')
    (out/'hilog.txt').write_text(sh(f'hilog -x -P {pid}'),encoding='utf-8')
    (out/'capture.txt').write_text('\n'.join(capture),encoding='utf-8')
    result=dict(state='done',case=case,variant=variant,run=n,pid=pid,bundle=bundle,elapsed_ms=10000,result=10000,metric='CPU in 10-second startup window, not completion latency')
    (out/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result),flush=True)
