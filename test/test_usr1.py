import os
import signal

from worker.applications.lang.python import ApplicationPython
from worker.log import Log
from worker.utils import waitforfiles

prerequisites = {'modules': {'python': 'any'}}


client = ApplicationPython()


def test_usr1_unit_log(search_in_file, temp_dir, worker_pid, wait_for_record
):
    client.load('log_body')

    log_new = 'new.log'
    log_path = temp_dir + '/worker.log'
    log_path_new = temp_dir + '/' + log_new

    os.rename(log_path, log_path_new)

    Log.swap(log_new)

    try:
        body = 'body_for_a_log_new\n'
        assert client.post(body=body)['status'] == 200

        assert wait_for_record(body, log_new) is not None, 'rename new'
        assert not os.path.isfile(log_path), 'rename old'

        os.kill(worker_pid, signal.SIGUSR1)

        assert waitforfiles(log_path), 'reopen'

        body = 'body_for_a_log_unit\n'
        assert client.post(body=body)['status'] == 200

        assert wait_for_record(body) is not None, 'rename new'
        assert search_in_file(body, log_new) is None, 'rename new 2'

    finally:
        # merge two log files into worker.log to check alerts

        with open(log_path, 'r', errors='ignore') as worker_log:
            log = worker_log.read()

        with open(log_path, 'w') as worker_log, open(
            log_path_new, 'r', errors='ignore'
        ) as worker_log_new:
            worker_log.write(worker_log_new.read())
            worker_log.write(log)

        Log.swap(log_new)
