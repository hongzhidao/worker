from worker.control import Control

prerequisites = {'modules': {'php': 'any'}}

client = Control()

conf_app = {
    "app": {
        "listen": "*:8080",
        "type": "php",
        "processes": {"spare": 0},
        "root": "/app",
        "index": "index.php",
    }
}

conf_basic = {
    "applications": conf_app,
}


def test_php_get_applications():
    assert 'success' in client.conf(conf_app, 'applications')

    conf = client.conf_get()

    assert 'listeners' not in conf
    assert conf['applications'] == {
        "app": {
            "listen": "*:8080",
            "type": "php",
            "processes": {"spare": 0},
            "root": "/app",
            "index": "index.php",
        }
    }, 'applications'

    assert client.conf_get('applications') == {
        "app": {
            "listen": "*:8080",
            "type": "php",
            "processes": {"spare": 0},
            "root": "/app",
            "index": "index.php",
        }
    }, 'applications prefix'

    assert client.conf_get('applications/app') == {
        "listen": "*:8080",
        "type": "php",
        "processes": {"spare": 0},
        "root": "/app",
        "index": "index.php",
    }, 'applications prefix 2'

    assert client.conf_get('applications/app/type') == 'php', 'type'
    assert (
        client.conf_get('applications/app/processes/spare') == 0
    ), 'spare processes'


def test_php_get_listen():
    assert 'success' in client.conf(conf_basic)

    assert client.conf_get()['applications']['app']['listen'] == '*:8080'
    assert client.conf_get('applications/app/listen') == '*:8080'


def test_php_change_listen():
    assert 'success' in client.conf(conf_basic)
    assert 'success' in client.conf(
        '"*:8081"', 'applications/app/listen'
    )

    assert client.conf_get('applications/app/listen') == '*:8081'


def test_php_add_application():
    assert 'success' in client.conf(conf_basic)
    assert 'success' in client.conf(
        {**conf_app['app'], 'listen': '*:8082'}, 'applications/other'
    )

    assert client.conf_get('applications/app/listen') == '*:8080'
    assert client.conf_get('applications/other/listen') == '*:8082'


def test_php_change_application():
    assert 'success' in client.conf(conf_basic)

    assert 'success' in client.conf('30', 'applications/app/processes/max')
    assert (
        client.conf_get('applications/app/processes/max') == 30
    ), 'change application max'

    assert 'success' in client.conf('"/www"', 'applications/app/root')
    assert (
        client.conf_get('applications/app/root') == '/www'
    ), 'change application root'


def test_php_delete():
    assert 'success' in client.conf(conf_basic)

    assert 'error' in client.conf_delete('applications/app/listen')
    assert 'success' in client.conf_delete('applications/app')
    assert 'error' in client.conf_delete('applications/app')


def test_php_delete_blocks():
    assert 'success' in client.conf(conf_basic)

    assert 'success' in client.conf_delete('applications')

    assert 'success' in client.conf(conf_app, 'applications')
    assert 'success' in client.conf(
        '"*:8081"', 'applications/app/listen'
    ), 'applications restore'
