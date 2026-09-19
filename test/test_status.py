import os
import signal
import socket
import struct
import time

import pytest

from worker.applications.lang.python import ApplicationPython
from worker.option import option
from worker.status import Status

prerequisites = {'modules': {'python': 'any'}}


client = ApplicationPython()


def app_default(name="empty", module="wsgi", listen="*:8080"):
    return {
        "listen": listen,
        "type": client.get_application_type(),
        "processes": {"spare": 0},
        "path": option.test_dir + "/python/" + name,
        "working_directory": option.test_dir + "/python/" + name,
        "module": module,
    }

def test_status():
    assert 'error' in client.conf_delete('/status'), 'DELETE method'
    assert set(client.conf_get('/status')) == {
        'processes', 'requests', 'responses', 'latency', 'applications',
    }
    assert 'error' in client.conf_get('/status/connections')


def check_aggregate():
    status = client.conf_get('/status')
    apps = list(status['applications'].values())

    for app in apps:
        assert set(app) == {'processes', 'requests', 'responses', 'latency'}

    for group in ('processes', 'requests', 'responses'):
        assert status[group] == {
            key: sum(app[group][key] for app in apps) for key in status[group]
        }

    requests = status['requests']
    assert requests['total'] == (
        requests['waiting'] + requests['processing'] + requests['completed']
    )

    sampled = [
        app['latency'] for app in apps if app['latency']['p50'] is not None
    ]
    if sampled:
        for key, value in status['latency'].items():
            assert min(app[key] for app in sampled) <= value <= max(
                app[key] for app in sampled
            )
    else:
        assert status['latency'] == {'p50': None, 'p95': None, 'p99': None}

    return status


def test_status_aggregate(temp_dir):
    release_path = temp_dir + '/release-aggregate'
    one = app_default('request_status')
    one['processes'] = 2
    two = app_default('request_status', listen='*:8081')
    two['processes'] = 1
    two['environment'] = {'RELEASE_PATH': release_path}

    assert 'success' in client.conf({'applications': {'one': one, 'two': two}})
    status = check_aggregate()
    assert status['processes'] == {
        'running': 3, 'idle': 3, 'starting': 0, 'stopping': 0,
    }
    assert status['requests']['total'] == 0

    assert client.get()['status'] == 200
    assert client.get(port=8081, headers={
        'Host': 'localhost', 'X-Status': '404', 'Connection': 'close',
    })['status'] == 404

    socks = []
    try:
        socks.append(client.get(
            port=8081,
            headers={'Host': 'localhost', 'X-Wait': '1', 'Connection': 'close'},
            no_recv=True,
        ))
        wait_requests('two', total=2, processing=1, completed=1)
        socks.append(client.get(port=8081, no_recv=True))
        wait_requests('two', total=3, waiting=1, processing=1, completed=1)

        status = check_aggregate()
        assert status['requests'] == {
            'total': 4, 'waiting': 1, 'processing': 1, 'completed': 2,
        }
        assert status['responses'] == {
            '1xx': 0, '2xx': 1, '3xx': 0, '4xx': 1, '5xx': 0,
        }
        open(release_path, 'a').close()
        for sock in socks:
            assert b'HTTP/1.1 200' in client.recvall(sock)
        wait_requests('two', total=3, completed=3)
    finally:
        open(release_path, 'a').close()
        for sock in socks:
            sock.close()

    assert check_aggregate()['requests']['completed'] == 4
    assert 'success' in client.conf_delete('applications/one')
    status = check_aggregate()
    assert status['requests']['total'] == 3
    assert {
        key: status[key]
        for key in ('processes', 'requests', 'responses', 'latency')
    } == status['applications']['two']

    assert 'success' in client.conf(
        {'REVISION': '2'}, 'applications/two/environment'
    )
    wait_requests('two')
    status = check_aggregate()
    assert status['requests']['total'] == 0
    assert status['responses'] == {
        '1xx': 0, '2xx': 0, '3xx': 0, '4xx': 0, '5xx': 0,
    }

    assert 'success' in client.conf_delete('applications/two')
    Status._check_zeros()


