import json
from pathlib import Path

import pytest
from worker.applications.lang.python import ApplicationPython

prerequisites = {'modules': {'python': 'any'}}

client = ApplicationPython()


@pytest.fixture(autouse=True)
def setup_method_fixture():
    client.load('empty')


@pytest.mark.parametrize(
    'options',
    [None, {}, {'format': '$uri'}, {'format': {'uri': '$uri'}}, {'if': '$arg_log'}],
    ids=['path', 'object', 'format', 'json-format', 'condition'],
)
@pytest.mark.parametrize('whole_config', [False, True])
def test_access_log_unsupported(temp_dir, options, whole_config):
    path = Path(temp_dir) / 'access.log'
    value = str(path) if options is None else {'path': str(path), **options}
    before = client.conf_get()

    if whole_config:
        response = client.conf({**before, 'access_log': value})
    else:
        response = client.conf(json.dumps(value), 'access_log')

    assert response.get('detail') == 'Unknown parameter "access_log".'
    assert client.conf_get() == before
    assert client.get()['status'] == 200
    assert not path.exists()
