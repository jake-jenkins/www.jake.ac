#!/usr/bin/env python3
"""Root-owned blue/green deployment agent. Never executes repository scripts."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import urllib.request
import uuid

ROOT = Path('/var/lib/jake-deploy')
STATE = ROOT / 'state.json'
CONF = Path('/etc/nginx/jake-routes.conf')
IMAGE_PREFIX = 'ghcr.io/jake-jenkins/www.jake.ac@sha256:'


def run(*args, timeout=180, capture=False):
    return subprocess.run(args, check=True, text=True, timeout=timeout,
                          stdout=subprocess.PIPE if capture else None).stdout


def validate(manifest):
    image, revision = manifest.get('image', ''), manifest.get('revision', '')
    if not re.fullmatch(re.escape(IMAGE_PREFIX) + '[0-9a-f]{64}', image):
        raise ValueError('Only immutable digests from the jake-site registry are accepted')
    if not re.fullmatch('[0-9a-f]{40}', revision):
        raise ValueError('revision must be a full Git commit SHA')
    return image, revision


def atomic_write(path, text):
    tmp = path.with_name(path.name + '.tmp')
    tmp.write_text(text)
    os.replace(tmp, path)


def config(state):
    status = json.dumps({k: state[k] for k in ('image', 'revision', 'release')}, separators=(',', ':'))
    return '''
    location = /__deployment {
        default_type application/json;
        add_header Cache-Control "no-store" always;
        return 200 '%s';
    }
    location / {
        proxy_pass http://127.0.0.1:%d;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_connect_timeout 5s;
        proxy_read_timeout 60s;
        add_header X-Deployment-Release "%s" always;
    }
''' % (status, state['port'], state['release'])


def get(url):
    req = urllib.request.Request(url, headers={'Connection': 'close', 'Host': 'www.jake.ac'})
    with urllib.request.urlopen(req, timeout=5) as response:
        return response.read(), response.headers


def ready(port):
    body, _ = get(f'http://127.0.0.1:{port}/')
    if b'<html' not in body.lower() or b'Jake' not in body:
        raise RuntimeError('Site homepage is missing')
    body, _ = get(f'http://127.0.0.1:{port}/favicon-32x32.png')
    if not body.startswith(b'\x89PNG\r\n\x1a\n'):
        raise RuntimeError('Site favicon is missing')


def wait_ready(port, timeout=120):
    deadline = time.monotonic() + timeout
    while True:
        try:
            ready(port)
            return
        except Exception:
            if time.monotonic() >= deadline:
                raise RuntimeError(f'Candidate on port {port} failed readiness checks')
            time.sleep(2)


def drain_complete():
    processes = run('ps', '-eo', 'args', capture=True)
    return 'nginx: worker process is shutting down' not in processes


def remove_container(name):
    found = run('docker', 'ps', '-a', '--filter', f'name=^{name}$', '--format', '{{.Names}}', capture=True).strip()
    if found:
        run('docker', 'rm', '-f', name)


def deploy(manifest, force=False):
    image, revision = validate(manifest)
    current = json.loads(STATE.read_text()) if STATE.exists() else {}
    if not force and current.get('image') == image and current.get('revision') == revision:
        print('Already deployed', revision)
        return
    if not drain_complete():
        raise RuntimeError('Previous requests are still draining; leaving both slots untouched')
    slot = 'green' if current.get('slot') == 'blue' else 'blue'
    port = 18201 if slot == 'blue' else 18202
    name = f'jake-{slot}'
    run('docker', 'pull', image, timeout=600)
    remove_container(name)
    switched = False
    old_conf = CONF.read_text() if CONF.exists() else ''
    candidate = dict(image=image, revision=revision, release=uuid.uuid4().hex,
                     port=port, slot=slot, container=name)
    try:
        run('docker', 'run', '-d', '--name', name, '--restart', 'unless-stopped', '--init',
            '--user', '101:101', '--cap-drop', 'ALL',
            '--security-opt', 'no-new-privileges=true', '--read-only',
            '--tmpfs', '/tmp:rw,noexec,nosuid,nodev,size=32m,mode=1777',
            '--memory', '96m', '--memory-swap', '96m', '--cpus', '0.5',
            '--pids-limit', '128', '--env', 'PYTHONDONTWRITEBYTECODE=1',
            '--env', 'PYTHONUNBUFFERED=1',
            '--publish', f'127.0.0.1:{port}:8080',
            '--log-opt', 'max-size=10m', '--log-opt', 'max-file=3',
            '--entrypoint', 'nginx', image, '-g', 'daemon off;')
        wait_ready(port)
        atomic_write(CONF, config(candidate))
        run('nginx', '-t')
        # Keep the old container alive: old Nginx workers finish existing requests.
        switched = True
        run('systemctl', 'reload', 'nginx')
        deadline = time.monotonic() + 30
        while True:
            try:
                body, _ = get('http://127.0.0.1:18444/__deployment')
                _, headers = get('http://127.0.0.1:18444/')
                if (json.loads(body)['release'] == candidate['release'] and
                        headers.get('X-Deployment-Release') == candidate['release']):
                    ready(port)
                    break
            except Exception:
                pass
            if time.monotonic() >= deadline:
                raise RuntimeError('Post-switch health verification failed')
            time.sleep(1)
        candidate['previous'] = {k: v for k, v in current.items() if k != 'previous'}
        atomic_write(STATE, json.dumps(candidate, indent=2) + '\n')
        print('Deployed', image, revision, flush=True)
    except Exception:
        atomic_write(CONF, old_conf)
        if switched:
            run('nginx', '-t')
            run('systemctl', 'reload', 'nginx')
            # A worker may still be finishing a candidate request. Retain it safely.
        else:
            remove_container(name)
        raise


def watch():
    checkout = ROOT / 'repository.git'
    if not checkout.exists():
        run('git', 'init', '--bare', str(checkout))
    # Read-only repository deploy key; no inbound CI access or runner on the VPS.
    ssh = ('ssh -i /var/lib/jake-deploy/ssh/id_ed25519 -o IdentitiesOnly=yes '
           '-o UserKnownHostsFile=/var/lib/jake-deploy/ssh/known_hosts '
           '-o StrictHostKeyChecking=yes -o BatchMode=yes')
    run('git', '-C', str(checkout), '-c', f'core.sshCommand={ssh}', 'fetch', '--depth=1',
        'git@github.com:jake-jenkins/www.jake.ac.git',
        '+refs/heads/production-deploy:refs/heads/production-deploy', timeout=120)
    raw = run('git', '-C', str(checkout), 'show', 'production-deploy:deployment.json', capture=True)
    deploy(json.loads(raw))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('manifest', nargs='?')
    parser.add_argument('--watch', action='store_true')
    parser.add_argument('--force', action='store_true')
    args = parser.parse_args()
    ROOT.mkdir(parents=True, exist_ok=True)
    # Serialize proxy configuration changes across websites sharing this host.
    proxy_lock = Path('/var/lib/website-deploy')
    proxy_lock.mkdir(parents=True, exist_ok=True)
    with (proxy_lock / 'nginx.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if args.watch:
            watch()
        else:
            deploy(json.loads(Path(args.manifest).read_text()), force=args.force)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f'Deployment failed: {exc}', file=sys.stderr, flush=True)
        sys.exit(1)