def test_status_aggregate_latency():
    fast = app_default('request_status')
    fast['processes'] = 1
    slow = app_default('request_status', listen='*:8081')
    slow['processes'] = 1
    assert 'success' in client.conf(
        {'applications': {'fast': fast, 'slow': slow}}
    )

    for _ in range(20):
        assert client.get()['status'] == 200
    assert client.get(port=8081, headers={
        'Host': 'localhost', 'X-Delay': '0.2', 'Connection': 'close',
    })['status'] == 200
    wait_requests('fast', total=20, completed=20)
    wait_requests('slow', total=1, completed=1)

    status = check_aggregate()
    fast_latency = status['applications']['fast']['latency']
    slow_latency = status['applications']['slow']['latency']
    assert fast_latency['p99'] < slow_latency['p50']
    assert status['latency']['p50'] <= fast_latency['p99']
    assert status['latency']['p95'] == fast_latency['p99']
    assert status['latency']['p99'] == slow_latency['p99']
    assert status['requests']['total'] == 21


def test_status_requests(skip_alert):
    skip_alert(r'Python failed to import module "blah"')

    assert 'success' in client.conf(
        {
            "applications": {
                "empty": app_default(),
                "other": app_default(listen="*:8081"),
                "blah": {
                    "listen": "*:8082",
                    "type": client.get_application_type(),
                    "processes": {"spare": 0},
                    "module": "blah",
                },
            },
        },
    )

    Status.init()

    assert client.get()['status'] == 200
    assert Status.get('/requests/total') == 1, '2xx'

    assert client.get(port=8081)['status'] == 200
    assert Status.get('/requests/total') == 2, '2xx app'

    assert (
        client.get(headers={'Host': '/', 'Connection': 'close'})['status']
        == 400
    )
    assert Status.get('/requests/total') == 2, 'rejected before app dispatch'
    wait_requests('empty', total=1, completed=1)
    wait_responses('empty', {'2xx': 1})

    assert client.get(port=8082)['status'] == 503
    assert Status.get('/requests/total') == 3, '5xx'
    wait_requests('blah', total=1, completed=1)
    wait_responses('blah', {'5xx': 1})
    check_empty_latency('blah')

    client.http(
        b"""GET / HTTP/1.1
Host: localhost

GET / HTTP/1.1
Host: localhost
Connection: close

""",
        raw=True,
    )
    assert Status.get('/requests/total') == 5, 'pipeline'
    wait_requests('empty', total=3, completed=3)
    wait_responses('empty', {'2xx': 3})

    sock = client.get(port=8081, no_recv=True)

    time.sleep(1)

    assert Status.get('/requests/total') == 6, 'no receive'

    sock.close()
    wait_requests('other', total=2, completed=2)

def test_status_requests_keepalive():
    assert 'success' in client.conf(
        {
            "applications": {
                "empty": app_default(),
                "delayed": app_default("delayed", listen="*:8081"),
            },
        },
    )

    Status.init()

    assert client.get()['status'] == 200
    assert Status.get('/requests/total') == 1

    # idle

    (_, sock) = client.get(
        headers={'Host': 'localhost', 'Connection': 'keep-alive'},
        start=True,
        read_timeout=1,
    )

    assert Status.get('/requests/total') == 2

    assert client.get(sock=sock)['status'] == 200
    assert Status.get('/requests/total') == 3
    wait_responses('empty', {'2xx': 3})

    # active

    (_, sock) = client.get(
        headers={
            'Host': 'localhost',
            'X-Delay': '2',
            'Connection': 'close',
        },
        port=8081,
        start=True,
        read_timeout=1,
    )
    assert Status.get('/requests/total') == 4

    client.recvall(sock)
    sock.close()
    assert Status.get('/requests/total') == 4

