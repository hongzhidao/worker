import os


def application(environ, start_response):
    body = (os.environ.get('APP_NAME', 'app') + ':' + str(os.getpid())).encode()
    start_response('200 OK', [('Content-Length', str(len(body)))])
    return [body]


def alternate(environ, start_response):
    body = ('alternate:' + str(os.getpid())).encode()
    start_response('200 OK', [('Content-Length', str(len(body)))])
    return [body]
