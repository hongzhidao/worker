import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import build as builder
import publish


class ReleaseValidation(unittest.TestCase):
    revision = '12345678' * 5

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        for distribution in ('ubuntu24.04', 'debian13'):
            for architecture in ('amd64', 'arm64'):
                for flavor in ('python', 'php'):
                    self.artifact(distribution, architecture, flavor)

    def artifact(self, distribution, architecture, flavor, **overrides):
        name = f'worker-{flavor}-0.1.0-{distribution}-{architecture}'
        manifest = {
            'version': '0.1.0', 'revision': self.revision,
            'build_distribution': distribution, 'architecture': architecture,
            'flavor': flavor, 'dirty_source': False, 'dirty_packager': False,
            'runtime_version': (
                ('8.3.33' if distribution == 'ubuntu24.04' else '8.4.25')
                if flavor == 'php' else ('3.12.1' if distribution == 'ubuntu24.04' else '3.13.1')
            ),
            **overrides,
        }
        archive = self.directory / (name + '.tar.gz')
        content = json.dumps(manifest).encode()
        with tarfile.open(archive, 'w:gz') as stream:
            member = tarfile.TarInfo(name + '/manifest.json')
            member.size = len(content)
            stream.addfile(member, io.BytesIO(content))
        deb = self.directory / (name + '.deb')
        deb.write_bytes(b'deb-test-fixture')
        for path in (archive, deb):
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            path.with_name(path.name + '.sha256').write_text(digest + '  ' + path.name + '\n')
        return archive, deb

    def validate(self):
        with patch.object(sys, 'argv', ['publish.py', 'v0.1.0', str(self.directory), '--check-only']), \
             patch.object(publish.subprocess, 'check_output', return_value=self.revision + '\n'), \
             patch.object(publish.subprocess, 'run') as external:
            publish.main()
            external.assert_not_called()

    def test_complete_matrix(self):
        self.validate()
        self.assertEqual(len((self.directory / 'SHA256SUMS').read_text().splitlines()), 16)

    def test_missing_build(self):
        next(self.directory.glob('*.tar.gz')).unlink()
        with self.assertRaisesRegex(RuntimeError, 'missing builds'):
            self.validate()

    def test_corrupt_deb(self):
        next(self.directory.glob('*.deb')).write_bytes(b'tampered')
        with self.assertRaisesRegex(RuntimeError, 'checksum mismatch'):
            self.validate()

    def test_wrong_revision(self):
        self.artifact('ubuntu24.04', 'amd64', 'python', revision='bad')
        with self.assertRaisesRegex(RuntimeError, 'revision mismatch'):
            self.validate()

    def test_dirty_build(self):
        self.artifact('debian13', 'arm64', 'php', dirty_source=True)
        with self.assertRaisesRegex(RuntimeError, 'dirty build'):
            self.validate()

    def test_wrong_version(self):
        self.artifact('debian13', 'arm64', 'php', version='0.2.0')
        with self.assertRaisesRegex(RuntimeError, 'version/revision mismatch'):
            self.validate()

    def test_wrong_runtime(self):
        self.artifact('debian13', 'arm64', 'php', runtime_version='8.3.33')
        with self.assertRaisesRegex(RuntimeError, 'runtime version mismatch'):
            self.validate()


class TagVersion(unittest.TestCase):
    def test_version_tag_matches_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'version').write_text('NXT_VERSION=0.1.0\n')
            with patch.object(builder, 'ROOT', root), patch.dict(os.environ, {
                'GITHUB_REF_TYPE': 'tag', 'GITHUB_REF_NAME': 'v0.1.0',
            }):
                self.assertEqual(builder.version(), '0.1.0')
            with patch.object(builder, 'ROOT', root), patch.dict(os.environ, {
                'GITHUB_REF_TYPE': 'tag', 'GITHUB_REF_NAME': 'v0.2.0',
            }):
                with self.assertRaisesRegex(RuntimeError, 'does not match'):
                    builder.version()


class LauncherConfiguration(unittest.TestCase):
    assets = Path(__file__).resolve().parent / 'assets'

    def test_python_listen(self):
        address = 'unix:/tmp/worker "python".sock'
        output = subprocess.check_output([
            sys.executable, str(self.assets / 'config.py'),
            '/bundle', '/srv/app', address, 'wsgi', 'application', 'wsgi', '',
        ])
        conf = json.loads(output)
        self.assertEqual(list(conf), ['applications'])
        self.assertEqual(conf['applications']['app']['listen'], address)
        self.assertEqual(conf['applications']['app']['module'], 'wsgi')

    @unittest.skipUnless(shutil.which('php'), 'PHP CLI unavailable')
    def test_php_listen(self):
        address = '[::1]:8080'
        output = subprocess.check_output([
            'php', str(self.assets / 'config.php'),
            '/bundle', '/srv/app', address, 'index.php',
        ])
        conf = json.loads(output)
        self.assertEqual(list(conf), ['applications'])
        self.assertEqual(conf['applications']['app']['listen'], address)
        self.assertEqual(conf['applications']['app']['script'], 'index.php')


if __name__ == '__main__':
    unittest.main()
