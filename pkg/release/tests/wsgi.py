import bz2
import hashlib
import json
import lzma
import sqlite3
import ssl
from zoneinfo import ZoneInfo

import smoke_dependency


def application(environ, start_response):
    ssl.create_default_context()
    database = sqlite3.connect(':memory:')
    assert database.execute('select 42').fetchone()[0] == 42
    database.close()
    assert str(ZoneInfo('UTC')) == 'UTC'
    body = environ['wsgi.input'].read(int(environ.get('CONTENT_LENGTH') or 0))
    assert bz2.decompress(bz2.compress(body)) == body
    assert lzma.decompress(lzma.compress(body)) == body
    result = json.dumps({
        'flavor': 'python', 'method': environ['REQUEST_METHOD'],
        'body': body.decode(), 'sha256': hashlib.sha256(body).hexdigest(),
        'dependency': smoke_dependency.VALUE,
    }).encode()
    start_response('200 OK', [('Content-Type', 'application/json'),
                             ('Content-Length', str(len(result)))])
    return [result]
