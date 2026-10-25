import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('deployment', Path(__file__).parents[1] / 'deploy/deploy.py')
deployment = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deployment)
IMAGE = deployment.IMAGE_PREFIX + 'a' * 64
MANIFEST = {'image': IMAGE, 'revision': 'b' * 40}


class DeploymentSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.state = Path(self.temp.name) / 'state.json'
        self.conf = Path(self.temp.name) / 'app.conf'
        self.old = dict(image=IMAGE, revision='c' * 40, slot='blue',
                        release='old', port=18201, container='jake-blue')
        self.state.write_text(json.dumps(self.old))
        self.conf.write_text('old config')
        self.paths = patch.multiple(deployment, STATE=self.state, CONF=self.conf)
        self.paths.start()
        self.addCleanup(self.paths.stop)

    def test_rejects_mutable_or_foreign_images_before_any_command(self):
        for image in ('ghcr.io/jake-jenkins/www.jake.ac:latest',
                      'ghcr.io/attacker/app@sha256:' + 'a' * 64,
                      IMAGE + '; touch /tmp/pwned'):
            with self.subTest(image=image), patch.object(deployment, 'run') as command:
                with self.assertRaises(ValueError):
                    deployment.deploy(dict(MANIFEST, image=image))
                command.assert_not_called()

    def test_route_configuration_leaves_tls_and_listeners_to_host(self):
        config = deployment.config(self.old)
        self.assertIn('proxy_pass http://127.0.0.1:18201', config)
        self.assertNotIn('listen ', config)
        self.assertNotIn('ssl_certificate', config)

    @patch.object(deployment, 'remove_container')
    @patch.object(deployment, 'run')
    @patch.object(deployment, 'drain_complete', return_value=True)
    def test_failed_readiness_leaves_old_release_and_route_untouched(self, drain, command, remove):
        with patch.object(deployment, 'wait_ready', side_effect=RuntimeError('not healthy')):
            with self.assertRaisesRegex(RuntimeError, 'not healthy'):
                deployment.deploy(MANIFEST)
        self.assertEqual(self.conf.read_text(), 'old config')
        self.assertEqual(json.loads(self.state.read_text()), self.old)
        self.assertFalse(any(c.args == ('systemctl', 'reload', 'nginx') for c in command.call_args_list))
        self.assertTrue(all(c.args == ('jake-green',) for c in remove.call_args_list))

    @patch.object(deployment, 'run')
    @patch.object(deployment, 'drain_complete', return_value=False)
    def test_active_draining_requests_prevent_slot_reuse(self, drain, command):
        with self.assertRaisesRegex(RuntimeError, 'still draining'):
            deployment.deploy(MANIFEST)
        command.assert_not_called()

    @patch.object(deployment, 'wait_ready')
    @patch.object(deployment, 'remove_container')
    @patch.object(deployment, 'drain_complete', return_value=True)
    def test_rejected_nginx_config_is_rolled_back_before_reload(self, drain, remove, ready):
        def commands(*args, **kwargs):
            if args == ('nginx', '-t'):
                raise RuntimeError('invalid config')
        with patch.object(deployment, 'run', side_effect=commands):
            with self.assertRaisesRegex(RuntimeError, 'invalid config'):
                deployment.deploy(MANIFEST)
        self.assertEqual(self.conf.read_text(), 'old config')
        self.assertEqual(json.loads(self.state.read_text()), self.old)

    @patch.object(deployment, 'ready')
    @patch.object(deployment, 'wait_ready')
    @patch.object(deployment, 'remove_container')
    @patch.object(deployment, 'run')
    @patch.object(deployment, 'drain_complete', return_value=True)
    def test_success_retains_previous_container_for_request_draining(self, drain, command, remove, wait, ready):
        def get(url):
            # Read the actual candidate config to emulate the newly loaded worker.
            config = self.conf.read_text()
            release = config.split('X-Deployment-Release "')[1].split('"')[0]
            return json.dumps({'release': release}).encode(), {'X-Deployment-Release': release}
        with patch.object(deployment, 'get', side_effect=get):
            deployment.deploy(MANIFEST)
        active = json.loads(self.state.read_text())
        self.assertEqual(active['slot'], 'green')
        self.assertEqual(active['previous'], self.old)
        remove.assert_called_once_with('jake-green')
        self.assertIn('127.0.0.1:18202', self.conf.read_text())

    @patch.object(deployment, 'ready')
    @patch.object(deployment, 'wait_ready')
    @patch.object(deployment, 'remove_container')
    @patch.object(deployment, 'run')
    @patch.object(deployment, 'drain_complete', return_value=True)
    def test_first_deployment_bootstraps_without_previous_state(self, drain, command, remove, wait, ready):
        self.state.unlink()
        self.conf.write_text('location / { return 503; }')
        def get(url):
            config = self.conf.read_text()
            release = config.split('X-Deployment-Release "')[1].split('"')[0]
            return json.dumps({'release': release}).encode(), {'X-Deployment-Release': release}
        with patch.object(deployment, 'get', side_effect=get):
            deployment.deploy(MANIFEST)
        active = json.loads(self.state.read_text())
        self.assertEqual(active['slot'], 'blue')
        self.assertEqual(active['previous'], {})


if __name__ == '__main__':
    unittest.main()