def test_status_applications():
    def check_applications(expert):
        apps = list(client.conf_get('/status/applications').keys()).sort()
        assert apps == expert.sort()

    def check_application(name, running, starting, idle, total=0,
                          waiting=0, processing=0, completed=0, response_2xx=0):
        expected = {
            'processes': {
                'running': running,
                'starting': starting,
                'idle': idle,
                'stopping': 0,
            },
            'requests': {
                'total': total,
                'waiting': waiting,
                'processing': processing,
                'completed': completed,
            },
            'responses': {
                '1xx': 0,
                '2xx': response_2xx,
                '3xx': 0,
                '4xx': 0,
                '5xx': 0,
            },
        }

        for _ in range(100):
            status = Status.get(f'/applications/{name}')
            status.pop('latency')
            if status == expected:
                return
            time.sleep(0.05)

        assert status == expected

    client.load('delayed')
    wait_processes('delayed')
    Status.init()

    check_applications(['delayed'])
    check_application('delayed', 0, 0, 0)

    # idle

    assert client.get()['status'] == 200
    check_application('delayed', 1, 0, 1, total=1, completed=1, response_2xx=1)

    assert 'success' in client.conf('4', 'applications/delayed/processes')
    wait_processes('delayed', running=4, idle=4)
    check_application('delayed', 4, 0, 4)

    # active

    (_, sock) = client.get(
        headers={
            'Host': 'localhost',
            'X-Delay': '2',
            'Connection': 'close',
        },
        start=True,
        read_timeout=1,
    )
    check_application('delayed', 4, 0, 3, total=1, processing=1, response_2xx=1)
    sock.close()

    # starting

    assert 'success' in client.conf(
        {
            "applications": {
                "restart": app_default("restart", "longstart"),
                "delayed": app_default("delayed", listen="*:8081"),
            },
        },
    )
    wait_processes('delayed')
    wait_processes('restart')
    Status.init()

    check_applications(['delayed', 'restart'])
    check_application('restart', 0, 0, 0)
    check_application('delayed', 0, 0, 0)

    client.get(read_timeout=1)

    check_application('restart', 0, 1, 0, total=1, waiting=1)
    check_application('delayed', 0, 0, 0)
    wait_processes('restart', running=1, idle=1)
    wait_requests('restart', total=1, completed=1)


def wait_requests(name, total=0, waiting=0, processing=0, completed=0):
    expected = {
        'total': total,
        'waiting': waiting,
        'processing': processing,
        'completed': completed,
    }

    for _ in range(100):
        requests = client.conf_get(f'/status/applications/{name}/requests')
        assert requests['total'] == (
            requests['waiting'] + requests['processing'] + requests['completed']
        )
        if requests == expected:
            return
        time.sleep(0.05)

    assert requests == expected


def wait_responses(name, counts=None):
    expected = {key: 0 for key in ('1xx', '2xx', '3xx', '4xx', '5xx')}
    expected.update(counts or {})

    for _ in range(100):
        responses = client.conf_get(f'/status/applications/{name}/responses')
        if responses == expected:
            return
        time.sleep(0.05)

    assert responses == expected


def check_latency(name, minimum=0, maximum=1000):
    latency = client.conf_get(f'/status/applications/{name}/latency')
    assert set(latency) == {'p50', 'p95', 'p99'}
    assert all(isinstance(value, int) for value in latency.values())
    assert (
        minimum <= latency['p50'] <= latency['p95'] <= latency['p99'] <= maximum
    )
    return latency


def check_empty_latency(name):
    assert client.conf_get(f'/status/applications/{name}/latency') == {
        'p50': None,
        'p95': None,
        'p99': None,
    }


@pytest.mark.parametrize('status', [200, 500])
def test_status_application_latency_completion(status, temp_dir):
    release_path = temp_dir + '/release-latency'
    client.load('request_status', environment={'RELEASE_PATH': release_path})
    check_empty_latency('request_status')

    sock = client.get(
        headers={
            'Host': 'localhost',
            'X-Wait': '1',
            'X-Status': str(status),
            'Connection': 'close',
        },
        no_recv=True,
    )
    try:
        wait_requests('request_status', total=1, processing=1)
        check_empty_latency('request_status')
        time.sleep(0.15)
        open(release_path, 'a').close()
        assert f'HTTP/1.1 {status}'.encode() in client.recvall(sock)
        wait_requests('request_status', total=1, completed=1)
        latency = check_latency('request_status', minimum=100)
        assert latency['p50'] == latency['p95'] == latency['p99']
    finally:
        open(release_path, 'a').close()
        sock.close()


