import pytest
from worker.applications.proto import ApplicationProto

prerequisites = {'modules': {'njs': 'any'}}


client = ApplicationProto()


@pytest.fixture(autouse=True)
def setup_method_fixture():
    assert 'success' in client.conf(
        {
            "listeners": {"*:8080": {"pass": "routes/entry"}},
            "routes": {"entry": [{"action": {"return": 200}}]},
        }
    )

def create_routes(*names):
    routes = client.conf_get('routes')
    routes.update({name: [{"action": {"return": 200}}] for name in names})
    assert 'success' in client.conf(routes, 'routes')

def set_pass(target):
    assert 'success' in client.conf({"pass": target}, 'routes/entry/0/action')

def check_expression(expression, url='/'):
    set_pass('`routes' + expression + '`')
    assert client.get(url=url)['status'] == 200

def test_njs_template_string():
    create_routes('str', '`string`', '`backtick', 'l1\nl2')

    check_expression('/str')
    check_expression(r'/\`backtick')
    check_expression('/l1\\nl2')

    set_pass('routes/`string`')
    assert client.get()['status'] == 200

def test_njs_template_expression():
    create_routes('str', 'localhost')

    check_expression('${uri}', '/str')
    check_expression('${uri}${host}')
    check_expression('${uri + host}')
    check_expression('${uri + `${host}`}')

def test_njs_iteration():
    create_routes('Connection,Host', 'close,localhost')

    check_expression('/${Object.keys(headers).sort().join()}')
    check_expression('/${Object.values(headers).sort().join()}')

def test_njs_variables():
    create_routes('str', 'localhost', '127.0.0.1')

    check_expression('/${host}')
    check_expression('/${remoteAddr}')
    check_expression('/${headers.Host}')

    set_pass('`routes/${cookies.foo}`')
    assert (
        client.get(headers={'Cookie': 'foo=str', 'Connection': 'close'})[
            'status'
        ]
        == 200
    ), 'cookies'

    set_pass('`routes/${args.foo}`')
    assert client.get(url='/?foo=str')['status'] == 200, 'args'

    check_expression('/${vars.header_host}')

    set_pass('`routes/${vars["arg_foo"]}`')
    assert client.get(url='/?foo=str')['status'] == 200, 'vars'

    set_pass('`routes/${vars.non_exist}`')
    assert client.get()['status'] == 404, 'undefined'

    create_routes('undefined')
    assert client.get()['status'] == 200, 'undefined 2'


def test_njs_uri_variables():
    create_routes('str', 'other')

    for expression in ('${uri}', '${vars.uri}'):
        check_expression(expression, '/str')
        check_expression(expression, '/other')


def test_njs_variables_cacheable_access_log(findall, temp_dir):
    assert 'success' in client.conf({"return": 200}, 'routes/entry/0/action')

    assert 'success' in client.conf(
        {
            'path': f'{temp_dir}/access.log',
            'format': '`${vars.host}, ${vars.status}\n`',
        },
        'access_log'
    ), 'access_log configure'

    reqs = 50
    for _ in range(reqs):
        client.get()

    assert len(findall(r'localhost, 200', 'access.log')) == reqs


def test_njs_invalid(skip_alert):
    skip_alert(r'js exception:')

    def check_invalid(template):
        assert 'error' in client.conf({"pass": template}, 'routes/entry/0/action')

    check_invalid('`a')
    check_invalid('`a``')
    check_invalid('`a`/')
    check_invalid('`${vars.}`')

    def check_invalid_resolve(template):
        set_pass(template)
        assert client.get()['status'] == 500

    check_invalid_resolve('`${a}`')
    check_invalid_resolve('`${uri.a.a}`')
    check_invalid_resolve('`${vars.a.a}`')
