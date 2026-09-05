import json
import socket
import sys
from urllib.parse import quote

import pytest
from worker.applications.lang.python import ApplicationPython

prerequisites = {'modules': {'python': 'any'}}
client = ApplicationPython()


@pytest.fixture(autouse=True)
def setup_method_fixture():
    client.load('listen', processes=1, listen='127.0.0.1:8080')


def assert_closed(port):
    with socket.socket() as sock:
        sock.settimeout(1)
        assert sock.connect_ex(('127.0.0.1', port)) != 0


def test_listen_required():
    before = client.conf_get()
    app = client.conf_get('applications/listen')
    del app['listen']
    for response in (
        client.conf(app, 'applications/other'),
        client.conf(app, 'applications/listen'),
        client.conf_delete('applications/listen/listen'),
    ):
        assert response.get('detail') == 'Required parameter "listen" is missing.'
    assert client.conf_get() == before
    assert client.get()['status'] == 200


@pytest.mark.parametrize('address', [
    None, True, 8080, {}, [], ['127.0.0.1:8080'], '', '127.0.0.1',
    '127.0.0.1:0', '127.0.0.1:65536', 'not-an-address',
])
def test_listen_invalid(address):
    before = client.conf_get()
    body = client.get()['body']
    assert 'error' in client.conf(json.dumps(address), 'applications/listen/listen')
    assert client.conf_get() == before
    assert client.get()['body'] == body


@pytest.mark.parametrize('addresses', [
    ('127.0.0.1:8081', '127.0.0.1:8081'),
    ('*:8081', '0.0.0.0:8081'),
    ('[::1]:8081', '[0:0:0:0:0:0:0:1]:8081'),
    ('unix:/tmp/worker-listen-duplicate.sock', 'unix:/tmp/worker-listen-duplicate.sock'),
])
def test_listen_unique(addresses):
    before = client.conf_get()
    app = before['applications']['listen']
    response = client.conf({'applications': {
        'first': {**app, 'listen': addresses[0]},
        'second': {**app, 'listen': addresses[1]},
    }})
    assert 'same "listen" address' in response.get('detail', '')
    assert client.conf_get() == before
    assert client.get()['status'] == 200


@pytest.mark.parametrize('listeners', [{}, {'*:8080': {'pass': 'applications/listen'}}])
def test_listeners_removed(listeners):
    before = client.conf_get()
    for response in (
        client.conf(listeners, 'listeners'),
        client.conf({**before, 'listeners': listeners}),
    ):
        assert response.get('detail') == 'Unknown parameter "listeners".'
    assert 'error' in client.conf_get('listeners')
    assert client.conf_get() == before


def test_listen_update_reuses_process():
    body = client.get()['body']
    assert 'success' in client.conf('"127.0.0.1:8081"', 'applications/listen/listen')
    assert client.get(port=8081)['body'] == body
    assert_closed(8080)
    assert 'success' in client.conf('"127.0.0.1:8080"', 'applications/listen/listen')
    assert client.get()['body'] == body
    assert_closed(8081)


@pytest.mark.parametrize('add_app', [False, True])
def test_listen_bind_failure_rolls_back(skip_alert, add_app):
    skip_alert(r'bind.*failed', r'failed to apply new conf')
    body = client.get()['body']
    before = client.conf_get()
    with socket.socket() as occupied:
        occupied.bind(('127.0.0.1', 0))
        occupied.listen()
        address = '127.0.0.1:' + str(occupied.getsockname()[1])
        if add_app:
            response = client.conf(
                {**before['applications']['listen'], 'listen': address},
                'applications/other',
            )
        else:
            response = client.conf(json.dumps(address), 'applications/listen/listen')
        assert 'error' in response
    assert client.conf_get() == before
    assert client.get()['body'] == body
    assert 'success' in client.conf('"127.0.0.1:8081"', 'applications/listen/listen')
    assert client.get(port=8081)['body'] == body


def test_listen_multiple_apps_and_swap():
    app = client.conf_get('applications/listen')
    conf = {'applications': {
        'first': {**app, 'environment': {'APP_NAME': 'first'}},
        'second': {**app, 'listen': '127.0.0.1:8081',
                   'environment': {'APP_NAME': 'second'}},
    }}
    assert 'success' in client.conf(conf)
    first = client.get()['body']
    second = client.get(port=8081)['body']
    assert first.startswith('first:')
    assert second.startswith('second:')
    assert 'error' in client.conf('"127.0.0.1:8081"', 'applications/first/listen')
    conf['applications']['first']['listen'] = '127.0.0.1:8081'
    conf['applications']['second']['listen'] = '127.0.0.1:8080'
    assert 'success' in client.conf(conf)
    assert client.get()['body'] == second
    assert client.get(port=8081)['body'] == first


def test_listen_same_port_different_ips():
    app = client.conf_get('applications/listen')
    assert 'success' in client.conf(
        {**app, 'listen': '127.0.0.2:8080', 'environment': {'APP_NAME': 'other'}},
        'applications/other',
    )
    assert client.get()['body'].startswith('app:')
    assert client.get(addr='127.0.0.2')['body'].startswith('other:')


@pytest.mark.parametrize('abstract', [False, True])
def test_listen_unix_socket(temp_dir, abstract):
    if abstract and sys.platform != 'linux':
        pytest.skip('abstract Unix sockets require Linux')
    path = ('@' if abstract else '') + temp_dir + '/listen.sock'
    address = 'unix:' + path
    body = client.get()['body']
    assert 'success' in client.conf(json.dumps(address), 'applications/listen/listen')
    assert client.conf_get('applications/listen/listen') == address
    assert client.get(sock_type='unix', addr=path.replace('@', '\0', 1))['body'] == body
    assert 'error' in client.conf(client.conf_get('applications/listen'), 'applications/other')
    assert client.conf_get('applications/listen/listen') == address


@pytest.mark.parametrize('name', ['plain', 'one/two', 'a b', 'a%b', '$arg_app', '`app`', '\u5e94\u7528'])
def test_listen_application_name(name):
    app = client.conf_get('applications/listen')
    assert 'success' in client.conf({'applications': {name: app}})
    assert client.get()['status'] == 200
    assert client.conf_get('applications/' + quote(name, '') + '/listen') == app['listen']


def test_listen_delete_releases_address():
    assert 'success' in client.conf_delete('applications/listen')
    assert_closed(8080)
    with socket.socket() as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(('127.0.0.1', 8080))
        sock.listen()
    assert client.conf_get() == {'applications': {}}


@pytest.mark.parametrize('delete', [False, True])
def test_listen_inflight_request(delete):
    client.load('delayed', listen='127.0.0.1:8080')
    sock = client.post(body='aaaa', headers={
        'Host': 'localhost', 'X-Parts': '2', 'X-Delay': '1', 'Connection': 'close',
    }, no_recv=True)
    try:
        sock.settimeout(5)
        received = b''
        while b'\r\n\r\naa' not in received:
            part = sock.recv(4096)
            assert part
            received += part
        if delete:
            assert 'success' in client.conf_delete('applications/delayed')
        else:
            assert 'success' in client.conf('"127.0.0.1:8081"', 'applications/delayed/listen')
            assert client.get(port=8081)['status'] == 200
        assert_closed(8080)
        while True:
            part = sock.recv(4096)
            if not part:
                break
            received += part
        assert received.split(b'\r\n\r\n', 1)[1] == b'aaaa'
    finally:
        sock.close()
