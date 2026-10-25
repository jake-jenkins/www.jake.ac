#!/usr/bin/env bash
set -euo pipefail
: "${IMAGE:?}"
name="jake-smoke-${GITHUB_RUN_ID:-local}-${GITHUB_RUN_ATTEMPT:-1}"
trap 'docker rm -f "$name" >/dev/null 2>&1 || true' EXIT
docker run -d --name "$name" --init --user 101:101 --read-only \
  --cap-drop ALL --security-opt no-new-privileges:true \
  --tmpfs /tmp:rw,noexec,nosuid,nodev,size=32m,mode=1777 \
  --memory 96m --memory-swap 96m --cpus 0.5 --pids-limit 128 \
  --publish 127.0.0.1::8080 --entrypoint nginx "$IMAGE" -g 'daemon off;'
address=$(docker port "$name" 8080/tcp)
for attempt in $(seq 1 30); do
  if curl --fail --silent "http://${address}/" > /tmp/jake-smoke-home.html; then
    break
  fi
  sleep 1
done
python3 - <<'PY'
from pathlib import Path
body=Path('/tmp/jake-smoke-home.html').read_bytes()
assert b'<html' in body.lower() and b'Jake' in body
PY
curl --fail --silent "http://${address}/favicon-32x32.png" | python3 -c 'import sys; assert sys.stdin.buffer.read().startswith(b"\x89PNG\r\n\x1a\n")'
