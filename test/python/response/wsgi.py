def application(environ, start_response):
    headers = [('Content-Length', '0')]
    start_response(environ.get('HTTP_X_STATUS', '200'), headers)
    return []
