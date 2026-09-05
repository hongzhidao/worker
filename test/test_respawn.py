import re
import subprocess
import time

import pytest
from worker.applications.lang.python import ApplicationPython

prerequisites = {'modules': {'python': 'any'}}


client = ApplicationPython()


PATTERN_ROUTER = 'worker: router'
PATTERN_CONTROLLER = 'worker: controller'

@pytest.fixture(autouse=True)
def setup_method_fixture(temp_dir):
    client.app_name = f'app-{temp_dir.split("/")[-1]}'

    client.load('empty', client.app_name)

    assert 'success' in client.conf(
        '1', 'applications/' + client.app_name + '/processes'
    )

def pid_by_name(name, ppid):
    output = subprocess.check_output(['ps', 'ax', '-O', 'ppid']).decode()
    m = re.search(r'\s*(\d+)\s*' + str(ppid) + r'.*' + name, output)
    return None if m is None else m.group(1)

def kill_pids(*pids):
    subprocess.call(['kill', '-9'] + list(pids))

def wait_for_process(process, worker_pid):
    for _ in range(50):
        found = pid_by_name(process, worker_pid)

        if found is not None:
            break

        time.sleep(0.1)

    return found

def find_proc(name, ppid, ps_output):
    return re.findall(str(ppid) + r'.*' + name, ps_output)

def smoke_test(worker_pid):
    for _ in range(10):
        r = client.conf('1', 'applications/' + client.app_name + '/processes')

        if 'success' in r:
            break

        time.sleep(0.1)

    assert 'success' in r
    assert client.get()['status'] == 200

    # Check if the only one router, controller,
    # and application processes running.

    out = subprocess.check_output(['ps', 'ax', '-O', 'ppid']).decode()
    assert len(find_proc(PATTERN_ROUTER, worker_pid, out)) == 1
    assert len(find_proc(PATTERN_CONTROLLER, worker_pid, out)) == 1
    assert len(find_proc(client.app_name, worker_pid, out)) == 1

def test_respawn_router(skip_alert, worker_pid, skip_fds_check):
    skip_fds_check(router=True)
    pid = pid_by_name(PATTERN_ROUTER, worker_pid)

    kill_pids(pid)
    skip_alert(r'process %s exited on signal 9' % pid)

    assert wait_for_process(PATTERN_ROUTER, worker_pid) is not None

    smoke_test(worker_pid)

def test_respawn_controller(skip_alert, worker_pid, skip_fds_check):
    skip_fds_check(controller=True)
    pid = pid_by_name(PATTERN_CONTROLLER, worker_pid)

    kill_pids(pid)
    skip_alert(r'process %s exited on signal 9' % pid)

    assert (
        wait_for_process(PATTERN_CONTROLLER, worker_pid)
        is not None
    )

    assert client.get()['status'] == 200

    smoke_test(worker_pid)

def test_respawn_application(skip_alert, worker_pid):
    pid = pid_by_name(client.app_name, worker_pid)

    kill_pids(pid)
    skip_alert(r'process %s exited on signal 9' % pid)

    assert wait_for_process(client.app_name, worker_pid) is not None

    smoke_test(worker_pid)
