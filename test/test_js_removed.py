import os
import subprocess
from pathlib import Path

import pytest
from worker.control import Control
from worker.option import option

client = Control()


@pytest.mark.parametrize('value', ['missing', ['missing'], [], {}])
def test_js_module_setting_unsupported(value):
    before = client.conf_get()
    response = client.conf({'js_module': value}, 'settings')
    assert response.get('detail') == 'Unknown parameter "js_module".'
    assert client.conf_get() == before


@pytest.mark.parametrize('method', ['GET', 'PUT', 'POST', 'DELETE'])
@pytest.mark.parametrize('path', ['/js_modules', '/js_modules/missing'])
def test_js_modules_api_unavailable(method, path):
    response = client.http(
        method, url=path, body='export default {};', sock_type='unix',
        addr=option.temp_dir + '/control.worker.sock',
    )
    assert response['status'] == 404
    assert 'js_modules' not in client.conf_get('/')
    assert not Path(option.temp_dir + '/state/scripts').exists()


def test_njs_configure_option_unsupported(tmp_path):
    build = tmp_path / 'build'
    result = subprocess.run(
        ['./configure', '--njs'], cwd=option.current_dir,
        env={**os.environ, 'NXT_BUILD_DIR': str(build)},
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    assert result.returncode != 0
    assert 'invalid option "--njs"' in result.stdout
    assert not build.exists()
