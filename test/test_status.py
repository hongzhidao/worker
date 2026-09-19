import os
import signal
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
    assert set(client.conf_get('/status')) == {'requests', 'applications'}
    assert 'error' in client.conf_get('/status/connections')

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
    assert Status.get('/requests/total') == 3, '4xx'

    assert client.get(port=8082)['status'] == 503
    assert Status.get('/requests/total') == 4, '5xx'

    client.http(
        b"""GET / HTTP/1.1
Host: localhost

GET / HTTP/1.1
Host: localhost
Connection: close

""",
        raw=True,
    )
    assert Status.get('/requests/total') == 6, 'pipeline'

    sock = client.get(port=8081, no_recv=True)

    time.sleep(1)

    assert Status.get('/requests/total') == 7, 'no receive'

    sock.close()

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

    def check_application(name, running, starting, idle, active):
        expected = {
            'processes': {
                'running': running,
                'starting': starting,
                'idle': idle,
                'stopping': 0,
            },
            'requests': {'active': active},
        }

        for _ in range(100):
            status = Status.get(f'/applications/{name}')
            if status == expected:
                return
            time.sleep(0.05)

        assert status == expected

    client.load('delayed')
    wait_processes('delayed')
    Status.init()

    check_applications(['delayed'])
    check_application('delayed', 0, 0, 0, 0)

    # idle

    assert client.get()['status'] == 200
    check_application('delayed', 1, 0, 1, 0)

    assert 'success' in client.conf('4', 'applications/delayed/processes')
    wait_processes('delayed', running=4, idle=4)
    check_application('delayed', 4, 0, 4, 0)

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
    check_application('delayed', 4, 0, 3, 1)
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
    check_application('restart', 0, 0, 0, 0)
    check_application('delayed', 0, 0, 0, 0)

    client.get(read_timeout=1)

    check_application('restart', 0, 1, 0, 1)
    check_application('delayed', 0, 0, 0, 0)
    wait_processes('restart', running=1, idle=1)


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
            client.conf_get('/status/applications/stopping/requests/active')
            == 1
        )
        assert b'HTTP/1.1 200' in client.recvall(sock)
    finally:
        sock.close()

    wait_processes('stopping')
    assert client.conf_get('/status/applications/stopping/requests/active') == 0
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
