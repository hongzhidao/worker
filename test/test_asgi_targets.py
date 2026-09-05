from distutils.version import LooseVersion

import pytest
from worker.applications.lang.python import ApplicationPython
from worker.option import option

prerequisites = {
    'modules': {'python': lambda v: LooseVersion(v) >= LooseVersion('3.5')}
}


client = ApplicationPython(load_module='asgi')

@pytest.fixture(autouse=True)
def setup_method_fixture():
    assert 'success' in client.conf(
        {
            "applications": {
                "targets": {
                    "type": "python",
                    "processes": {"spare": 0},
                    "working_directory": option.test_dir
                    + "/python/targets/",
                    "path": option.test_dir + '/python/targets/',
                    "protocol": "asgi",
                    "targets": {
                        "1": {
                            "listen": "*:8080",
                            "module": "asgi",
                            "callable": "application_200",
                        },
                        "2": {
                            "listen": "*:8081",
                            "module": "asgi",
                            "callable": "application_201",
                        },
                    },
                }
            },
        }
    )

def conf_targets(targets):
    current = client.conf_get('applications/targets/targets')
    for name, target in targets.items():
        target['listen'] = current[name]['listen']
    assert 'success' in client.conf(targets, 'applications/targets/targets')

def test_asgi_targets():
    assert client.get(url='/1')['status'] == 200
    assert client.get(url='/2', port=8081)['status'] == 201

def test_asgi_targets_legacy():
    conf_targets(
        {
            "1": {"module": "asgi", "callable": "legacy_application_200"},
            "2": {"module": "asgi", "callable": "legacy_application_201"},
        }
    )

    assert client.get(url='/1')['status'] == 200
    assert client.get(url='/2', port=8081)['status'] == 201

def test_asgi_targets_mix():
    conf_targets(
        {
            "1": {"module": "asgi", "callable": "application_200"},
            "2": {"module": "asgi", "callable": "legacy_application_201"},
        }
    )

    assert client.get(url='/1')['status'] == 200
    assert client.get(url='/2', port=8081)['status'] == 201

def test_asgi_targets_broken(skip_alert):
    skip_alert(r'Python failed to get "blah" from module')

    conf_targets(
        {
            "1": {"module": "asgi", "callable": "application_200"},
            "2": {"module": "asgi", "callable": "blah"},
        }
    )

    assert client.get(url='/1')['status'] != 200
