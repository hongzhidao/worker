import json


def application(environ, start_response):
    body = json.dumps({'worker': 'python', 'path': environ['PATH_INFO']}).encode()
    start_response('200 OK', [('Content-Type', 'application/json'), ('Content-Length', str(len(body)))])
    return [body]
