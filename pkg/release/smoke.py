#!/usr/bin/env python3
"""Exercise unpacked and installed runtime bundles, optionally in a clean OS."""

import argparse
import hashlib
import json
import os
import re
import shutil
import signal
import socket
import stat
import subprocess
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).resolve().parent / 'tests'


def run(*args, **kwargs):
    return subprocess.run(args, check=True, text=True, **kwargs)


def copy_base(root):
    (root / 'usr/bin').mkdir(parents=True)
    (root / 'usr/lib').mkdir(parents=True)
    (root / 'usr/lib64').mkdir(parents=True)
    for name in ('bin', 'lib', 'lib64'):
        (root / name).symlink_to('usr/' + name)
    architecture = subprocess.check_output(['dpkg', '--print-architecture'], text=True).strip()
    libc_files = subprocess.check_output(['dpkg-query', '-L', 'libc6:' + architecture], text=True)
    for filename in libc_files.splitlines():
        source = Path(filename)
        if '.so' in source.name and source.is_file():
            destination = root / filename.lstrip('/')
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source.resolve(), destination)
    requested = ['/bin/sh'] + [shutil.which(name) for name in
                               ('dirname', 'uname', 'getconf', 'id', 'mktemp', 'mkdir', 'sleep', 'rm', 'cat', 'tail')]
    for executable in requested:
        source = Path(executable)
        destination = root / str(source).lstrip('/')
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source.resolve(), destination)
        result = run('ldd', str(source), stdout=subprocess.PIPE)
        for library in re.findall(r'(?:=>\s+)?(/\S+)\s+\(', result.stdout):
            destination = root / library.lstrip('/')
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(Path(library).resolve(), destination)
    (root / 'etc').mkdir()
    (root / 'etc/passwd').write_text('root:x:0:0:root:/root:/bin/sh\nnobody:x:65534:65534:nobody:/nonexistent:/bin/sh\n')
    (root / 'etc/group').write_text('root:x:0:\nnogroup:x:65534:\n')
    (root / 'etc/nsswitch.conf').write_text('passwd: files\ngroup: files\nhosts: files dns\n')
    (root / 'tmp').mkdir(mode=0o1777)
    (root / 'tmp').chmod(0o1777)
    (root / 'dev/shm').mkdir(parents=True, mode=0o1777)
    (root / 'dev/shm').chmod(0o1777)
    for name, minor in [('null', 3), ('zero', 5), ('random', 8), ('urandom', 9)]:
        os.mknod(root / 'dev' / name, stat.S_IFCHR | 0o666, os.makedev(1, minor))
        (root / 'dev' / name).chmod(0o666)
    (root / 'proc').mkdir()
    run('mount', '-t', 'proc', 'proc', str(root / 'proc'))
    (root / 'dev/stderr').symlink_to('/proc/self/fd/2')
    (root / 'dev/stdout').symlink_to('/proc/self/fd/1')


def request(port, body=None):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(urllib.request.Request(f'http://127.0.0.1:{port}/check?x=1', data=body), timeout=2) as response:
        assert response.status == 200
        return json.load(response)


