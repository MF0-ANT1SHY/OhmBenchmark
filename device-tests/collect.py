"""Collect three fresh-process runs of the real app's instrumented business path."""
import gzip, json, pathlib, subprocess, sys, time
ROOT = pathlib.Path(__file__).resolve().parents[1]
HDC = r'C:\Program Files (x86)\commandline-tools-windows-x64-5.1.1.840\command-line-tools\sdk\default\openharmony\toolchains\hdc.exe'
case, variant, bundle = sys.argv[1:4]
module = sys.argv[4] if len(sys.argv) > 4 else 'entry'
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
        if value.get('state')=='error': raise RuntimeError(value)
        time.sleep(.25)
    raise TimeoutError(f'{state}: {status()}')

for n in range(1,4):
    out = ROOT/'measurements'/case/variant/f'run{n}'
    out.mkdir(parents=True,exist_ok=True)
    sh(f'aa force-stop {bundle}')
    sh(f'rm -f {base}/ohm-status.json {base}/ohm-go')
    sh(f'aa start -a EntryAbility -b {bundle}')
    time.sleep(4)
    sh(f'aa start -a EntryAbility -b {bundle} --ps bench {case}')
    wait_state('ready')
    pid=sh(f'pidof {bundle}').split()[0]
    (out/'before.txt').write_text(sh(f'cat /proc/{pid}/stat; cat /proc/{pid}/status; cat /sys/class/thermal/thermal_zone0/temp'),encoding='utf-8')
    commands=[]
    for cmd in [
      f'hiperf record -p {pid} -f 1000 -e sw-cpu-clock -s fp -o /data/local/tmp/ohm-perf.data --control prepare',
      f'hiperf stat -p {pid} -e hw-cpu-cycles,hw-instructions,sw-task-clock,sw-context-switches -o /data/local/tmp/ohm-stat.txt --control prepare',
      'hitrace --trace_begin -b 65536 app sched disk distributeddatamgr ark',
      'hiperf record --control start', 'hiperf stat --control start']:
        commands.append(cmd+'\n'+sh(cmd))
    sh(f'touch {base}/ohm-go')
    result=wait_state('done')
    for cmd in ['hiperf stat --control stop','hiperf record --control stop','hitrace --trace_finish -o /data/local/tmp/ohm-trace.txt']:
        commands.append(cmd+'\n'+sh(cmd))
    (out/'after.txt').write_text(sh(f'cat /proc/{pid}/stat; cat /proc/{pid}/status'),encoding='utf-8')
    result.update(variant=variant,run=n,pid=int(pid),bundle=bundle)
    (out/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    (out/'capture.txt').write_text('\n'.join(commands),encoding='utf-8')
    for remote,local in [('ohm-perf.data','perf.data'),('ohm-stat.txt','perf-stat.txt'),('ohm-trace.txt','trace.txt')]:
        hdc('file','recv','/data/local/tmp/'+remote,str(out/local))
    with (out/'trace.txt').open('rb') as f, gzip.open(out/'trace.txt.gz','wb') as z: z.write(f.read())
    (out/'trace.txt').unlink()
    (out/'hilog.txt').write_text(sh(f'hilog -x -P {pid}'),encoding='utf-8')
    print(json.dumps(result),flush=True)
    time.sleep(2)
