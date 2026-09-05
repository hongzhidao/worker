def application(env, start_response):
    start_response(
        '200',
        [
            ('Content-Length', '0'),
            ('Remote-Addr', env.get('REMOTE_ADDR')),
            ('Url-Scheme', env.get('wsgi.url_scheme')),
            ('Request-Forwarded-For', env.get('HTTP_X_FORWARDED_FOR', '')),
            ('Request-Forwarded-Proto', env.get('HTTP_X_FORWARDED_PROTO', '')),
        ],
    )
    return []
