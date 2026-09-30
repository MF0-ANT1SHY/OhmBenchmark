"""Collect three fresh-process runs of the real app's instrumented business path."""
import gzip, json, pathlib, subprocess, sys, time
ROOT = pathlib.Path(__file__).resolve().parents[1]
HDC = r'C:\Program Files (x86)\commandline-tools-windows-x64-5.1.1.840\command-line-tools\sdk\default\openharmony\toolchains\hdc.exe'
case, variant, bundle = sys.argv[1:4]
module = sys.argv[4] if len(sys.argv) > 4 else 'entry'
ability = sys.argv[5] if len(sys.argv) > 5 else 'EntryAbility'
base = f'/data/app/el2/100/base/{bundle}/haps/{module}/files'
def hdc(*args):
    return subprocess.check_output([HDC,*args],timeout=90).decode('utf-8',errors='replace').strip()
def sh(cmd): return hdc('shell',cmd)
def status():
    try: return json.loads(sh(f'cat {base}/ohm-status.json'))
    except (ValueError,subprocess.SubprocessError): return {}
def wait_state(state, seconds=180):
    until = time.monotonic()+seconds
    while time.monotonic()<until:
        value=status()
        if value.get('state')==state: return value
        if value.get('state')=='error':
            (out/'error.json').write_text(json.dumps(value),encoding='utf-8')
            raise RuntimeError(str(value)[:500])
        time.sleep(.25)
    raise TimeoutError(f'{state}: {status()}')

for n in range(1,4):
    out = ROOT/'measurements'/case/variant/f'run{n}'
    out.mkdir(parents=True,exist_ok=True)
    sh(f'aa force-stop {bundle}')
    sh(f'rm -f {base}/ohm-status.json {base}/ohm-go')
    sh(f'aa start -a {ability} -b {bundle}')
    time.sleep(4)
    sh(f'aa start -a {ability} -b {bundle} --ps bench {case}')
    wait_state('ready')
    sh('uitest dumpLayout -p /data/local/tmp/ohm-layout.json')
    hdc('file','recv','/data/local/tmp/ohm-layout.json',str(out/'ui-before.json'))
    layout=json.loads((out/'ui-before.json').read_text(encoding='utf-8'))
    pending=[layout]; texts=[]
    while pending:
        node=pending.pop(); attrs=node.get('attributes',{})
        texts.append(attrs.get('text',''));pending.extend(node.get('children',[]))
    if any(t in ['不允许','允许本次','仅使用时允许'] or ('允许' in t and '通知' in t) for t in texts):
        raise RuntimeError('Permission dialog present; resolve on phone before collecting')
    sh('snapshot_display -f /data/local/tmp/ohm-screen.jpeg')
    hdc('file','recv','/data/local/tmp/ohm-screen.jpeg',str(out/'ui-before.jpeg'))
    pid=sh(f'pidof {bundle}').split()[0]
    if case=='weatherassistant_http_session_leak':
        fd_before=int(sh(f'ls /proc/{pid}/fd | wc -l'))
        (out/'fd-before.txt').write_text(sh(f'ls -l /proc/{pid}/fd'),encoding='utf-8')
    (out/'before.txt').write_text(sh(f'cat /proc/{pid}/stat; cat /proc/{pid}/status; cat /sys/class/thermal/thermal_zone0/temp'),encoding='utf-8')
    commands=[]
    for cmd in [
      f'hiperf record -p {pid} -f 1000 -e sw-cpu-clock -s fp -o /data/local/tmp/ohm-perf.data --control prepare',
      f'hiperf stat -p {pid} -e hw-cpu-cycles,hw-instructions,sw-task-clock,sw-context-switches -o /data/local/tmp/ohm-stat.txt --control prepare',
      'hitrace --trace_begin -b 65536 app sched disk distributeddatamgr ark'+(' ace graphic' if case=='sheafreader_article_list_foreach' else ''),
      'hiperf record --control start', 'hiperf stat --control start']:
        commands.append(cmd+'\n'+sh(cmd))
    sh(f'touch {base}/ohm-go')
    if case=='sheafreader_article_list_foreach':
        time.sleep(2)
        for swipe in range(3):
            sh('uitest uiInput swipe 630 2300 630 850 800')
            time.sleep(.5)
    result=wait_state('done')
    if case=='sheafreader_article_list_foreach':
        result['metric']='CPU and component appearances in 10-second UI update/scroll window, not completion latency'
    for cmd in ['hiperf stat --control stop','hiperf record --control stop','hitrace --trace_finish -o /data/local/tmp/ohm-trace.txt']:
        commands.append(cmd+'\n'+sh(cmd))
    (out/'after.txt').write_text(sh(f'cat /proc/{pid}/stat; cat /proc/{pid}/status'),encoding='utf-8')
    result.update(variant=variant,run=n,pid=int(pid),bundle=bundle)
    if case=='weatherassistant_http_session_leak':
        result.update(fd_before=fd_before,fd_after=int(sh(f'ls /proc/{pid}/fd | wc -l')))
        (out/'fd-after.txt').write_text(sh(f'ls -l /proc/{pid}/fd'),encoding='utf-8')
    (out/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    (out/'capture.txt').write_text('\n'.join(commands),encoding='utf-8')
    for remote,local in [('ohm-perf.data','perf.data'),('ohm-stat.txt','perf-stat.txt'),('ohm-trace.txt','trace.txt')]:
        hdc('file','recv','/data/local/tmp/'+remote,str(out/local))
    with (out/'trace.txt').open('rb') as f, gzip.open(out/'trace.txt.gz','wb') as z: z.write(f.read())
    (out/'trace.txt').unlink()
    (out/'hilog.txt').write_text(sh(f'hilog -x -P {pid}'),encoding='utf-8')
    sh('snapshot_display -f /data/local/tmp/ohm-screen.jpeg')
    hdc('file','recv','/data/local/tmp/ohm-screen.jpeg',str(out/'ui-after.jpeg'))
    print(json.dumps(result),flush=True)
    time.sleep(2)
