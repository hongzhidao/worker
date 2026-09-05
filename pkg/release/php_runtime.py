"""Build upstream PHP with internal timezone data and the bundled extensions."""

import hashlib
import json
import platform
import re
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path


def prepare(root, series, distribution, jobs):
    pinned = json.loads((Path(__file__).parent / 'runtimes.json').read_text())['php'][series]
    version, checksum = pinned['version'], pinned['sha256']
    build = root / 'build'
    build.mkdir(exist_ok=True)
    prefix = build / f'php-runtime-{version}-{distribution}-{platform.machine()}'
    metadata = {
        'name': 'php-runtime', 'version': version, 'source': 'php',
        'source_version': version, 'source_sha256': checksum,
        'source_url': f'https://www.php.net/distributions/php-{version}.tar.xz',
        'build_profile': 1,
    }
    stamp = prefix / 'runtime-source.json'
    if stamp.exists() and json.loads(stamp.read_text()) == metadata:
        return prefix
    cache = build / 'runtime-sources'
    cache.mkdir(exist_ok=True)
    archive = cache / f'php-{version}.tar.xz'
    if not archive.exists():
        partial = archive.with_suffix('.partial')
        subprocess.run(['curl', '--fail', '--location', '--retry', '3', '--output',
                        str(partial), metadata['source_url']], check=True)
        partial.rename(archive)
    with archive.open('rb') as stream:
        actual = hashlib.file_digest(stream, 'sha256').hexdigest()
    if actual != checksum:
        raise RuntimeError(f'PHP source checksum mismatch: {archive}')
    with tempfile.TemporaryDirectory(prefix='php-source-', dir=build) as temporary:
        source_root = Path(temporary)
        with tarfile.open(archive) as stream:
            stream.extractall(source_root, filter='data')
        source = source_root / ('php-' + version)
        flags = [
            './configure', '--prefix=' + str(prefix),
            '--with-config-file-path=' + str(prefix / 'etc'),
            '--with-config-file-scan-dir=' + str(prefix / 'etc/conf.d'),
            '--disable-all', '--disable-cgi', '--disable-phpdbg', '--enable-cli',
            '--enable-embed=shared', '--with-external-pcre', '--with-openssl',
            '--with-zlib', '--with-curl', '--with-sodium', '--with-password-argon2', '--with-iconv',
            '--enable-bcmath', '--enable-ctype', '--enable-fileinfo', '--enable-filter',
            '--enable-ftp', '--enable-mbstring', '--enable-intl', '--enable-opcache',
            '--enable-pcntl', '--enable-phar', '--enable-posix', '--enable-session',
            '--enable-sockets', '--enable-tokenizer', '--enable-pdo',
            '--with-mysqli=mysqlnd', '--with-pdo-mysql=mysqlnd',
            '--with-sqlite3', '--with-pdo-sqlite', '--with-zip',
            '--with-libxml', '--enable-dom', '--enable-simplexml', '--enable-xml',
            '--enable-xmlreader', '--enable-xmlwriter', '--enable-soap',
            '--enable-gd', '--with-jpeg', '--with-freetype',
        ]
        subprocess.run(flags, cwd=source, check=True)
        subprocess.run(['make', f'-j{jobs}'], cwd=source, check=True)
        subprocess.run(['make', 'install'], cwd=source, check=True)
        licenses = prefix / 'share/licenses/php'
        for path in source.rglob('*'):
            if path.is_file() and re.fullmatch(r'(?:LICENSE|COPYING|COPYRIGHT)(?:\..*)?', path.name, re.I):
                destination = licenses / path.relative_to(source)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, destination)
        (prefix / 'etc/conf.d').mkdir(parents=True, exist_ok=True)
        (prefix / 'etc/php.ini').write_text('date.timezone=UTC\n')
        stamp.write_text(json.dumps(metadata, indent=2) + '\n')
    return prefix
