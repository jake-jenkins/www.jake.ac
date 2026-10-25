#!/usr/bin/env bash
set -euo pipefail
: "${DEPLOY_IMAGE:?}" "${DEPLOY_REVISION:?}"
# Authenticate both reads and writes of this private repository. Never save the token.
: "${GITHUB_TOKEN:?}"
export GIT_CONFIG_COUNT=1
export GIT_CONFIG_KEY_0=http.https://github.com/.extraheader
export GIT_CONFIG_VALUE_0="AUTHORIZATION: basic $(printf 'x-access-token:%s' "$GITHUB_TOKEN" | base64 -w0)"
manifest_dir=$(mktemp -d)
trap 'rm -rf "$manifest_dir"' EXIT
git init "$manifest_dir"
git -C "$manifest_dir" remote add origin "https://github.com/${GITHUB_REPOSITORY}.git"
git -C "$manifest_dir" config user.name 'github-actions[bot]'
git -C "$manifest_dir" config user.email '41898282+github-actions[bot]@users.noreply.github.com'
if git -C "$manifest_dir" ls-remote --exit-code origin refs/heads/production-deploy >/dev/null; then
  git -C "$manifest_dir" fetch --depth=1 origin production-deploy
  git -C "$manifest_dir" checkout -b production-deploy FETCH_HEAD
else
  status=$?
  # Exit 2 means the branch is absent. Authentication/network errors must fail closed.
  if [ "$status" -ne 2 ]; then
    exit "$status"
  fi
  git -C "$manifest_dir" checkout --orphan production-deploy
fi
python3 - "$manifest_dir/deployment.json" <<'PY'
import json, os, pathlib, re, sys
image, revision = os.environ['DEPLOY_IMAGE'], os.environ['DEPLOY_REVISION']
assert re.fullmatch(r'ghcr.io/jake-jenkins/www.jake.ac@sha256:[0-9a-f]{64}', image)
assert re.fullmatch(r'[0-9a-f]{40}', revision)
pathlib.Path(sys.argv[1]).write_text(json.dumps({'image': image, 'revision': revision}, indent=2) + '\n')
PY
git -C "$manifest_dir" add deployment.json
git -C "$manifest_dir" diff --cached --quiet && exit 0
git -C "$manifest_dir" commit -m "Deploy ${DEPLOY_REVISION}"
git -C "$manifest_dir" push origin production-deploy