def test_status_application_latency_excludes_waiting():
    client.load('request_status', processes=1)
    pid = int(client.get()['body'])
    os.kill(pid, signal.SIGSTOP)
    sock = None
    try:
        sock = client.get(
            headers={
                'Host': 'localhost', 'X-Delay': '0.2', 'Connection': 'close',
            },
            no_recv=True,
        )
        wait_requests('request_status', total=2, waiting=1, completed=1)
        time.sleep(1.2)
        os.kill(pid, signal.SIGCONT)
        assert b'HTTP/1.1 200' in client.recvall(sock)
        wait_requests('request_status', total=2, completed=2)
        latency = check_latency('request_status', maximum=800)
        assert latency['p99'] >= 150
    finally:
        os.kill(pid, signal.SIGCONT)
        if sock is not None:
            sock.close()


def test_status_application_response_classes():
    client.load('request_status')
    wait_responses('request_status')
    counts = {}

    for status, group in (
        (200, '2xx'), (299, '2xx'), (302, '3xx'), (404, '4xx'),
        (500, '5xx'), (599, '5xx'), (100, None), (103, None), (600, None),
    ):
        assert client.get(headers={
            'Host': 'localhost', 'X-Status': str(status), 'Connection': 'close',
        })['status'] == status

        if group is not None:
            counts[group] = counts.get(group, 0) + 1
        wait_responses('request_status', counts)

    wait_requests('request_status', total=9, completed=9)


@pytest.mark.parametrize('timeout', [False, True])
def test_status_application_response_stream(timeout, temp_dir):
    release_path = temp_dir + '/release-response'
    client.load(
        'request_status',
        environment={'RELEASE_PATH': release_path},
        limits={'timeout': 1 if timeout else 0},
    )
    sock = client.get(
        headers={
            'Host': 'localhost', 'X-Wait-Body': '1', 'Connection': 'close',
        },
        no_recv=True,
    )
    try:
        wait_responses('request_status', {'2xx': 1})
        wait_requests('request_status', total=1, processing=1)
        first = client.recvall(sock, read_timeout=0.1)
        assert b'HTTP/1.1 200' in first
        assert b'Transfer-Encoding: chunked' in first

        if not timeout:
            open(release_path, 'a').close()
        rest = client.recvall(sock)
        if not timeout:
            assert rest.endswith(b'0\r\n\r\n')
        wait_requests('request_status', total=1, completed=1)
        wait_responses('request_status', {'2xx': 1})
    finally:
        open(release_path, 'a').close()
        sock.close()

    assert client.get()['status'] == 200
    wait_responses('request_status', {'2xx': 2})


def test_status_application_response_reconfigure(temp_dir):
    release_path = temp_dir + '/release-response'
    client.load('request_status', environment={'RELEASE_PATH': release_path})
    sock = client.get(
        headers={'Host': 'localhost', 'X-Wait': '1', 'Connection': 'close'},
        no_recv=True,
    )
    try:
        wait_requests('request_status', total=1, processing=1)
        wait_responses('request_status')
        assert 'success' in client.conf(
            {'REVISION': '2'}, 'applications/request_status/environment'
        )
        wait_responses('request_status')
        open(release_path, 'a').close()
        assert b'HTTP/1.1 200' in client.recvall(sock)
        wait_responses('request_status')
        wait_requests('request_status')
    finally:
        open(release_path, 'a').close()
        sock.close()

    assert client.get()['status'] == 200
    wait_responses('request_status', {'2xx': 1})


