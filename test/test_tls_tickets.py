import socket

import pytest

pytest.importorskip('OpenSSL.SSL')
from OpenSSL.SSL import (
    TLSv1_2_METHOD,
    Context,
    Connection,
    _lib,
)
from worker.applications.tls import ApplicationTLS

prerequisites = {'modules': {'openssl': 'any'}}


client = ApplicationTLS()


ticket = 'U1oDTh11mMxODuw12gS0EXX1E/PkZG13cJNQ6m5+6BGlfPTjNlIEw7PSVU3X1gTE'
ticket2 = (
    '5AV0DSYIYbZWZQB7fCnTHZmMxtotb/aXjam+n2XS79lTvX3Tq9xGqpC8XKNEF2lt'
)
ticket80 = '6Pfil8lv/k8zf8MndPpfXaO5EAV6dhME6zs6CfUyq2yziynQwSywtKQMqHGnJ2HR\
49TZXi/Y4/8RSIO7QPsU51/HLR1gWIMhVM2m9yh93Bw='

@pytest.fixture(autouse=True)
def setup_method_fixture():
    client.certificate()

    listener_conf = {
        "pass": "routes",
        "tls": {
            "certificate": "default",
            "session": {"cache_size": 0, "tickets": True},
        },
    }

    assert 'success' in client.conf(
        {
            "listeners": {
                "*:8080": listener_conf,
                "*:8081": listener_conf,
                "*:8082": listener_conf,
            },
            "routes": [{"action": {"return": 200}}],
            "applications": {},
        }
    ), 'load application configuration'

def set_tickets(tickets=True, port=8080):
    assert 'success' in client.conf(
        {"cache_size": 0, "tickets": tickets},
        'listeners/*:' + str(port) + '/tls/session',
    )

def connect(ctx=None, session=None, port=8080):
    sock = socket.create_connection(('127.0.0.1', port))

    if ctx is None:
        ctx = Context(TLSv1_2_METHOD)

    client = Connection(ctx, sock)
    client.set_connect_state()

    if session is not None:
        client.set_session(session)

    client.do_handshake()
    client.shutdown()

    return (
        client.get_session(),
        ctx,
        _lib.SSL_session_reused(client._ssl),
    )

def has_ticket(sess):
    return _lib.SSL_SESSION_has_ticket(sess._session)

@pytest.mark.skipif(
    not hasattr(_lib, 'SSL_SESSION_has_ticket'),
    reason='ticket check is not supported',
)
def test_tls_ticket():
    sess, ctx, reused = connect()
    assert has_ticket(sess), 'tickets True'
    assert not reused, 'tickets True not reused'

    sess, ctx, reused = connect(ctx, sess)
    assert has_ticket(sess), 'tickets True reconnect'
    assert reused, 'tickets True reused'

    set_tickets(tickets=False)

    sess, _, _ = connect()
    assert not has_ticket(sess), 'tickets False'

    assert 'success' in client.conf_delete(
        'listeners/*:8080/tls/session/tickets'
    ), 'tickets default configure'

    sess, _, _ = connect()
    assert not has_ticket(sess), 'tickets default (false)'

@pytest.mark.skipif(
    not hasattr(_lib, 'SSL_SESSION_has_ticket'),
    reason='ticket check is not supported',
)
def test_tls_ticket_string():
    set_tickets(ticket)
    sess, ctx, _ = connect()
    assert has_ticket(sess), 'tickets string'

    sess2, _, reused = connect(ctx, sess)
    assert has_ticket(sess2), 'tickets string reconnect'
    assert reused, 'tickets string reused'

    sess2, _, reused = connect(ctx, sess, port=8081)
    assert has_ticket(sess2), 'connect True'
    assert not reused, 'connect True not reused'

    set_tickets(ticket2, port=8081)

    sess2, _, reused = connect(ctx, sess, port=8081)
    assert has_ticket(sess2), 'wrong ticket'
    assert not reused, 'wrong ticket not reused'

    set_tickets(ticket80)

    sess, ctx, _ = connect()
    assert has_ticket(sess), 'tickets string 80'

    sess2, _, reused = connect(ctx, sess)
    assert has_ticket(sess2), 'tickets string 80 reconnect'
    assert reused, 'tickets string 80 reused'

    sess2, _, reused = connect(ctx, sess, port=8081)
    assert has_ticket(sess2), 'wrong ticket 80'
    assert not reused, 'wrong ticket 80 not reused'

@pytest.mark.skipif(
    not hasattr(_lib, 'SSL_SESSION_has_ticket'),
    reason='ticket check is not supported',
)
def test_tls_ticket_array():
    set_tickets([])

    sess, ctx, _ = connect()
    assert not has_ticket(sess), 'tickets array empty'

    set_tickets([ticket, ticket2])
    set_tickets(ticket, port=8081)
    set_tickets(ticket2, port=8082)

    sess, ctx, _ = connect()
    _, _, reused = connect(ctx, sess, port=8081)
    assert not reused, 'not last ticket'
    _, _, reused = connect(ctx, sess, port=8082)
    assert reused, 'last ticket'

    sess, ctx, _ = connect(port=8081)
    _, _, reused = connect(ctx, sess)
    assert reused, 'first ticket'

    sess, ctx, _ = connect(port=8082)
    _, _, reused = connect(ctx, sess)
    assert reused, 'second ticket'

    assert 'success' in client.conf_delete(
        'listeners/*:8080/tls/session/tickets/0'
    ), 'removed first ticket'
    assert 'success' in client.conf_post(
        '"' + ticket + '"', 'listeners/*:8080/tls/session/tickets'
    ), 'add new ticket to the end of array'

    sess, ctx, _ = connect()
    _, _, reused = connect(ctx, sess, port=8082)
    assert not reused, 'not last ticket 2'
    _, _, reused = connect(ctx, sess, port=8081)
    assert reused, 'last ticket 2'

def test_tls_ticket_invalid():
    def check_tickets(tickets):
        assert 'error' in client.conf(
            {"tickets": tickets}, 'listeners/*:8080/tls/session',
        )

    check_tickets({})
    check_tickets('!?&^' * 16)
    check_tickets(ticket[:-2] + '!' + ticket[3:])
    check_tickets(ticket[:-1])
    check_tickets(ticket + 'b')
    check_tickets(ticket + 'blah')
    check_tickets([True, ticket, ticket2])
    check_tickets([ticket, 'blah', ticket2])
    check_tickets([ticket, ticket2, []])
