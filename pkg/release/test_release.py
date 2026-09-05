import hashlib
import csv
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import build as builder
import publish
from smoke import wait_for_statistics


class ReleaseValidation(unittest.TestCase):
    revision = '12345678' * 5

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        for distribution in ('ubuntu24.04', 'debian13'):
            for architecture in ('amd64', 'arm64'):
                for flavor in ('python', 'php', 'all'):
                    self.artifact(distribution, architecture, flavor)

    def artifact(self, distribution, architecture, flavor, **overrides):
        name = f'worker-{flavor}-0.1.0-{distribution}-{architecture}'
        manifest = {
            'version': '0.1.0', 'revision': self.revision,
            'build_distribution': distribution, 'architecture': architecture,
            'flavor': flavor, 'dirty_source': False, 'dirty_packager': False,
            'glibc_minimum': '2.39' if distribution == 'ubuntu24.04' else '2.41',
            'runtime_version': (
                ('8.3.33' if distribution == 'ubuntu24.04' else '8.4.25')
                if flavor == 'php' else ('3.12.1' if distribution == 'ubuntu24.04' else '3.13.1')
            ),
            **overrides,
        }
        if flavor == 'all':
            manifest.pop('runtime_version')
            manifest['runtime_versions'] = {
                'python': '3.12.1' if distribution == 'ubuntu24.04' else '3.13.1',
                'php': '8.3.33' if distribution == 'ubuntu24.04' else '8.4.25',
            }
            manifest.update(overrides)
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
        self.assertEqual(len((self.directory / 'SHA256SUMS').read_text().splitlines()), 24)
        with (self.directory / 'downloads.tsv').open() as stream:
            rows = list(csv.reader(stream, delimiter='\t'))
        self.assertEqual(len(rows), 12)
        self.assertTrue((self.directory / 'install.sh').is_file())

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

    def test_missing_combined_runtime(self):
        self.artifact('debian13', 'arm64', 'all', runtime_versions={'python': '3.13.1'})
        with self.assertRaisesRegex(RuntimeError, 'runtime version mismatch'):
            self.validate()

    def test_publish_notes_and_verified_assets(self):
        (self.directory / 'unverified.deb').write_bytes(b'unverified')
        with patch.object(sys, 'argv', ['publish.py', 'v0.1.0', str(self.directory)]), \
             patch.object(publish.subprocess, 'check_output', return_value=self.revision + '\n'), \
             patch.object(publish.subprocess, 'run') as external:
            external.return_value.returncode = 1
            publish.main()
            arguments = external.call_args_list[1].args[0]
            self.assertNotIn(str(self.directory / 'unverified.deb'), arguments)
            self.assertIn(str(self.directory / 'install.sh'), arguments)
            self.assertIn(str(self.directory / 'downloads.tsv'), arguments)
        notes = (self.directory / 'RELEASE_NOTES.md').read_text()
        self.assertIn('sh install.sh all --version v0.1.0', notes)
        self.assertEqual(notes.count('[tar.gz]('), 12)


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

    def test_combined_configuration(self):
        output = subprocess.check_output([
            sys.executable, str(self.assets / 'config.py'), '--all', '127.0.0.1:8081',
            '/bundle', '/app', '127.0.0.1:8080', 'wsgi', 'application', 'wsgi', '',
        ])
        applications = json.loads(output)['applications']
        self.assertEqual(set(applications), {'python', 'php'})
        self.assertEqual(applications['php']['listen'], '127.0.0.1:8081')
        self.assertEqual(applications['python']['home'], '/bundle/runtime')

    def test_configuration_file_runtime_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'config.json'
            path.write_text(json.dumps({'applications': {
                'py': {'type': 'python'}, 'php': {'type': 'php'},
                'custom': {'type': 'python', 'home': '/custom'},
            }}))
            output = subprocess.check_output([
                sys.executable, str(self.assets / 'config.py'), '--config', '/bundle', str(path),
            ])
            applications = json.loads(output)['applications']
            self.assertEqual(applications['py']['home'], '/bundle/runtime')
            self.assertEqual(applications['php']['options']['file'], '/bundle/runtime/php.ini')
            self.assertEqual(applications['custom']['home'], '/custom')


