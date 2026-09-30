"""Render the captured native sample profiles with the device's own hiperf."""
import pathlib,subprocess
root=pathlib.Path(__file__).resolve().parents[1]
hdc=r'C:\Program Files (x86)\commandline-tools-windows-x64-5.1.1.840\command-line-tools\sdk\default\openharmony\toolchains\hdc.exe'
def run(*args):
    return subprocess.check_output([hdc,*args],timeout=90).decode('utf-8',errors='replace')
for data in sorted((root/'measurements').glob('*/*/run*/perf.data')):
    output=data.with_name('perf-report.txt')
    if output.exists() and output.stat().st_size:continue
    run('file','send',str(data),'/data/local/tmp/ohm-profile.data')
    result=run('shell','hiperf report -i /data/local/tmp/ohm-profile.data --sort comm,dso,func --limit-percent 1 -o /data/local/tmp/ohm-profile.txt')
    if 'report done' not in result:raise RuntimeError(result)
    run('file','recv','/data/local/tmp/ohm-profile.txt',str(output))
    print(str(output.relative_to(root)),flush=True)
