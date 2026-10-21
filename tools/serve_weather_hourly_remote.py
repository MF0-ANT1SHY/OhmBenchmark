#!/usr/bin/env python3
"""Run the ordinary ten-city weather fixture on the device's HDC workstation.

Keep this foreground command running during collection or agent reproduction.
It refuses an occupied port and never stops an existing process. The service
expires after the requested bounded lease; all receipts remain outside the app.
"""
import argparse
from pathlib import Path
from remote_device import Remote
ROOT=Path(__file__).resolve().parents[1]
TARGET='/home/research/ohm-clean/services/weather_hourly'

def serve(host,duration):
    if not 60<=duration<=7200:raise ValueError('service duration must be between 60 and 7200 seconds')
    remote=Remote(host)
    remote.python("import socket\nwith socket.socket() as probe:\n if hasattr(socket,'SO_EXCLUSIVEADDRUSE'):probe.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)\n probe.bind(('127.0.0.1',18496))")
    for name in ('weather_session_data_service.py','weather_hourly_data_service.py','weather_hourly_workstation_lease.py','workstation_process.py'):
        remote.upload(ROOT/'tools'/name,TARGET+'/'+name)
    remote.hdc(['rport','tcp:18496','tcp:18496'])
    print('Starting the bounded ordinary weather service on '+host+'; keep this command running.',flush=True)
    code="import subprocess,sys\nfrom pathlib import Path\nlauncher=Path(PAYLOAD['launcher']).resolve()\nsubprocess.run([sys.executable,'-X','utf8',str(launcher),'--duration',str(PAYLOAD['duration'])],check=True)"
    print(remote.python(code,{'launcher':TARGET+'/weather_hourly_workstation_lease.py','duration':duration},timeout=duration+60),flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--host',default='hkrc');parser.add_argument('--duration',type=int,default=7200);args=parser.parse_args();serve(args.host,args.duration)
