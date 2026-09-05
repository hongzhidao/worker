#!/usr/bin/env python3
"""Validate a complete build matrix before publishing a tagged GitHub Release."""

import argparse
import csv
import hashlib
import json
import re
import shutil
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
                for arch in ('amd64', 'arm64') for flavor in ('python', 'php', 'all')}
    found = set()
    php_versions = json.loads((Path(__file__).parent / 'runtimes.json').read_text())['php']
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    checksums = []
    downloads = []
    verified_assets = []
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
        languages = ('python', 'php') if manifest['flavor'] == 'all' else (manifest['flavor'],)
        versions = manifest.get('runtime_versions', {manifest['flavor']: manifest.get('runtime_version')})
        if set(versions) != set(languages):
            raise RuntimeError(f'runtime version mismatch in {archive}')
        for language in languages:
            if language == 'php':
                series = '8.3' if key[0] == 'ubuntu24.04' else '8.4'
                valid_runtime = versions[language] == php_versions[series]['version']
            else:
                series = '3.12.' if key[0] == 'ubuntu24.04' else '3.13.'
                valid_runtime = isinstance(versions[language], str) and versions[language].startswith(series)
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
            verified_assets.extend((artifact, artifact.with_name(artifact.name + '.sha256')))
            if artifact == archive:
                downloads.append((*key, manifest['glibc_minimum'], archive.name, digest))
    if found != expected:
        raise RuntimeError(f'missing builds: {sorted(expected - found)}')
    (args.directory / 'SHA256SUMS').write_text('\n'.join(sorted(checksums)) + '\n')
    with (args.directory / 'downloads.tsv').open('w', newline='') as stream:
        csv.writer(stream, delimiter='\t', lineterminator='\n').writerows(sorted(downloads))
    shutil.copy2(Path(__file__).parent / 'install.sh', args.directory / 'install.sh')
    if args.check_only:
        print('Complete release matrix and checksums verified.')
        return
    exists = subprocess.run(['gh', 'release', 'view', args.tag, '--json', 'isDraft'],
                            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if exists.returncode == 0:
        raise RuntimeError('release already exists; do not overwrite published runtime packages')
    notes = args.directory / 'RELEASE_NOTES.md'
    table = ['| Build / CPU | Python | PHP | Python + PHP |',
             '| --- | --- | --- | --- |']
    files = {row[:3]: row[4] for row in downloads}
    for distribution in ('ubuntu24.04', 'debian13'):
        for architecture in ('amd64', 'arm64'):
            cells = []
            for flavor in ('python', 'php', 'all'):
                filename = files[(distribution, architecture, flavor)]
                url = f'https://github.com/hongzhidao/worker/releases/download/{args.tag}/{filename}'
                cells.append(f'[tar.gz]({url}) / [deb]({url.removesuffix(".tar.gz")}.deb)')
            table.append(f'| {distribution} / {architecture} | ' + ' | '.join(cells) + ' |')
    notes.write_text(
        f'# Worker {args.tag[1:]}\n\n'
        'Run Python and PHP applications with one control and statistics API using the **all** package.\n'
        'Single-language packages are also available. All packages include their runtimes and shared libraries.\n\n'
        '## Quick Start\n\n```sh\n'
        f'curl -fLO https://github.com/hongzhidao/worker/releases/download/{args.tag}/install.sh\n'
        f'sh install.sh all --version {args.tag}\n'
        './worker-all/worker --state ./worker-state\n```\n\n'
        'In another terminal:\n\n```sh\ncurl http://127.0.0.1:8080/\ncurl http://127.0.0.1:8081/\n'
        './worker-all/worker status --state ./worker-state\n```\n\n'
        'The installer detects CPU architecture, checks glibc, verifies SHA256, and installs without sudo.\n'
        'It never replaces an existing directory. Select `python` or `php` for a single language.\n\n'
        '## Manual Downloads\n\n' + '\n'.join(table) + '\n\n'
        'Ubuntu 24.04 builds require glibc 2.39+; Debian 13 builds require glibc 2.41+.\n'
        'Alpine/musl is not supported.\n\n'
        'For .deb packages, install the one selected file with `sudo apt install ./FILE.deb`.\n'
        'Commands are `worker-all`, `worker-python`, and `worker-php`. Services are initially disabled.\n'
        'See the packaged README for FastAPI, Django, PHP, persistent state, and systemd setup.\n')
    assets = sorted(str(path) for path in verified_assets + [
        args.directory / name for name in ('SHA256SUMS', 'downloads.tsv', 'install.sh')])
    subprocess.run(['gh', 'release', 'create', args.tag, '--verify-tag', '--draft',
                    '--title', 'Worker ' + args.tag[1:], '--notes-file', str(notes), *assets], check=True)
    subprocess.run(['gh', 'release', 'edit', args.tag, '--draft=false'], check=True)


if __name__ == '__main__':
    main()
