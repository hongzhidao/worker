from worker.applications.lang.php import ApplicationPHP
from worker.option import option

prerequisites = {'modules': {'php': 'any'}}


client = ApplicationPHP()


def test_php_application_targets():
    assert 'success' in client.conf(
        {
            "applications": {
                "targets": {
                    "type": "php",
                    "processes": {"spare": 0},
                    "targets": {
                        "1": {
                            "listen": "*:8080",
                            "script": "1.php",
                            "root": option.test_dir + "/php/targets",
                        },
                        "2": {
                            "listen": "*:8081",
                            "script": "2.php",
                            "root": option.test_dir + "/php/targets/2",
                        },
                        "default": {
                            "listen": "*:8082",
                            "index": "index.php",
                            "root": option.test_dir + "/php/targets",
                        },
                    },
                }
            },
        }
    )

    assert client.get(url='/1')['body'] == '1'
    assert client.get(url='/2', port=8081)['body'] == '2'
    assert client.get(url='/blah', port=8082)['status'] == 503  # TODO 404
    assert client.get(url='/', port=8082)['body'] == 'index'
    assert client.get(url='/1.php?test=test.php/', port=8082)['body'] == '1'

    assert 'success' in client.conf(
        "\"1.php\"", 'applications/targets/targets/default/index'
    ), 'change targets index'
    assert client.get(url='/', port=8082)['body'] == '1'

    assert 'success' in client.conf_delete(
        'applications/targets/targets/default/index'
    ), 'remove targets index'
    assert client.get(url='/', port=8082)['body'] == 'index'

def test_php_application_targets_error():
    assert 'success' in client.conf(
        {
            "applications": {
                "targets": {
                    "type": "php",
                    "processes": {"spare": 0},
                    "targets": {
                        "default": {
                            "listen": "*:8080",
                            "index": "index.php",
                            "root": option.test_dir + "/php/targets",
                        },
                    },
                }
            },
        }
    ), 'initial configuration'
    assert client.get()['status'] == 200

    assert 'error' in client.conf(
        '"127.0.0.1"', 'applications/targets/targets/default/listen'
    ), 'invalid target listen'
    assert 'error' in client.conf(
        '"' + option.test_dir + '/php/targets\"',
        'applications/targets/root',
    ), 'invalid root'
    assert 'error' in client.conf(
        '"index.php"', 'applications/targets/index'
    ), 'invalid index'
    assert 'error' in client.conf(
        '"index.php"', 'applications/targets/script'
    ), 'invalid script'
    assert 'error' in client.conf_delete(
        'applications/targets/default/root'
    ), 'root remove'
