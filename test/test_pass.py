from urllib.parse import quote

import pytest
from worker.applications.lang.python import ApplicationPython
from worker.option import option

prerequisites = {'modules': {'python': 'any'}}

client = ApplicationPython()


@pytest.fixture(autouse=True)
def setup_method_fixture():
    client.load('empty')


@pytest.mark.parametrize('name', ['plain', 'one/two', 'a b', 'a%b', 'routes', '\u5e94\u7528'])
def test_pass_application_name(name):
    app = client.conf_get('applications/empty')
    assert 'success' in client.conf(
        {
            'listeners': {'*:8080': {'pass': 'applications/' + quote(name, '')}},
            'applications': {name: app},
        }
    )
    assert client.get()['status'] == 200


def test_pass_application_variable():
    assert 'success' in client.conf(
        {'pass': 'applications/$arg_app'}, 'listeners/*:8080',
    )
    assert client.get(url='/?app=empty')['status'] == 200
    assert client.get(url='/?app=missing')['status'] == 404
    assert client.get()['status'] == 404
    assert client.get(url='/?app=empty')['status'] == 200


def test_pass_legacy_application():
    assert 'success' in client.conf(
        {'application': 'empty'}, 'listeners/*:8080',
    )
    assert client.get()['status'] == 200


def test_pass_target_variable():
    app = client.conf_get('applications/empty')
    app['path'] = option.test_dir + '/python/targets'
    del app['module']
    app['targets'] = {
        'first': {'module': 'wsgi', 'callable': 'wsgi_target_a'},
        'second': {'module': 'wsgi', 'callable': 'wsgi_target_b'},
    }
    assert 'success' in client.conf(app, 'applications/targets')
    assert 'success' in client.conf(
        {'pass': 'applications/$arg_app/$arg_target'}, 'listeners/*:8080',
    )
    assert client.get(url='/?app=targets&target=first')['body'] == '1'
    assert client.get(url='/?app=targets&target=second')['body'] == '2'
    assert client.get(url='/?app=targets&target=missing')['status'] == 404
    assert client.get(url='/?app=empty&target=first')['status'] == 404
    assert client.get(url='/?app=targets&target=first')['body'] == '1'


@pytest.mark.parametrize('target', [
    '', 'applications', 'applications/missing', 'applications/empty/missing',
    'applications//empty', 'applications/empty/extra/path', 'applications/%',
    'routes', 'routes/main', 'r%6futes/main',
])
def test_pass_invalid_preserves_configuration(target):
    before = client.conf_get()
    assert 'error' in client.conf({'pass': target}, 'listeners/*:8080')
    assert client.conf_get() == before
    assert client.get()['status'] == 200


@pytest.mark.parametrize('routes', [
    [], {}, [{'action': {'return': 200}}],
    {'main': [{'action': {'pass': 'applications/empty'}}]},
])
@pytest.mark.parametrize('whole_config', [False, True])
def test_routes_unsupported(routes, whole_config):
    before = client.conf_get()
    if whole_config:
        response = client.conf({**before, 'routes': routes})
    else:
        response = client.conf(routes, 'routes')
    assert response.get('detail') == 'Unknown parameter "routes".'
    assert client.conf_get() == before
    assert client.get()['status'] == 200


@pytest.mark.parametrize('name,value', [
    ('return', 200), ('location', '/'), ('action', {'return': 200}),
])
def test_listener_route_actions_unsupported(name, value):
    before = client.conf_get()
    response = client.conf(
        {'pass': 'applications/empty', name: value}, 'listeners/*:8080',
    )
    assert response.get('detail') == f'Unknown parameter "{name}".'
    assert client.conf_get() == before
    assert client.get()['status'] == 200