@pytest.mark.parametrize(
    'finish', ['complete', 'disconnect_waiting', 'disconnect_processing']
)
def test_status_application_request_lifecycle(finish, temp_dir):
    release_path = temp_dir + '/release'
    client.load(
        'request_status',
        processes=1,
        environment={'RELEASE_PATH': release_path},
    )
    wait_requests('request_status')
    pid = int(client.get()['body'])
    wait_requests('request_status', total=1, completed=1)

    os.kill(pid, signal.SIGSTOP)
    sock = None
    try:
        sock = client.get(
            headers={
                'Host': 'localhost',
                'X-Wait': '1',
                'Connection': 'close',
            },
            no_recv=True,
        )
        wait_requests('request_status', total=2, waiting=1, completed=1)

        if finish != 'disconnect_waiting':
            os.kill(pid, signal.SIGCONT)
            wait_requests('request_status', total=2, processing=1, completed=1)

        if finish == 'complete':
            open(release_path, 'a').close()
            response = client.recvall(sock)
            assert b'HTTP/1.1 200' in response
            assert response.endswith(str(pid).encode())
        else:
            sock.setsockopt(
                socket.SOL_SOCKET, socket.SO_LINGER, struct.pack('ii', 1, 0)
            )
            sock.close()
            os.kill(pid, signal.SIGCONT)
            open(release_path, 'a').close()

        wait_requests('request_status', total=2, completed=2)
    finally:
        open(release_path, 'a').close()
        os.kill(pid, signal.SIGCONT)
        if sock is not None:
            sock.close()

    assert client.get()['status'] == 200
    wait_requests('request_status', total=3, completed=3)


def test_status_application_request_process_exit(skip_alert, temp_dir):
    release_path = temp_dir + '/release'
    client.load('request_status', environment={'RELEASE_PATH': release_path})
    pid = int(client.get()['body'])
    sock = client.get(
        headers={
            'Host': 'localhost',
            'X-Wait': '1',
            'Connection': 'close',
        },
        no_recv=True,
    )
    try:
        wait_requests('request_status', total=2, processing=1, completed=1)
        time.sleep(0.15)
        skip_alert(fr'app process {pid} exited on signal 9')
        os.kill(pid, signal.SIGKILL)
        assert b'HTTP/1.1 503' in client.recvall(sock)
        wait_requests('request_status', total=2, completed=2)
        wait_responses('request_status', {'2xx': 1, '5xx': 1})
        assert check_latency('request_status')['p99'] >= 100
    finally:
        open(release_path, 'a').close()
        sock.close()

    assert client.get()['status'] == 200
    wait_requests('request_status', total=3, completed=3)


def test_status_application_request_queue(temp_dir):
    release_path = temp_dir + '/release'
    client.load(
        'request_status',
        processes=1,
        environment={'RELEASE_PATH': release_path},
    )
    assert client.get()['status'] == 200
    socks = []
    try:
        for _ in range(5):
            socks.append(client.get(
                headers={
                    'Host': 'localhost',
                    'X-Wait': '1',
                    'Connection': 'close',
                },
                no_recv=True,
            ))

        wait_requests('request_status', total=6, waiting=4,
                      processing=1, completed=1)
        open(release_path, 'a').close()
        for sock in socks:
            assert b'HTTP/1.1 200' in client.recvall(sock)
        wait_requests('request_status', total=6, completed=6)
    finally:
        open(release_path, 'a').close()
        for sock in socks:
            sock.close()


def test_status_application_request_timeout():
    client.load('request_status', limits={'timeout': 1})
    sock = client.get(
        headers={'Host': 'localhost', 'X-Delay': '2', 'Connection': 'close'},
        no_recv=True,
    )
    try:
        wait_requests('request_status', total=1, processing=1)
        assert b'HTTP/1.1 503' in client.recvall(sock)
        wait_requests('request_status', total=1, completed=1)
        wait_responses('request_status', {'5xx': 1})
        check_latency('request_status', minimum=800, maximum=1500)
    finally:
        sock.close()

    wait_processes('request_status', running=1, idle=1)
    assert client.get()['status'] == 200
    wait_requests('request_status', total=2, completed=2)


def test_status_application_request_counter_lifetime():
    client.load('request_status', processes=1)
    assert client.get()['status'] == 200
    wait_requests('request_status', total=1, completed=1)
    latency = check_latency('request_status')

    assert 'success' in client.conf_get(
        '/control/applications/request_status/restart'
    )
    wait_processes('request_status', running=1, idle=1)
    wait_requests('request_status', total=1, completed=1)
    wait_responses('request_status', {'2xx': 1})
    assert check_latency('request_status') == latency

    assert 'success' in client.conf(
        '"*:8081"', 'applications/request_status/listen'
    )
    wait_requests('request_status', total=1, completed=1)
    assert client.get(port=8081)['status'] == 200
    wait_requests('request_status', total=2, completed=2)

    assert 'success' in client.conf(
        {'REVISION': '2'}, 'applications/request_status/environment'
    )
    wait_requests('request_status')
    wait_responses('request_status')
    check_empty_latency('request_status')
    assert client.get(
        port=8081,
        headers={'Host': 'localhost', 'X-Status': '500', 'Connection': 'close'},
    )['status'] == 500
    wait_requests('request_status', total=1, completed=1)
    wait_responses('request_status', {'5xx': 1})


