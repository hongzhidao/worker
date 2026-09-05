#!/usr/bin/env python3
"""Install and exercise one runtime .deb on a disposable systemd test machine."""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import urllib.request

from smoke import available_port, control_request


def run(*args):
    return subprocess.run(args, check=True, text=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('artifact', type=Path)
    args = parser.parse_args()
    if os.geteuid() != 0 or not Path('/run/systemd/system').is_dir():
        parser.error('requires root on a disposable systemd machine')
    package = subprocess.check_output(['dpkg-deb', '-f', str(args.artifact), 'Package'], text=True).strip()
    if package not in ('worker-python', 'worker-php', 'worker-all'):
        parser.error('expected a Worker runtime package')
    installed = subprocess.run(['dpkg-query', '-W', '-f=${db:Status-Status}', package],
                               capture_output=True, text=True)
    if installed.stdout == 'installed':
        parser.error('refusing to replace an already installed package')
    flavor = package.removeprefix('worker-')
    languages = ('python', 'php') if flavor == 'all' else (flavor,)
    control = Path('/run') / package / 'control.sock'
    state = Path('/var/lib') / package
    if state.exists():
        parser.error('refusing to reuse existing service state')
    app = Path(tempfile.mkdtemp(prefix='worker-service-test-', dir='/var/lib'))
    app.chmod(0o755)
    (app / 'wsgi.py').write_text(
        'import json, os\nfrom pathlib import Path\n'
        'def application(environ, start_response):\n'
        '    path = Path(os.environ["WORKER_DATA_DIR"]) / "python.txt"\n'
        '    count = int(path.read_text()) + 1 if path.exists() else 1\n'
        '    path.write_text(str(count))\n'
        '    body = json.dumps({"count": count}).encode()\n'
        '    start_response("200 OK", [("Content-Type", "application/json")])\n'
        '    return [body]\n')
    (app / 'index.php').write_text(
        '<?php\n$path = getenv("WORKER_DATA_DIR") . "/php.txt";\n'
        '$count = is_file($path) ? (int) file_get_contents($path) + 1 : 1;\n'
        'if (file_put_contents($path, (string) $count) === false) { http_response_code(500); exit; }\n'
        'header("Content-Type: application/json"); echo json_encode(["count" => $count]);\n')
    ports = {language: available_port() for language in languages}
    applications = {}
    for language in languages:
        value = {'type': language, 'listen': f'127.0.0.1:{ports[language]}', 'processes': 1}
        if language == 'python':
            value.update(path=str(app), module='wsgi')
        else:
            value.update(root=str(app), script='index.php')
        applications[language] = value
    config = app / 'apps.json'
    config.write_text(json.dumps({'applications': applications}))
    for path in app.iterdir():
        path.chmod(0o644)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def counts():
        for attempt in range(100):
            try:
                return {language: json.load(opener.open(f'http://127.0.0.1:{ports[language]}/', timeout=2))['count']
                        for language in languages}
            except OSError:
                if attempt == 99:
                    raise
                time.sleep(0.1)

    try:
        run('dpkg', '-i', str(args.artifact.resolve()))
        assert subprocess.run(['systemctl', 'is-active', '--quiet', package]).returncode != 0
        defaults = Path('/etc/default') / package
        defaults.write_text(f'WORKER_CONFIG={config}\n')
        run('systemctl', 'start', package)
        initial = counts()
        for language in languages:
            assert control_request(control, 'PUT', f'/config/applications/{language}/processes', 2)[0] == 200
        defaults.write_text('# Preserve API configuration on restart.\n')
        run('systemctl', 'restart', package)
        restarted = counts()
        assert all(restarted[language] > initial[language] for language in languages)
        run('dpkg', '-i', str(args.artifact.resolve()))
        upgraded = counts()
        assert all(upgraded[language] > restarted[language] for language in languages)
        for language in languages:
            assert control_request(control, 'GET', f'/config/applications/{language}/processes') == (200, 2)
        assert control_request(control, 'GET', '/status')[0] == 200
        run('dpkg', '--remove', package)
        assert subprocess.run(['systemctl', 'is-active', '--quiet', package]).returncode != 0
        assert (state / 'data').is_dir()
        print('PASS systemd startup, persistent app writes, configuration, restart, reinstall, removal')
    finally:
        subprocess.run(['journalctl', '-u', package, '--no-pager', '-n', '80'])
        subprocess.run(['systemctl', 'stop', package], stderr=subprocess.DEVNULL)
        shutil.rmtree(app)


if __name__ == '__main__':
    main()
