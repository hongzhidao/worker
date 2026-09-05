from worker.applications.lang.python import ApplicationPython
from worker.option import option

prerequisites = {'modules': {'python': 'all'}}


client = ApplicationPython()


def test_python_targets():
    assert 'success' in client.conf(
        {
            "applications": {
                "targets": {
                    "type": "python",
                    "working_directory": option.test_dir
                    + "/python/targets/",
                    "path": option.test_dir + '/python/targets/',
                    "targets": {
                        "1": {
                            "listen": "*:8080",
                            "module": "wsgi",
                            "callable": "wsgi_target_a",
                        },
                        "2": {
                            "listen": "*:8081",
                            "module": "wsgi",
                            "callable": "wsgi_target_b",
                        },
                    },
                }
            },
        }
    )

    resp = client.get(url='/1')
    assert resp['status'] == 200
    assert resp['body'] == '1'

    resp = client.get(url='/2', port=8081)
    assert resp['status'] == 200
    assert resp['body'] == '2'