class Installer(unittest.TestCase):
    script = Path(__file__).resolve().parent / 'install.sh'

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.bin = self.directory / 'bin'
        self.bin.mkdir()
        for name, text in (
            ('uname', '#!/bin/sh\ncase "$1" in -s) echo Linux ;; -m) echo x86_64 ;; esac\n'),
            ('getconf', '#!/bin/sh\necho "glibc 2.41"\n'),
        ):
            path = self.bin / name
            path.write_text(text)
            path.chmod(0o755)
        self.destination = self.directory / "installed with 'quotes'"
        self.archive = self.directory / 'worker-all-0.1.0-ubuntu24.04-amd64.tar.gz'
        with tarfile.open(self.archive, 'w:gz') as stream:
            body = b'#!/bin/sh\necho worker\n'
            member = tarfile.TarInfo('bundle/worker')
            member.size = len(body)
            member.mode = 0o755
            stream.addfile(member, io.BytesIO(body))
        self.digest = hashlib.sha256(self.archive.read_bytes()).hexdigest()
        self.index()

    def index(self, digest=None, arch='amd64'):
        (self.directory / 'downloads.tsv').write_text(
            f'ubuntu24.04\t{arch}\tall\t2.39\t{self.archive.name}\t{digest or self.digest}\n')

    def install(self, *arguments):
        return subprocess.run(['sh', str(self.script), 'all', '--prefix', str(self.destination), *arguments],
                              env={**os.environ, 'PATH': str(self.bin) + ':' + os.environ['PATH'],
                                   'WORKER_DOWNLOAD_BASE_URL': self.directory.as_uri()},
                              capture_output=True, text=True)

    def test_verified_install_and_existing_destination(self):
        result = self.install()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(os.access(self.destination / 'worker', os.X_OK))
        result = self.install()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Destination exists', result.stderr)

    def test_checksum_failure_does_not_install(self):
        self.index(digest='0' * 64)
        self.assertNotEqual(self.install().returncode, 0)
        self.assertFalse(self.destination.exists())

    def test_missing_architecture(self):
        self.index(arch='arm64')
        self.assertIn('No all package', self.install().stderr)
        self.assertFalse(self.destination.exists())

    def test_old_glibc(self):
        (self.bin / 'getconf').write_text('#!/bin/sh\necho "glibc 2.35"\n')
        self.assertIn('detected 2.35', self.install().stderr)
        self.assertFalse(self.destination.exists())

    def test_malformed_artifact_name(self):
        self.archive = Path('worker-../../outside.tar.gz')
        (self.directory / 'downloads.tsv').write_text(
            f'ubuntu24.04\tamd64\tall\t2.39\t{self.archive}\t{self.digest}\n')
        self.assertIn('Invalid artifact name', self.install().stderr)
        self.assertFalse(self.destination.exists())


class LauncherReadiness(unittest.TestCase):
    def test_waits_for_complete_startup_output_without_seeking_child_stream(self):
        with tempfile.TemporaryFile(mode='w+b') as log:
            command = ["/bundle with 'quotes'/worker", 'status', '--control', '/tmp/control.sock']
            import shlex
            line = 'Statistics: ' + shlex.join(command) + '\n'
            partial = line[:25].encode()
            log.write(partial)
            log.flush()

            def finish_output():
                time.sleep(0.1)
                log.write(line[25:].encode())
                log.flush()

            writer = threading.Thread(target=finish_output)
            writer.start()
            process = unittest.mock.Mock()
            process.poll.return_value = None
            try:
                wait_for_statistics(process, log, command, timeout=2)
            finally:
                writer.join()
            self.assertEqual(os.pread(log.fileno(), len(line.encode()), 0), line.encode())

    def test_reports_exit_before_startup_output(self):
        with tempfile.TemporaryFile(mode='w+b') as log:
            process = unittest.mock.Mock()
            process.poll.return_value = 1
            with self.assertRaisesRegex(RuntimeError, 'did not finish'):
                wait_for_statistics(process, log, [], timeout=1)


if __name__ == '__main__':
    unittest.main()
