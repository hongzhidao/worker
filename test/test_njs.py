import pytest
from worker.applications.lang.python import ApplicationPython
from worker.applications.proto import ApplicationProto

prerequisites = {'modules': {'njs': 'any', 'python': 'any'}}


client = ApplicationProto()


@pytest.fixture(autouse=True)
def setup_method_fixture():
    ApplicationPython().load('empty')

def create_applications(*names):
    applications = client.conf_get('applications')
    applications.update({name: applications['empty'] for name in names})
    assert 'success' in client.conf(applications, 'applications')

def set_pass(target):
    assert 'success' in client.conf({"pass": target}, 'listeners/*:8080')

def check_expression(expression, url='/'):
    set_pass('`applications' + expression + '`')
    assert client.get(url=url)['status'] == 200

def test_njs_template_string():
    create_applications('str', '`string`', '`backtick', 'l1\nl2')

    check_expression('/str')
    check_expression(r'/\`backtick')
    check_expression('/l1\\nl2')

    set_pass('applications/`string`')
    assert client.get()['status'] == 200

def test_njs_template_expression():
    create_applications('str', 'localhost')

    check_expression('${uri}', '/str')
    check_expression('${uri}${host}')
    check_expression('${uri + host}')
    check_expression('${uri + `${host}`}')

def test_njs_iteration():
    create_applications('Connection,Host', 'close,localhost')

    check_expression('/${Object.keys(headers).sort().join()}')
    check_expression('/${Object.values(headers).sort().join()}')

def test_njs_variables():
    create_applications('str', 'localhost', '127.0.0.1')

    check_expression('/${host}')
    check_expression('/${remoteAddr}')
    check_expression('/${headers.Host}')

    set_pass('`applications/${cookies.foo}`')
    assert (
        client.get(headers={'Cookie': 'foo=str', 'Connection': 'close'})[
            'status'
        ]
        == 200
    ), 'cookies'

    set_pass('`applications/${args.foo}`')
    assert client.get(url='/?foo=str')['status'] == 200, 'args'

    check_expression('/${vars.header_host}')

    set_pass('`applications/${vars["arg_foo"]}`')
    assert client.get(url='/?foo=str')['status'] == 200, 'vars'

    set_pass('`applications/${vars.non_exist}`')
    assert client.get()['status'] == 404, 'undefined'

    create_applications('undefined')
    assert client.get()['status'] == 200, 'undefined 2'


def test_njs_uri_variables():
    create_applications('str', 'other')

    for expression in ('${uri}', '${vars.uri}'):
        check_expression(expression, '/str')
        check_expression(expression, '/other')


def test_njs_invalid(skip_alert):
    skip_alert(r'js exception:')

    def check_invalid(template):
        assert 'error' in client.conf({"pass": template}, 'listeners/*:8080')

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
