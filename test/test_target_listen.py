import copy
import json
import socket
from urllib.parse import quote

import pytest
from worker.applications.lang.python import ApplicationPython
from worker.option import option

prerequisites = {'modules': {'python': 'any'}}
client = ApplicationPython()


@pytest.fixture(autouse=True)
def setup_method_fixture():
    assert 'success' in client.conf({'applications': {'app': {
        'type': client.get_application_type(),
        'path': option.test_dir + '/python/listen',
        'processes': 1,
        'targets': {
            'first': {'listen': '127.0.0.1:8080', 'module': 'wsgi'},
            'second': {'listen': '127.0.0.1:8081', 'module': 'wsgi',
                       'callable': 'alternate'},
        },
    }}})


def test_target_listen_shared_process():
    first = client.get()['body']
    assert first.startswith('app:')
    assert client.get(port=8081)['body'] == 'alternate:' + first.split(':')[1]


@pytest.mark.parametrize('value', ['127.0.0.1:8082', '', None, []])
def test_target_listen_excludes_app_listen(value):
    before = client.conf_get()
    assert 'error' in client.conf(json.dumps(value), 'applications/app/listen')
    assert client.conf_get() == before
    assert client.get()['status'] == client.get(port=8081)['status'] == 200


@pytest.mark.parametrize('value', [None, True, 8082, '', [], {}, ['*:8082'], '127.0.0.1'])
def test_target_listen_invalid(value):
    before = client.conf_get()
    assert 'error' in client.conf(json.dumps(value), 'applications/app/targets/first/listen')
    assert client.conf_get() == before
    assert client.get()['status'] == 200


def test_target_listen_required():
    before = client.conf_get()
    assert 'error' in client.conf_delete('applications/app/targets/first/listen')
    assert 'error' in client.conf({'module': 'wsgi'}, 'applications/app/targets/third')
    assert 'error' in client.conf({}, 'applications/app/targets')
    assert 'error' in client.conf_delete('applications/app/targets')
    assert client.conf_get() == before


@pytest.mark.parametrize('scope', ['same_app', 'other_targets', 'ordinary_app'])
def test_target_listen_global_unique(scope):
    before = client.conf_get()
    if scope == 'same_app':
        response = client.conf('"127.0.0.1:8081"', 'applications/app/targets/first/listen')
    elif scope == 'other_targets':
        response = client.conf(before['applications']['app'], 'applications/other')
    else:
        response = client.conf({
            'listen': '127.0.0.1:8081', 'type': client.get_application_type(),
            'module': 'wsgi', 'processes': {'spare': 0},
        }, 'applications/other')
    assert 'same "listen" address' in response.get('detail', '')
    assert client.conf_get() == before


def test_target_listen_normalized_unique():
    before = client.conf_get()
    conf = copy.deepcopy(before)
    conf['applications']['app']['targets']['first']['listen'] = '*:8080'
    conf['applications']['app']['targets']['second']['listen'] = '0.0.0.0:8080'
    response = client.conf(conf)
    assert 'same "listen" address' in response.get('detail', '')
    assert client.conf_get() == before


def test_target_listen_update_and_swap():
    first = client.get()['body']
    second = client.get(port=8081)['body']
    assert 'success' in client.conf('"127.0.0.1:8082"', 'applications/app/targets/first/listen')
    assert client.get(port=8082)['body'] == first
    assert client.get(port=8081)['body'] == second
    conf = client.conf_get()
    conf['applications']['app']['targets']['first']['listen'] = '127.0.0.1:8081'
    conf['applications']['app']['targets']['second']['listen'] = '127.0.0.1:8082'
    assert 'success' in client.conf(conf)
    assert client.get(port=8081)['body'] == first
    assert client.get(port=8082)['body'] == second
    with socket.socket() as sock:
        sock.settimeout(1)
        assert sock.connect_ex(('127.0.0.1', 8080)) != 0


@pytest.mark.parametrize('add_app', [False, True])
def test_target_listen_bind_failure_rolls_back(skip_alert, add_app):
    skip_alert(r'bind.*failed', r'failed to apply new conf')
    before = client.conf_get()
    first = client.get()['body']
    second = client.get(port=8081)['body']
    with socket.socket() as occupied:
        occupied.bind(('127.0.0.1', 0))
        occupied.listen()
        address = '127.0.0.1:' + str(occupied.getsockname()[1])
        conf = copy.deepcopy(before)
        if add_app:
            conf['applications']['other'] = copy.deepcopy(conf['applications']['app'])
        targets = conf['applications']['other' if add_app else 'app']['targets']
        targets['first']['listen'] = '127.0.0.1:8082'
        targets['second']['listen'] = address
        assert 'error' in client.conf(conf)
    assert client.conf_get() == before
    assert client.get()['body'] == first
    assert client.get(port=8081)['body'] == second
    with socket.socket() as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(('127.0.0.1', 8082))
        sock.listen()


@pytest.mark.parametrize('name', ['a/b', 'a%b', '$arg_target', '\u76ee\u6807'])
def test_target_listen_literal_name(name):
    conf = client.conf_get()
    targets = conf['applications']['app']['targets']
    targets[name] = targets.pop('second')
    assert 'success' in client.conf(conf)
    assert client.get(port=8081)['body'].startswith('alternate:')
    path = 'applications/app/targets/' + quote(name, '') + '/listen'
    body = client.get(port=8081)['body']
    assert 'success' in client.conf('"127.0.0.1:8082"', path)
    assert client.get(port=8082)['body'] == body


def test_target_listen_delete():
    assert 'success' in client.conf_delete('applications/app/targets/first')
    assert 'error' in client.conf_delete('applications/app/targets/second')
    assert client.get(port=8081)['body'].startswith('alternate:')
    assert 'success' in client.conf_delete('applications/app')
    for port in (8080, 8081):
        with socket.socket() as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(('127.0.0.1', port))
            sock.listen()


def test_target_listen_unix_socket(temp_dir):
    address = 'unix:' + temp_dir + '/target.sock'
    first = client.get()['body']
    second = client.get(port=8081)['body']
    assert 'success' in client.conf(json.dumps(address), 'applications/app/targets/first/listen')
    assert client.get(sock_type='unix', addr=temp_dir + '/target.sock')['body'] == first
    assert client.get(port=8081)['body'] == second
    assert client.conf_get('applications/app/targets/first/listen') == address


@pytest.mark.parametrize('name', ['target', 'pass'])
def test_target_listen_no_selector_field(name):
    response = client.conf('"first"', 'applications/app/' + name)
    assert response.get('detail') == f'Unknown parameter "{name}".'


def test_target_listen_external_unsupported():
    response = client.conf({
        'type': 'external', 'executable': '/not-started', 'processes': {'spare': 0},
        'targets': {'first': {'listen': '127.0.0.1:8082'}},
    }, 'applications/go')
    assert response.get('detail') == 'Unknown parameter "targets".'
