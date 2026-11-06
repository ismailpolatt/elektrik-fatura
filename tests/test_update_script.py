import os
from pathlib import Path
import subprocess
import tempfile
import unittest


class UpdateScriptTests(unittest.TestCase):
    def run_update(self, running='elektrik', build_code='0'):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        docker = root / 'docker'
        docker.write_text('''#!/usr/bin/env python3
import os, sys
from pathlib import Path
args = sys.argv[1:]
with Path(os.environ['TEST_DOCKER_LOG']).open('a') as log:
    log.write(' '.join(args) + '\\n')
if args[:2] == ['compose', 'ps']:
    print(os.environ['TEST_RUNNING'])
if args[:2] == ['compose', 'build']:
    sys.exit(int(os.environ['TEST_BUILD_CODE']))
if args[:2] == ['compose', 'exec']:
    sys.stdin.read()
''')
        docker.chmod(0o755)
        log = root / 'calls'
        env = dict(os.environ, PATH=str(root) + os.pathsep + os.environ['PATH'],
                   TEST_DOCKER_LOG=str(log), TEST_RUNNING=running, TEST_BUILD_CODE=build_code)
        script = Path(__file__).resolve().parents[1] / 'scripts/update.sh'
        result = subprocess.run(['bash', str(script)], env=env, capture_output=True, text=True)
        return result, log.read_text().splitlines()

    def test_backup_before_build_and_recreate(self):
        result, calls = self.run_update()
        self.assertEqual(result.returncode, 0)
        backup = next(i for i, call in enumerate(calls) if call.startswith('compose exec'))
        self.assertLess(backup, calls.index('compose build elektrik'))
        self.assertLess(calls.index('compose build elektrik'), calls.index('compose up -d --no-deps elektrik'))

    def test_failed_build_does_not_recreate_container(self):
        result, calls = self.run_update(build_code='1')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(any(call.startswith('compose up') for call in calls))

    def test_wrong_project_does_not_build(self):
        result, calls = self.run_update(running='')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(any(call.startswith('compose build') for call in calls))


if __name__ == '__main__':
    unittest.main()
