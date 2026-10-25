#!/usr/bin/env python3
import ipaddress
import json
import os
import subprocess
import time

def fetch(path):
    args=['curl','--fail','--silent','--show-error','--max-time','10','--noproxy','*',
          '-H','Cache-Control: no-cache']
    origin=os.environ.get('DEPLOY_ORIGIN_IP','')
    if origin:
        address=ipaddress.ip_address(origin)
        value=f'[{address}]' if address.version==6 else str(address)
        args += ['--resolve',f'www.jake.ac:443:{value}']
    return subprocess.check_output(args+['https://www.jake.ac'+path],timeout=15)

deadline=time.monotonic()+600
while time.monotonic()<deadline:
    try:
        state=json.loads(fetch('/__deployment'))
        if (state.get('image')==os.environ['DEPLOY_IMAGE'] and
                state.get('revision')==os.environ['DEPLOY_REVISION']):
            homepage=fetch('/')
            assert b'<html' in homepage.lower() and b'Jake' in homepage
            assert fetch('/favicon-32x32.png').startswith(b'\x89PNG\r\n\x1a\n')
            print('Verified release',state['revision'])
            raise SystemExit(0)
    except Exception as exc:
        print('Waiting for deployment:',type(exc).__name__,flush=True)
    time.sleep(10)
raise SystemExit('Release was not verified within 10 minutes; inspect jake-deploy.service on the VPS.')
