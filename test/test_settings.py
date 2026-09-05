import re
import socket
import subprocess
import time

import pytest
from worker.applications.lang.python import ApplicationPython

prerequisites = {'modules': {'python': 'any'}}


client = ApplicationPython()

def sysctl():
    try:
        out = subprocess.check_output(
            ['sysctl', '-a'], stderr=subprocess.STDOUT
        ).decode()
    except FileNotFoundError:
        pytest.skip('requires sysctl')

    return out

@pytest.mark.parametrize('settings', [{}, {'mime_types': {'text/plain': ['txt']}}])
def test_settings_static_unsupported(settings):
    before = client.conf_get()
    resp = client.conf({'http': {'static': settings}}, 'settings')

    assert resp.get('detail') == 'Unknown parameter "static".'
    assert client.conf_get() == before


def test_settings_header_read_timeout():
    client.load('empty')

    def req():
        (_, sock) = client.http(
            b"""GET / HTTP/1.1
""",
            start=True,
            read_timeout=1,
            raw=True,
        )

        time.sleep(3)

        return client.http(
            b"""Host: localhost
Connection: close

""",
            sock=sock,
            raw=True,
        )

    assert 'success' in client.conf(
        {'http': {'header_read_timeout': 2}}, 'settings'
    )
    assert req()['status'] == 408, 'status header read timeout'

    assert 'success' in client.conf(
        {'http': {'header_read_timeout': 7}}, 'settings'
    )
    assert req()['status'] == 200, 'status header read timeout 2'

def test_settings_header_read_timeout_update():
    client.load('empty')

    assert 'success' in client.conf(
        {'http': {'header_read_timeout': 4}}, 'settings'
    )

    sock = client.http(
        b"""GET / HTTP/1.1
""",
        raw=True,
        no_recv=True,
    )

    time.sleep(2)

    sock = client.http(
        b"""Host: localhost
""",
        sock=sock,
        raw=True,
        no_recv=True,
    )

    time.sleep(2)

    (resp, sock) = client.http(
        b"""X-Blah: blah
""",
        start=True,
        sock=sock,
        read_timeout=1,
        raw=True,
    )

    if len(resp) != 0:
        sock.close()

    else:
        time.sleep(2)

        resp = client.http(
            b"""Connection: close

""",
            sock=sock,
            raw=True,
        )

    assert resp['status'] == 408, 'status header read timeout update'

def test_settings_body_read_timeout():
    client.load('empty')

    def req():
        (_, sock) = client.http(
            b"""POST / HTTP/1.1
Host: localhost
Content-Length: 10
Connection: close

""",
            start=True,
            raw_resp=True,
            read_timeout=1,
            raw=True,
        )

        time.sleep(3)

        return client.http(b"""0123456789""", sock=sock, raw=True)

    assert 'success' in client.conf(
        {'http': {'body_read_timeout': 2}}, 'settings'
    )
    assert req()['status'] == 408, 'status body read timeout'

    assert 'success' in client.conf(
        {'http': {'body_read_timeout': 7}}, 'settings'
    )
    assert req()['status'] == 200, 'status body read timeout 2'

def test_settings_body_read_timeout_update():
    client.load('empty')

    assert 'success' in client.conf(
        {'http': {'body_read_timeout': 4}}, 'settings'
    )

    (resp, sock) = client.http(
        b"""POST / HTTP/1.1
Host: localhost
Content-Length: 10
Connection: close

""",
        start=True,
        read_timeout=1,
        raw=True,
    )

    time.sleep(2)

    (resp, sock) = client.http(
        b"""012""", start=True, sock=sock, read_timeout=1, raw=True
    )

    time.sleep(2)

    (resp, sock) = client.http(
        b"""345""", start=True, sock=sock, read_timeout=1, raw=True
    )

    time.sleep(2)

    resp = client.http(b"""6789""", sock=sock, raw=True)

    assert resp['status'] == 200, 'status body read timeout update'

def test_settings_send_timeout(temp_dir):
    client.load('body_generate')

    def req(addr, data_len):
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.connect(addr)

        req = (
            """GET / HTTP/1.1
Host: localhost
X-Length: %d
Connection: close

"""
            % data_len
        )

        sock.sendall(req.encode())

        data = sock.recv(16).decode()

        time.sleep(3)

        data += client.recvall(sock).decode()

        sock.close()

        return data

    sysctl_out = sysctl()
    values = re.findall(
        r'net.core.[rw]mem_(?:max|default).*?(\d+)', sysctl_out
    )
    values = [int(v) for v in values]

    data_len = 1048576 if len(values) == 0 else 10 * max(values)

    addr = temp_dir + '/sock'

    assert 'success' in client.conf(
        {"unix:" + addr: {'application': 'body_generate'}}, 'listeners'
    )

    assert 'success' in client.conf(
        {'http': {'send_timeout': 1}}, 'settings'
    )

    data = req(addr, data_len)
    assert re.search(r'200 OK', data), 'send timeout status'
    assert len(data) < data_len, 'send timeout data '

    client.conf({'http': {'send_timeout': 7}}, 'settings')

    data = req(addr, data_len)
    assert re.search(r'200 OK', data), 'send timeout status  2'
    assert len(data) > data_len, 'send timeout data 2'

