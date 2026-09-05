import subprocess
from pathlib import Path

import pytest
from worker.option import option


@pytest.mark.parametrize('failed_option', ['--log', '--pid'])
def test_runtime_startup_failure_exits(temp_dir, failed_option):
    root = Path(temp_dir) / 'startup'
    root.mkdir()
    missing = root / 'missing' / 'file'
    log = root / 'worker.log'

    options = {
        '--control': f'unix:{root}/control.sock',
        '--pid': str(root / 'worker.pid'),
        '--log': str(log),
        '--state': str(root / 'state'),
        '--tmp': str(root),
        '--modules': option.current_dir + '/build',
    }
    if option.user is not None:
        options['--user'] = option.user
    options[failed_option] = str(missing)

    command = [option.current_dir + '/build/workerd', '--no-daemon']
    for name, value in options.items():
        command.extend([name, value])

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=10,
    )
    diagnostics = result.stdout
    if log.exists():
        diagnostics += log.read_text()

    assert result.returncode == 1, diagnostics
    assert str(missing) in diagnostics, diagnostics
