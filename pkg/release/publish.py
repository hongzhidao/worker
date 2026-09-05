#!/usr/bin/env python3
"""Validate a complete build matrix before publishing a tagged GitHub Release."""

import argparse
import hashlib
import json
import re
import subprocess
import tarfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('tag')
    parser.add_argument('directory', type=Path)
    parser.add_argument('--check-only', action='store_true')
    args = parser.parse_args()
    if not re.fullmatch(r'v\d+\.\d+\.\d+', args.tag):
        parser.error('release tags must use vMAJOR.MINOR.PATCH')
    expected = {(distro, arch, flavor) for distro in ('ubuntu24.04', 'debian13')
                for arch in ('amd64', 'arm64') for flavor in ('python', 'php')}
    found = set()
    php_versions = json.loads((Path(__file__).parent / 'runtimes.json').read_text())['php']
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    checksums = []
    for archive in sorted(args.directory.glob('*.tar.gz')):
        with tarfile.open(archive) as stream:
            members = [member for member in stream.getmembers()
                       if member.name.count('/') == 1 and member.name.endswith('/manifest.json')]
            if len(members) != 1:
                raise RuntimeError(f'invalid manifest in {archive}')
            manifest = json.load(stream.extractfile(members[0]))
        key = (manifest['build_distribution'], manifest['architecture'], manifest['flavor'])
        if key not in expected or key in found:
            raise RuntimeError(f'unexpected or duplicate build: {key}')
        if manifest['version'] != args.tag[1:] or manifest['revision'] != revision:
            raise RuntimeError(f'version/revision mismatch in {archive}')
        if manifest['dirty_source'] or manifest['dirty_packager']:
            raise RuntimeError(f'dirty build in {archive}')
        if manifest['flavor'] == 'php':
            series = '8.3' if key[0] == 'ubuntu24.04' else '8.4'
            valid_runtime = manifest['runtime_version'] == php_versions[series]['version']
        else:
            series = '3.12.' if key[0] == 'ubuntu24.04' else '3.13.'
            valid_runtime = manifest['runtime_version'].startswith(series)
        if not valid_runtime:
            raise RuntimeError(f'runtime version mismatch in {archive}')
        found.add(key)
        for artifact in (archive, archive.with_name(archive.name.removesuffix('.tar.gz') + '.deb')):
            with artifact.open('rb') as stream:
                digest = hashlib.file_digest(stream, 'sha256').hexdigest()
            expected_sum = artifact.with_name(artifact.name + '.sha256').read_text().strip()
            if expected_sum != digest + '  ' + artifact.name:
                raise RuntimeError(f'checksum mismatch: {artifact}')
            checksums.append(expected_sum)
    if found != expected:
        raise RuntimeError(f'missing builds: {sorted(expected - found)}')
    (args.directory / 'SHA256SUMS').write_text('\n'.join(sorted(checksums)) + '\n')
    if args.check_only:
        print('Complete release matrix and checksums verified.')
        return
    exists = subprocess.run(['gh', 'release', 'view', args.tag, '--json', 'isDraft'],
                            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if exists.returncode == 0:
        raise RuntimeError('release already exists; do not overwrite published runtime packages')
    notes = args.directory / 'RELEASE_NOTES.md'
    notes.write_text(
        f'# Worker {args.tag[1:]}\n\n'
        'Download the Python or PHP package for your Linux distribution and CPU architecture.\n'
        'Each package includes Worker, its language module, the language runtime, and shared libraries.\n'
        'Ubuntu 24.04 builds require glibc 2.39+; Debian 13 builds require glibc 2.41+.\n'
        'Alpine/musl is not supported.\n\n'
        'Verify the SHA256 checksum before extracting or installing.\n'
        'For tar.gz packages, extract and run `./worker --app /path/to/app`.\n'
        'For .deb packages, use `sudo apt install ./worker-*.deb`, then `worker-python` or `worker-php`.\n'
        'See the packaged README for app entry points, dependencies, and service configuration.\n')
    assets = sorted(str(path) for path in args.directory.iterdir()
                    if path.name.endswith(('.tar.gz', '.deb', '.sha256')) or path.name == 'SHA256SUMS')
    subprocess.run(['gh', 'release', 'create', args.tag, '--verify-tag', '--draft',
                    '--title', 'Worker ' + args.tag[1:], '--notes-file', str(notes), *assets], check=True)
    subprocess.run(['gh', 'release', 'edit', args.tag, '--draft=false'], check=True)


if __name__ == '__main__':
    main()