def test_settings_idle_timeout():
    client.load('empty')

    def req():
        (_, sock) = client.get(
            headers={'Host': 'localhost', 'Connection': 'keep-alive'},
            start=True,
            read_timeout=1,
        )

        time.sleep(3)

        return client.get(sock=sock)

    assert client.get()['status'] == 200, 'init'

    assert 'success' in client.conf(
        {'http': {'idle_timeout': 2}}, 'settings'
    )
    assert req()['status'] == 408, 'status idle timeout'

    assert 'success' in client.conf(
        {'http': {'idle_timeout': 7}}, 'settings'
    )
    assert req()['status'] == 200, 'status idle timeout 2'

def test_settings_idle_timeout_2():
    client.load('empty')

    def req():
        sock = client.http(b'', raw=True, no_recv=True)

        time.sleep(3)

        return client.get(sock=sock)

    assert client.get()['status'] == 200, 'init'

    assert 'success' in client.conf(
        {'http': {'idle_timeout': 1}}, 'settings'
    )
    assert req()['status'] == 408, 'status idle timeout'

    assert 'success' in client.conf(
        {'http': {'idle_timeout': 7}}, 'settings'
    )
    assert req()['status'] == 200, 'status idle timeout 2'

def test_settings_max_body_size():
    client.load('empty')

    assert 'success' in client.conf(
        {'http': {'max_body_size': 5}}, 'settings'
    )

    assert client.post(body='01234')['status'] == 200, 'status size'
    assert client.post(body='012345')['status'] == 413, 'status size max'

def test_settings_max_body_size_large():
    client.load('mirror')

    assert 'success' in client.conf(
        {'http': {'max_body_size': 32 * 1024 * 1024}}, 'settings'
    )

    body = '0123456789abcdef' * 4 * 64 * 1024
    resp = client.post(body=body, read_buffer_size=1024 * 1024)
    assert resp['status'] == 200, 'status size 4'
    assert resp['body'] == body, 'status body 4'

    body = '0123456789abcdef' * 8 * 64 * 1024
    resp = client.post(body=body, read_buffer_size=1024 * 1024)
    assert resp['status'] == 200, 'status size 8'
    assert resp['body'] == body, 'status body 8'

    body = '0123456789abcdef' * 16 * 64 * 1024
    resp = client.post(body=body, read_buffer_size=1024 * 1024)
    assert resp['status'] == 200, 'status size 16'
    assert resp['body'] == body, 'status body 16'

    body = '0123456789abcdef' * 32 * 64 * 1024
    resp = client.post(body=body, read_buffer_size=1024 * 1024)
    assert resp['status'] == 200, 'status size 32'
    assert resp['body'] == body, 'status body 32'

@pytest.mark.skip('not yet')
def test_settings_negative_value():
    assert 'error' in client.conf(
        {'http': {'max_body_size': -1}}, 'settings'
    ), 'settings negative value'

def test_settings_body_buffer_size():
    client.load('mirror')

    assert 'success' in client.conf(
        {
            'http': {
                'max_body_size': 64 * 1024 * 1024,
                'body_buffer_size': 32 * 1024 * 1024,
            }
        },
        'settings',
    )

    body = '0123456789abcdef'
    resp = client.post(body=body)
    assert bool(resp), 'response from application'
    assert resp['status'] == 200, 'status'
    assert resp['body'] == body, 'body'

    body = '0123456789abcdef' * 1024 * 1024
    resp = client.post(body=body, read_buffer_size=1024 * 1024)
    assert bool(resp), 'response from application 2'
    assert resp['status'] == 200, 'status 2'
    assert resp['body'] == body, 'body 2'

    body = '0123456789abcdef' * 2 * 1024 * 1024
    resp = client.post(body=body, read_buffer_size=1024 * 1024)
    assert bool(resp), 'response from application 3'
    assert resp['status'] == 200, 'status 3'
    assert resp['body'] == body, 'body 3'

    body = '0123456789abcdef' * 3 * 1024 * 1024
    resp = client.post(body=body, read_buffer_size=1024 * 1024)
    assert bool(resp), 'response from application 4'
    assert resp['status'] == 200, 'status 4'
    assert resp['body'] == body, 'body 4'
