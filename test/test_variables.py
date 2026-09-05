import pytest
from worker.applications.lang.python import ApplicationPython

prerequisites = {'modules': {'python': 'any'}}

client = ApplicationPython()


@pytest.fixture(autouse=True)
def setup_method_fixture():
    client.load('response')


def test_variables_empty():
    def update_pass(prefix):
        assert 'success' in client.conf(
            {
                "listeners": {
                    "*:8080": {"pass": prefix + "/$method"},
                },
            },
        ), 'variables empty'

    update_pass("routes")
    assert client.get(url='/1')['status'] == 404

    update_pass("upstreams")
    assert client.get(url='/2')['status'] == 404

    update_pass("applications")
    assert client.get(url='/3')['status'] == 404


def test_variables_invalid():
    def check_variables(expression):
        assert 'error' in client.conf(
            {'pass': expression}, 'listeners/*:8080'
        ), 'invalid pass variable'

    check_variables("$")
    check_variables("${")
    check_variables("${}")
    check_variables("$ur")
    check_variables("$uri$$host")
    check_variables("$uriblah")
    check_variables("${uri")
    check_variables("${{uri}")
    check_variables("$ar")
    check_variables("$arg")
    check_variables("$arg_")
    check_variables("$cookie")
    check_variables("$cookie_")
    check_variables("$header")
    check_variables("$header_")
