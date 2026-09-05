#!/usr/bin/env python3
"""Build a relocatable Worker runtime bundle and a matching Debian package."""

import argparse
import hashlib
import gzip
import json
import os
import platform
import re
import shlex
import shutil
import subprocess
import sys
import sysconfig
import tarfile
import tempfile
import zipfile
from pathlib import Path

from php_runtime import prepare as prepare_php

ROOT = Path(__file__).resolve().parents[2]
ASSETS = Path(__file__).resolve().parent / 'assets'
GLIBC = re.compile(r'^(?:ld-linux.*|ld64.*|lib(?:c|m|mvec|pthread|dl|rt|resolv|util|anl|thread_db|BrokenLocale|nss_.*)\.so\..*)$')


def run(*args, **kwargs):
    return subprocess.run(args, check=True, text=True, **kwargs)


def output(*args):
    return run(*args, stdout=subprocess.PIPE).stdout.strip()


def version():
    match = re.search(r'^NXT_VERSION=([0-9]+\.[0-9]+\.[0-9]+)$',
                      (ROOT / 'version').read_text(), re.M)
    if not match:
        raise RuntimeError('version must contain NXT_VERSION=major.minor.patch')
    value = match[1]
    tag = os.environ.get('GITHUB_REF_NAME', '')
    if os.environ.get('GITHUB_REF_TYPE') == 'tag' and tag != 'v' + value:
        raise RuntimeError(f'tag {tag!r} does not match version v{value}')
    return value


def distro():
    values = {}
    for line in Path('/etc/os-release').read_text().splitlines():
        if '=' in line and not line.startswith('#'):
            key, value = line.split('=', 1)
            values[key] = shlex.split(value)[0]
    if values.get('ID') not in ('ubuntu', 'debian'):
        raise RuntimeError('build on Ubuntu or Debian; dependencies use dpkg metadata')
    name = values['ID'] + values['VERSION_ID']
    if not re.fullmatch(r'[a-z]+[0-9.]+', name):
        raise RuntimeError('unsupported distribution identifier')
    return name


def copy(source, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination, follow_symlinks=True)


def elf(path):
    if not path.is_file():
        return False
    with path.open('rb') as stream:
        return stream.read(4) == b'\x7fELF'