def server(command, expected, environment, container=None):
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        port = listener.getsockname()[1]
    command += ['--listen', f'127.0.0.1:{port}']
    with tempfile.TemporaryFile(mode='w+') as log:
        process = subprocess.Popen(command, stdout=log, stderr=log, env=environment,
                                   start_new_session=True)
        try:
            deadline = time.monotonic() + 30
            while True:
                try:
                    result = request(port)
                    break
                except (OSError, urllib.error.URLError):
                    if process.poll() is not None or time.monotonic() >= deadline:
                        log.seek(0)
                        raise RuntimeError('server did not become healthy:\n' + log.read())
                    time.sleep(0.1)
            assert result.get('flavor', result.get('worker')) == expected, result
            if 'flavor' in result:
                body = 'Worker runtime \u4f60\u597d'.encode()
                result = request(port, body)
                assert result['method'] == 'POST' and result['body'] == body.decode(), result
                assert result['sha256'] == hashlib.sha256(body).hexdigest(), result
                if expected == 'python':
                    assert result['dependency'] == 42
                else:
                    assert {'curl', 'mbstring', 'dom', 'PDO', 'openssl'}.issubset(result['extensions'])
            assert process.poll() is None, 'server exited after responding'
        finally:
            if container:
                subprocess.run(['docker', 'stop', '-t', '10', container],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                process.terminate()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
                raise RuntimeError('server did not shut down cleanly')
            log.seek(0)
            text = log.read()
            if 'PHP Startup:' in text or 'error while loading shared libraries' in text:
                raise RuntimeError(text)


def smoke(artifact, mode, image):
    with artifact.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    assert artifact.with_name(artifact.name + '.sha256').read_text().split()[0] == digest
    with tempfile.TemporaryDirectory(prefix='bundle-smoke-', dir=ROOT / 'build') as temporary:
        root = Path(temporary)
        root.chmod(0o755)
        expanded = root / 'expanded'
        expanded.mkdir()
        deb = artifact.suffix == '.deb'
        if deb:
            run('dpkg-deb', '-x', str(artifact), str(expanded))
            bundles = list((expanded / 'opt/worker').iterdir())
        else:
            with tarfile.open(artifact) as archive:
                archive.extractall(expanded, filter='data')
            bundles = list(expanded.iterdir())
        assert len(bundles) == 1
        bundle = root / 'bundle with spaces'
        bundles[0].rename(bundle)
        manifest = json.loads((bundle / 'manifest.json').read_text())
        flavor = manifest['flavor']
        app = root / 'user app'
        shutil.copytree(FIXTURES, app)
        environment = {**os.environ, 'PYTHONPATH': '/not-a-runtime',
                       'PHP_INI_SCAN_DIR': '/not-a-runtime'}
        mounted = False
        try:
            if mode == 'chroot':
                jail = root / 'clean'
                jail.mkdir()
                copy_base(jail)
                mounted = True
                if deb:
                    run('dpkg-deb', '-x', str(artifact), str(jail))
                    target = f'/opt/worker/{flavor}'
                    entry = f'/usr/bin/worker-{flavor}'
                else:
                    target = '/bundle with spaces'
                    shutil.copytree(bundle, jail / target.lstrip('/'))
                    entry = target + '/worker'
                shutil.copytree(app, jail / 'app')
                prefix = ['chroot', '--userspec=65534:65534', str(jail)]
                runtime = prefix + [target + '/' + flavor]
                command = prefix + [entry]
                app_path = '/app'
                environment.pop('TMPDIR', None)
            elif mode == 'container':
                # Each invocation uses an untouched base image, without language packages.
                run('docker', 'run', '--rm', image, 'sh', '-ec',
                    '! command -v python3; ! command -v php; ! command -v gcc')
                mounts = ['-v', f'{bundle}:/bundle with spaces:ro', '-v', f'{app}:/app:ro']
                runtime = ['docker', 'run', '--rm', '--user', '65534:65534', *mounts,
                           image, '/bundle with spaces/' + flavor]
                app_path = '/app'
                command = None
            else:
                runtime = [str(bundle / flavor)]
                command = [str(bundle / 'worker')]
                app_path = str(app)
            runtime_arguments = ['-m', 'pip', '--version'] if flavor == 'python' else ['-v']
            run(*(runtime + runtime_arguments), env=environment)
            if mode == 'container':
                name = 'worker-smoke-' + uuid.uuid4().hex[:12]
                command = ['docker', 'run', '--rm', '--name', name, '--network', 'host', *mounts]
                if deb:
                    command += ['-v', f'{artifact}:/package.deb:ro', image, 'sh', '-ec',
                                'dpkg -i /package.deb >&2; exec "$@"', 'sh', f'/usr/bin/worker-{flavor}']
                else:
                    command += ['--user', '65534:65534', image, '/bundle with spaces/worker']
            else:
                name = None
            custom = command + ['--app', app_path]
            if flavor == 'python':
                custom += ['--python-path', app_path + '/vendor']
            server(custom, flavor, environment, name)
            if mode != 'container':
                server(command.copy(), flavor, environment)
                if flavor == 'python':
                    server(command + ['--protocol', 'asgi'], flavor, environment)
        finally:
            if mounted:
                run('umount', str(jail / 'proc'))
        print(f'PASS {artifact.name}: {mode}, runtime, user application, shutdown')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('artifacts', nargs='+', type=Path)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--container', metavar='IMAGE')
    mode.add_argument('--chroot', action='store_true', help='requires root and a private mount namespace')
    args = parser.parse_args()
    for path in args.artifacts:
        smoke(path.resolve(), 'container' if args.container else 'chroot' if args.chroot else 'native', args.container)


if __name__ == '__main__':
    main()
