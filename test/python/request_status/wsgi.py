import os
import time


def application(environ, start_response):
    body = str(os.getpid()).encode()

    if environ.get('HTTP_X_WAIT'):
        while not os.path.exists(os.environ['RELEASE_PATH']):
            time.sleep(0.01)

    time.sleep(float(environ.get('HTTP_X_DELAY', 0)))
    streaming = environ.get('HTTP_X_WAIT_BODY')
    write = start_response(
        environ.get('HTTP_X_STATUS', '200'),
        [] if streaming else [('Content-Length', str(len(body)))],
    )
    if streaming:
        write(body[:1])
        while not os.path.exists(os.environ['RELEASE_PATH']):
            time.sleep(0.01)
        body = body[1:]
    return [body]