class Dependencies:
    def __init__(self, bundle, php_prefix=None):
        self.bundle = bundle
        self.packages = {}
        self.libraries = {}
        self.php_prefix = php_prefix

    def record(self, path):
        path = Path(path).resolve()
        if self.php_prefix is not None and path.is_relative_to(self.php_prefix):
            if 'php-runtime' not in self.packages:
                self.packages['php-runtime'] = json.loads((self.php_prefix / 'runtime-source.json').read_text())
                shutil.copytree(self.php_prefix / 'share/licenses/php', self.bundle / 'licenses/php-runtime')
            return
        candidates = [str(path)]
        if str(path).startswith('/usr/lib/'):
            candidates.append(str(path)[4:])
        owner = None
        for candidate in candidates:
            result = subprocess.run(['dpkg-query', '-S', candidate], text=True,
                                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            if result.returncode == 0:
                owner = result.stdout.split(': ', 1)[0].split(', ')[0]
                break
        if owner is None:
            raise RuntimeError(f'no distribution package owns bundled file {path}')
        if owner in self.packages:
            return
        data = output('dpkg-query', '-W', '-f=${Package}\t${Version}\t${source:Package}\t${source:Version}', owner)
        name, binary_version, source, source_version = data.split('\t')
        copyright_file = Path('/usr/share/doc') / name / 'copyright'
        if not copyright_file.exists():
            raise RuntimeError(f'missing copyright file for {name}')
        copy(copyright_file, self.bundle / 'licenses' / name / 'copyright')
        self.packages[owner] = {
            'name': name, 'version': binary_version,
            'source': source, 'source_version': source_version,
        }

    def collect(self, paths):
        queue = list(paths)
        visited = set()
        while queue:
            path = Path(queue.pop()).resolve()
            if path in visited or not elf(path):
                continue
            visited.add(path)
            result = run('ldd', str(path), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            for line in result.stdout.splitlines():
                if '=> not found' in line:
                    raise RuntimeError(f'unresolved library for {path}: {line.strip()}')
                match = re.match(r'\s*(\S+)\s+=>\s+(/\S+)\s+\(', line)
                if not match:
                    continue
                soname, filename = match.groups()
                if GLIBC.fullmatch(soname):
                    continue
                previous = self.libraries.get(soname)
                resolved = Path(filename).resolve()
                if previous is not None and previous != resolved:
                    raise RuntimeError(f'conflicting libraries named {soname}')
                if previous is None:
                    self.libraries[soname] = resolved
                    copy(resolved, self.bundle / 'lib' / soname)
                    self.record(resolved)
                    queue.append(resolved)


def python_runtime(bundle, dependencies):
    runtime = bundle / 'runtime'
    full_version = platform.python_version()
    minor = f'{sys.version_info.major}.{sys.version_info.minor}'
    executable = Path(sys.executable).resolve()
    copy(executable, runtime / 'bin' / 'python')
    dependencies.record(executable)
    stdlib = Path(sysconfig.get_path('stdlib'))
    target = runtime / 'lib' / ('python' + minor)
    shutil.copytree(stdlib, target, ignore=shutil.ignore_patterns(
        '__pycache__', '*.pyc', 'test', 'tests', 'site-packages', 'dist-packages',
        'config-*', 'EXTERNALLY-MANAGED', 'idlelib', 'tkinter', '_tkinter*.so', 'turtledemo'))
    dependencies.record(stdlib / 'os.py')
    dependencies.record(stdlib / 'encodings' / '__init__.py')
    wheels = sorted(Path('/usr/share/python-wheels').glob('*.whl'))
    pip = [wheel for wheel in wheels if wheel.name.startswith('pip-')]
    if not pip:
        raise RuntimeError('install python3-venv (the pip wheel is required)')
    site = runtime / 'lib' / 'python3' / 'dist-packages'
    site.mkdir(parents=True)
    for wheel in wheels:
        if wheel.name.startswith(('pip-', 'setuptools-')):
            with zipfile.ZipFile(wheel) as archive:
                for item in archive.infolist():
                    destination = (site / item.filename).resolve()
                    if not destination.is_relative_to(site.resolve()):
                        raise RuntimeError('invalid wheel path')
                archive.extractall(site)
            dependencies.record(wheel)
    dependencies.collect([runtime / 'bin' / 'python', *target.rglob('*.so')])
    return full_version, minor, []


def php_runtime(bundle, dependencies):
    prefix = dependencies.php_prefix
    config = str(prefix / 'bin/php-config')
    executable = prefix / 'bin/php'
    full_version = output(config, '--version')
    if output(str(executable), '-n', '-r', 'echo PHP_VERSION;') != full_version:
        raise RuntimeError('php and php-config must refer to the same runtime')
    if output(str(executable), '-n', '-r', 'echo timezone_version_get();') == '0.system':
        raise RuntimeError('PHP must use internal timezone data for relocatable packages')
    minor = '.'.join(full_version.split('.')[:2])
    runtime = bundle / 'runtime'
    copy(executable, runtime / 'bin' / 'php')
    dependencies.record(executable)
    extension_dir = Path(output(config, '--extension-dir'))
    entries = []
    extensions = json.loads(output(str(executable), '-n', '-r', 'echo json_encode(get_loaded_extensions());'))
    for library in sorted(extension_dir.glob('*.so')):
        name = library.stem
        directive = 'zend_extension' if name == 'opcache' else 'extension'
        copy(library, runtime / 'extensions' / library.name)
        dependencies.record(library)
        entries.append(f'{directive}={library.name}')
        extensions.append(name)
    required = {'curl', 'mbstring', 'pdo', 'dom', 'fileinfo'}
    loaded = {name.lower() for name in extensions}
    if not required.issubset(loaded):
        raise RuntimeError('missing PHP extensions: ' + ', '.join(sorted(required - loaded)))
    (runtime / 'conf.d').mkdir()
    (runtime / 'php.ini').write_text(
        'extension_dir="${WORKER_BUNDLE_ROOT}/runtime/extensions"\n'
        'date.timezone=UTC\nexpose_php=Off\ndisplay_errors=Off\nlog_errors=On\n'
        'memory_limit=256M\n'
        'openssl.cafile="${WORKER_BUNDLE_ROOT}/runtime/ca-certificates.crt"\n'
        'curl.cainfo="${WORKER_BUNDLE_ROOT}/runtime/ca-certificates.crt"\n'
        + '\n'.join(entries) + '\n')
    dependencies.collect([runtime / 'bin' / 'php', *runtime.glob('extensions/*.so')])
    return full_version, minor, extensions


def write_deb(bundle, destination, manifest, epoch):
    package = 'worker-' + manifest['flavor']
    with tempfile.TemporaryDirectory(prefix='deb-', dir=destination) as temporary:
        root = Path(temporary)
        root.chmod(0o755)
        installed = root / 'opt' / 'worker' / manifest['flavor']
        shutil.copytree(bundle, installed)
        binary = root / 'usr' / 'bin' / package
        binary.parent.mkdir(parents=True)
        binary.write_text(f'#!/bin/sh\nexec /opt/worker/{manifest["flavor"]}/worker "$@"\n')
        binary.chmod(0o755)
        control = root / 'DEBIAN'
        control.mkdir()
        (control / 'control').write_text(
            f'Package: {package}\nVersion: {manifest["version"]}\n'
            f'Architecture: {manifest["architecture"]}\n'
            'Maintainer: Worker Project <hongzhidao@gmail.com>\n'
            'Section: web\nPriority: optional\n'
            f'Depends: libc6 (>= {manifest["glibc_minimum"]}), coreutils\n'
            'Homepage: https://github.com/hongzhidao/worker\n'
            f'Description: Worker with bundled {manifest["flavor"]} runtime\n'
            ' Runs applications without compiling Worker or installing a language runtime.\n')
        service = root / 'usr' / 'lib' / 'systemd' / 'system' / (package + '.service')
        service.parent.mkdir(parents=True)
        service.write_text(
            '[Unit]\nDescription=Worker ' + manifest['flavor'] + '\nAfter=network.target\n\n'
            '[Service]\nType=simple\nDynamicUser=yes\n'
            f'EnvironmentFile=-/etc/default/{package}\nExecStart=/usr/bin/{package}\n'
            'Restart=on-failure\nKillSignal=SIGTERM\nTimeoutStopSec=15\n'
            'NoNewPrivileges=yes\nPrivateTmp=yes\n\n[Install]\nWantedBy=multi-user.target\n')
        defaults = root / 'etc' / 'default' / package
        defaults.parent.mkdir(parents=True)
        defaults.write_text(
            f'WORKER_APP=/opt/worker/{manifest["flavor"]}/example\n'
            'WORKER_LISTEN=127.0.0.1:8080\n')
        (control / 'conffiles').write_text('/etc/default/' + package + '\n')
        for path in root.rglob('*'):
            if path.is_dir():
                path.chmod(0o755)
            os.utime(path, (epoch, epoch), follow_symlinks=False)
        name = bundle.name + '.deb'
        run('dpkg-deb', '--root-owner-group', '--build', str(root), str(destination / name),
            env={**os.environ, 'SOURCE_DATE_EPOCH': str(epoch)})
        return destination / name


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('flavor', choices=('python', 'php'))
    parser.add_argument('--output', type=Path, default=ROOT / 'build' / 'release')
    parser.add_argument('--jobs', type=int, default=min(os.cpu_count() or 2, 4))
    parser.add_argument('--source-ref', help='build core sources from this Git commit instead of the worktree')
    parser.add_argument('--php-series', choices=('8.3', '8.4'), help='override the platform PHP series')
    args = parser.parse_args()
    release = version()
    architecture = {'x86_64': 'amd64', 'aarch64': 'arm64'}.get(platform.machine())
    if not architecture:
        parser.error('only x86_64 and aarch64 are supported')
    distribution = distro()
    glibc = output('getconf', 'GNU_LIBC_VERSION').split()[1]
    destination = args.output.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    build_root = ROOT / 'build'
    build_root.mkdir(exist_ok=True)
    php_prefix = None
    if args.flavor == 'php':
        series = args.php_series or ('8.3' if distribution == 'ubuntu24.04' else '8.4')
        php_prefix = prepare_php(ROOT, series, distribution, args.jobs)
    revision = output('git', '-C', str(ROOT), 'rev-parse', 'HEAD')
    if args.source_ref:
        revision = output('git', '-C', str(ROOT), 'rev-parse', '--verify',
                          '--end-of-options', args.source_ref + '^{commit}')
    epoch = int(os.environ.get('SOURCE_DATE_EPOCH') or output(
        'git', '-C', str(ROOT), 'show', '-s', '--format=%ct', revision))
    dirty = bool(output('git', '-C', str(ROOT), 'status', '--porcelain', '--untracked-files=no'))
    if os.environ.get('GITHUB_REF_TYPE') == 'tag' and dirty:
        raise RuntimeError('tag releases require a clean checkout')
    with tempfile.TemporaryDirectory(prefix='release-', dir=build_root) as temporary:
        work = Path(temporary)
        source = work / 'source'
        source.mkdir()
        if args.source_ref:
            with tempfile.TemporaryFile() as archive:
                run('git', '-C', str(ROOT), 'archive', revision,
                    'src', 'auto', 'docs', 'configure', 'version', stdout=archive)
                archive.seek(0)
                with tarfile.open(fileobj=archive) as stream:
                    stream.extractall(source, filter='data')
            if (source / 'version').read_text() != (ROOT / 'version').read_text():
                raise RuntimeError('source-ref and worktree version files differ')
        else:
            for name in ('src', 'auto', 'docs'):
                shutil.copytree(ROOT / name, source / name)
            for name in ('configure', 'version'):
                copy(ROOT / name, source / name)
        run('./configure', cwd=source)
        command = ['./configure', args.flavor]
        if args.flavor == 'python':
            command.append('--config=python3-config')
        else:
            command += ['--config=' + str(php_prefix / 'bin/php-config'),
                        '--lib-path=' + str(php_prefix / 'lib')]
        run(*command, cwd=source)
        run('make', f'-j{args.jobs}', cwd=source)
        stage = work / 'bundle'
        (stage / 'bin').mkdir(parents=True)
        copy(source / 'build' / 'workerd', stage / 'bin' / 'workerd')
        modules = list((source / 'build').glob('*.worker.so'))
        if len(modules) != 1:
            raise RuntimeError('expected exactly one language module')
        copy(modules[0], stage / 'modules' / modules[0].name)
        dependencies = Dependencies(stage, php_prefix)
        runtime_builder = python_runtime if args.flavor == 'python' else php_runtime
        full_version, minor, extensions = runtime_builder(stage, dependencies)
        copy(Path(shutil.which('curl')).resolve(), stage / 'bin' / 'curl')
        dependencies.record(Path(shutil.which('curl')).resolve())
        dependencies.collect([stage / 'bin' / 'workerd', stage / 'bin' / 'curl',
                              stage / 'modules' / modules[0].name])
        certificates = Path('/etc/ssl/certs/ca-certificates.crt')
        copy(certificates, stage / 'runtime' / 'ca-certificates.crt')
        dependencies.record(Path('/usr/share/doc/ca-certificates/copyright'))
        if args.flavor == 'python':
            shutil.copytree('/usr/share/zoneinfo', stage / 'runtime' / 'zoneinfo',
                            ignore=shutil.ignore_patterns('posix', 'right'))
            dependencies.record(Path('/usr/share/zoneinfo/UTC'))
        name = f'worker-{args.flavor}{minor}-{release}-{distribution}-{architecture}'
        manifest = {
            'version': release, 'revision': revision,
            'dirty_source': dirty and not bool(args.source_ref), 'dirty_packager': dirty,
            'flavor': args.flavor, 'runtime_version': full_version,
            'architecture': architecture, 'build_distribution': distribution,
            'glibc_minimum': glibc, 'php_extensions': extensions,
            'packages': sorted(dependencies.packages.values(), key=lambda value: value['name']),
        }
        (stage / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
        (stage / 'bundle.env').write_text(
            f'WORKER_FLAVOR={args.flavor}\nWORKER_ARCH={architecture}\n'
            f'WORKER_GLIBC_MIN={shlex.quote(glibc)}\nWORKER_VERSION={release}\n')
        for asset in ('worker', 'environment', 'config.py', 'config.php'):
            copy(ASSETS / asset, stage / ('worker' if asset == 'worker' else 'libexec/' + asset))
        copy(ASSETS / 'runtime', stage / args.flavor)
        (stage / 'worker').chmod(0o755)
        (stage / args.flavor).chmod(0o755)
        for name_in in ('LICENSE', 'NOTICE'):
            copy(ROOT / name_in, stage / name_in)
        copy(Path(__file__).parent / 'BUNDLE_README.md', stage / 'README.md')
        example = 'wsgi.py' if args.flavor == 'python' else 'index.php'
        copy(ASSETS / example, stage / 'example' / example)
        if args.flavor == 'python':
            copy(ASSETS / 'asgi.py', stage / 'example' / 'asgi.py')
        sources = ['# Dependency Sources', '',
                   f'Worker: https://github.com/hongzhidao/worker/tree/{revision}', '',
                   'Exact distribution package versions and copyright notices are included',
                   'in manifest.json and licenses/. Corresponding source packages:', '']
        for package in manifest['packages']:
            host = 'https://launchpad.net/ubuntu/+source' if distribution.startswith('ubuntu') else 'https://sources.debian.org/src'
            url = package.get('source_url', f'{host}/{package["source"]}/{package["source_version"]}')
            sources.append('- ' + url)
        (stage / 'SOURCES.md').write_text('\n'.join(sources) + '\n')
        bundle = work / name
        stage.rename(bundle)
        for path in bundle.rglob('*'):
            if path.is_dir():
                path.chmod(0o755)
            else:
                path.chmod(0o755 if path.stat().st_mode & 0o111 else 0o644)
                if elf(path):
                    run('strip', '--strip-unneeded', str(path))
        archive = destination / (name + '.tar.gz')
        def normalize(info):
            info.uid = info.gid = 0
            info.uname = info.gname = 'root'
            info.mtime = epoch
            return info
        with archive.open('wb') as raw:
            with gzip.GzipFile(filename='', mode='wb', fileobj=raw, mtime=epoch) as compressed:
                with tarfile.open(fileobj=compressed, mode='w') as stream:
                    stream.add(bundle, arcname=name, filter=normalize)
        deb = write_deb(bundle, destination, manifest, epoch)
        for artifact in (archive, deb):
            with artifact.open('rb') as stream:
                digest = hashlib.file_digest(stream, 'sha256').hexdigest()
            (destination / (artifact.name + '.sha256')).write_text(digest + '  ' + artifact.name + '\n')
        print(json.dumps({'archive': str(archive), 'deb': str(deb), **manifest}, indent=2))


if __name__ == '__main__':
    main()