def wait_processes(name, running=0, starting=0, idle=0, stopping=0):
    expected = {
        'running': running,
        'starting': starting,
        'idle': idle,
        'stopping': stopping,
    }

    for _ in range(100):
        processes = client.conf_get(f'/status/applications/{name}/processes')
        if processes == expected:
            return
        time.sleep(0.05)

    assert processes == expected


@pytest.mark.parametrize('action', ['idle', 'restart', 'reconfigure'])
@pytest.mark.parametrize('exit_signal', [signal.SIGCONT, signal.SIGKILL])
def test_status_applications_stopping(action, exit_signal, skip_alert):
    client.load(
        'listen',
        name='stopping',
        processes={'spare': 0, 'idle_timeout': 1 if action == 'idle' else 60},
    )
    assert 'success' in client.conf(
        app_default(listen='*:8081'), 'applications/other'
    )

    pid = int(client.get()['body'].split(':')[1])
    wait_processes('stopping', running=1, idle=1)

    os.kill(pid, signal.SIGSTOP)
    try:
        if action == 'restart':
            assert 'success' in client.conf_get(
                '/control/applications/stopping/restart'
            )
        elif action == 'reconfigure':
            assert 'success' in client.conf(
                {'REVISION': '1'}, 'applications/stopping/environment'
            )

        wait_processes('stopping', stopping=1)
        wait_processes('other')

        running = 0
        if action == 'restart':
            assert 'success' in client.conf_get(
                '/control/applications/stopping/restart'
            )
            wait_processes('stopping', stopping=1)
        else:
            # Exit records survive replacement of the application object.
            assert 'success' in client.conf(
                {'REVISION': '2'}, 'applications/stopping/environment'
            )
            wait_processes('stopping', stopping=1)
            assert client.get()['status'] == 200
            running = 1
            wait_processes('stopping', running=1, idle=1, stopping=1)

        if exit_signal == signal.SIGKILL:
            skip_alert(fr'app process {pid} exited on signal 9')
        os.kill(pid, exit_signal)
        wait_processes('stopping', running=running, idle=running)
    finally:
        try:
            os.kill(pid, signal.SIGCONT)
        except ProcessLookupError:
            pass

    assert client.get()['status'] == 200
    wait_processes('stopping', running=1, idle=1)


def test_status_applications_stopping_active():
    client.load('delayed', name='stopping')
    sock = client.get(
        headers={'Host': 'localhost', 'X-Delay': '2', 'Connection': 'close'},
        no_recv=True,
    )
    try:
        wait_processes('stopping', running=1)
        assert 'success' in client.conf_get(
            '/control/applications/stopping/restart'
        )
        wait_processes('stopping', stopping=1)
        assert (
            client.conf_get('/status/applications/stopping/requests/processing')
            == 1
        )
        assert b'HTTP/1.1 200' in client.recvall(sock)
    finally:
        sock.close()

    wait_processes('stopping')
    wait_requests('stopping', total=1, completed=1)
    assert client.get()['status'] == 200
    wait_processes('stopping', running=1, idle=1)


def test_status_applications_unexpected_exit(skip_alert):
    client.load('listen', name='stopping')
    pid = int(client.get()['body'].split(':')[1])
    wait_processes('stopping', running=1, idle=1)

    skip_alert(fr'app process {pid} exited on signal 9')
    os.kill(pid, signal.SIGKILL)
    wait_processes('stopping')

    assert client.get()['status'] == 200
    wait_processes('stopping', running=1, idle=1)


def test_status_application_pass():
    assert 'success' in client.conf(
        {
            "applications": {
                "empty": app_default(),
            },
        },
    )

    Status.init()

    assert client.get()['status'] == 200
    assert Status.get('/requests/total') == 1, 'application pass'
