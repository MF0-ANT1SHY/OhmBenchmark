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
TARGET='/home/research/ohm-clean/services/weather_session'

def serve(host,duration):
    if not 60<=duration<=7200:raise ValueError('service duration must be between 60 and 7200 seconds')
    remote=Remote(host)
    remote.python("import socket\ntry:\n connection=socket.create_connection(('127.0.0.1',18494),timeout=2)\nexcept ConnectionRefusedError:pass\nelse:\n connection.close();raise RuntimeError('Port 18494 is already in use; existing service left unchanged')")
    for name in ('weather_session_data_service.py','weather_session_workstation_lease.py','workstation_process.py'):
        remote.upload(ROOT/'tools'/name,TARGET+'/'+name)
    remote.hdc(['rport','tcp:18494','tcp:18494'])
    print('Starting the bounded ordinary weather service on '+host+'; keep this command running.',flush=True)
    code="import subprocess,sys\nfrom pathlib import Path\nlauncher=Path(PAYLOAD['launcher']).resolve()\nsubprocess.run([sys.executable,'-X','utf8',str(launcher),'--duration',str(PAYLOAD['duration'])],check=True)"
    print(remote.python(code,{'launcher':TARGET+'/weather_session_workstation_lease.py','duration':duration},timeout=duration+60),flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--host',default='hkrc');parser.add_argument('--duration',type=int,default=7200);args=parser.parse_args();serve(args.host,args.duration)
