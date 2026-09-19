from worker.control import Control


class Status:
    _status = None
    control = Control()

    def _check_zeros():
        assert Status.control.conf_get('/status') == {
            'processes': {
                'running': 0, 'idle': 0, 'starting': 0, 'stopping': 0,
            },
            'requests': {
                'total': 0, 'waiting': 0, 'processing': 0, 'completed': 0,
            },
            'responses': {'1xx': 0, '2xx': 0, '3xx': 0, '4xx': 0, '5xx': 0},
            'latency': {'p50': None, 'p95': None, 'p99': None},
            'applications': {},
        }

    def init(status=None):
        Status._status = (
            status if status is not None else Status.control.conf_get('/status')
        )

    def diff():
        def find_diffs(d1, d2):
            if isinstance(d1, dict) and isinstance(d2, dict):
                return {
                    k: find_diffs(d1.get(k, 0), d2.get(k, 0))
                    for k in d1
                    if k in d2
                }
            else:
                if d1 is None or d2 is None:
                    return d1
                return d1 - d2

        return find_diffs(Status.control.conf_get('/status'), Status._status)

    def get(path='/'):
        path = path.split('/')[1:]
        diff = Status.diff()

        for p in path:
            diff = diff[p]

        return diff
