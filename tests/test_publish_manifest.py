import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class ManifestPublishingTests(unittest.TestCase):
    def publish(self, discovery_status):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            tools = root / 'bin'
            tools.mkdir()
            git = tools / 'git'
            git.write_text('#!' + sys.executable + '\n' + '''
import json, os, pathlib, sys
args = sys.argv[1:]
with open(os.environ['CALL_LOG'], 'a') as log:
    log.write(json.dumps(args) + '\\n')
if 'ls-remote' in args:
    assert args[0] == '-C', 'Branch discovery must use the clean manifest repository'
    sys.exit(int(os.environ['DISCOVERY_STATUS']))
if 'diff' in args:
    sys.exit(1)
''')
            git.chmod(0o755)
            encoder = tools / 'base64'
            encoder.write_text('#!' + sys.executable + '\nimport base64,sys\nsys.stdout.write(base64.b64encode(sys.stdin.buffer.read()).decode())\n')
            encoder.chmod(0o755)
            log = root / 'calls.jsonl'
            result = subprocess.run(['bash', str(Path(__file__).parents[1] / 'deploy/publish-manifest.sh')],
                cwd=Path(__file__).parents[1], text=True, capture_output=True,
                env=dict(os.environ, PATH=str(tools) + os.pathsep + os.environ['PATH'],
                         GITHUB_TOKEN='test-only-token', GITHUB_REPOSITORY='jake-jenkins/www.jake.ac',
                         DEPLOY_IMAGE='ghcr.io/jake-jenkins/www.jake.ac@sha256:' + 'a' * 64,
                         DEPLOY_REVISION='b' * 40, CALL_LOG=str(log),
                         DISCOVERY_STATUS=str(discovery_status)))
            return result, [json.loads(line) for line in log.read_text().splitlines()]

    def test_existing_branch_is_fetched_before_pushing(self):
        result, calls = self.publish(0)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(any('fetch' in c for c in calls))
        self.assertTrue(any('push' in c for c in calls))
        self.assertFalse(any('--orphan' in c for c in calls))

    def test_missing_branch_can_be_initialized(self):
        result, calls = self.publish(2)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(any('--orphan' in c for c in calls))
        self.assertTrue(any('push' in c for c in calls))

    def test_authentication_failure_never_creates_or_pushes_a_branch(self):
        result, calls = self.publish(128)
        self.assertEqual(result.returncode, 128)
        self.assertFalse(any('--orphan' in c or 'push' in c for c in calls))

