import ssl
import subprocess

import pytest
from worker.applications.tls import ApplicationTLS
from worker.option import option

prerequisites = {'modules': {'openssl': 'any'}}


client = ApplicationTLS()


@pytest.fixture(autouse=True)
def setup_method_fixture():
    client._load_conf(
        {
            "listeners": {"*:8080": {"pass": "routes"}},
            "routes": [{"action": {"return": 200}}],
            "applications": {},
        }
    )

def add_tls(cert='default'):
    assert 'success' in client.conf(
        {"pass": "routes", "tls": {"certificate": cert}},
        'listeners/*:8080',
    )

def remove_tls():
    assert 'success' in client.conf({"pass": "routes"}, 'listeners/*:8080')

def generate_ca_conf():
    with open(option.temp_dir + '/ca.conf', 'w') as f:
        f.write(
            """[ ca ]
default_ca = myca

[ myca ]
new_certs_dir = %(dir)s
database = %(database)s
default_md = sha256
policy = myca_policy
serial = %(certserial)s
default_days = 1
x509_extensions = myca_extensions
copy_extensions = copy

[ myca_policy ]
commonName = optional

[ myca_extensions ]
basicConstraints = critical,CA:TRUE"""
            % {
                'dir': option.temp_dir,
                'database': option.temp_dir + '/certindex',
                'certserial': option.temp_dir + '/certserial',
            }
        )

    with open(option.temp_dir + '/certserial', 'w') as f:
        f.write('1000')

    with open(option.temp_dir + '/certindex', 'w') as f:
        f.write('')

def config_bundles(bundles):
    client.certificate('root', False)

    for b in bundles:
        client.openssl_conf(rewrite=True, alt_names=bundles[b]['alt_names'])
        subj = (
            '/CN={}/'.format(bundles[b]['subj'])
            if 'subj' in bundles[b]
            else '/'
        )

        subprocess.check_output(
            [
                'openssl',
                'req',
                '-new',
                '-subj',
                subj,
                '-config',
                option.temp_dir + '/openssl.conf',
                '-out',
                option.temp_dir + '/{}.csr'.format(b),
                '-keyout',
                option.temp_dir + '/{}.key'.format(b),
            ],
            stderr=subprocess.STDOUT,
        )

    generate_ca_conf()

    for b in bundles:
        subj = (
            '/CN={}/'.format(bundles[b]['subj'])
            if 'subj' in bundles[b]
            else '/'
        )

        subprocess.check_output(
            [
                'openssl',
                'ca',
                '-batch',
                '-subj',
                subj,
                '-config',
                option.temp_dir + '/ca.conf',
                '-keyfile',
                option.temp_dir + '/root.key',
                '-cert',
                option.temp_dir + '/root.crt',
                '-in',
                option.temp_dir + '/{}.csr'.format(b),
                '-out',
                option.temp_dir + '/{}.crt'.format(b),
            ],
            stderr=subprocess.STDOUT,
        )

    load_certs(bundles)

    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_REQUIRED
    context.verify_flags &= ~ssl.VERIFY_X509_STRICT
    context.load_verify_locations(option.temp_dir + '/root.crt')

    return context

def load_certs(bundles):
    for bname, bvalue in bundles.items():
        assert 'success' in client.certificate_load(
            bname, bname
        ), 'certificate {} upload'.format(bvalue['subj'])

def check_cert(host, expect, context):
    resp, sock = client.get_ssl(
        headers={
            'Host': host,
            'Content-Length': '0',
            'Connection': 'close',
        },
        start=True,
        context=context,
    )

    assert resp['status'] == 200
    assert sock.getpeercert()['subject'][0][0][1] == expect

def test_tls_sni():
    bundles = {
        "default": {"subj": "default", "alt_names": ["default"]},
        "localhost.com": {
            "subj": "localhost.com",
            "alt_names": ["alt1.localhost.com"],
        },
        "example.com": {
            "subj": "example.com",
            "alt_names": ["alt1.example.com", "alt2.example.com"],
        },
    }
    context = config_bundles(bundles)
    add_tls(["default", "localhost.com", "example.com"])

    check_cert('alt1.localhost.com', bundles['localhost.com']['subj'], context)
    check_cert('alt2.example.com', bundles['example.com']['subj'], context)
    check_cert('blah', bundles['default']['subj'], context)

def test_tls_sni_no_hostname():
    bundles = {
        "localhost.com": {"subj": "localhost.com", "alt_names": []},
        "example.com": {
            "subj": "example.com",
            "alt_names": ["example.com"],
        },
    }
    context = config_bundles(bundles)
    add_tls(["localhost.com", "example.com"])

    resp, sock = client.get_ssl(
        headers={'Content-Length': '0', 'Connection': 'close'},
        start=True,
        context=context,
    )
    assert resp['status'] == 200
    assert (
        sock.getpeercert()['subject'][0][0][1]
        == bundles['localhost.com']['subj']
    )

def test_tls_sni_upper_case():
    bundles = {
        "localhost.com": {"subj": "LOCALHOST.COM", "alt_names": []},
        "example.com": {
            "subj": "example.com",
            "alt_names": ["ALT1.EXAMPLE.COM", "*.ALT2.EXAMPLE.COM"],
        },
    }
    context = config_bundles(bundles)
    add_tls(["localhost.com", "example.com"])

    check_cert('localhost.com', bundles['localhost.com']['subj'], context)
    check_cert('LOCALHOST.COM', bundles['localhost.com']['subj'], context)
    check_cert('EXAMPLE.COM', bundles['localhost.com']['subj'], context)
    check_cert('ALT1.EXAMPLE.COM', bundles['example.com']['subj'], context)
    check_cert('WWW.ALT2.EXAMPLE.COM', bundles['example.com']['subj'], context)

def test_tls_sni_only_bundle():
    bundles = {
        "localhost.com": {
            "subj": "localhost.com",
            "alt_names": ["alt1.localhost.com", "alt2.localhost.com"],
        }
    }
    context = config_bundles(bundles)
    add_tls(["localhost.com"])

    check_cert('domain.com', bundles['localhost.com']['subj'], context)
    check_cert('alt1.domain.com', bundles['localhost.com']['subj'], context)

def test_tls_sni_wildcard():
    bundles = {
        "localhost.com": {"subj": "localhost.com", "alt_names": []},
        "example.com": {
            "subj": "example.com",
            "alt_names": ["*.example.com", "*.alt.example.com"],
        },
    }
    context = config_bundles(bundles)
    add_tls(["localhost.com", "example.com"])

    check_cert('example.com', bundles['localhost.com']['subj'], context)
    check_cert('www.example.com', bundles['example.com']['subj'], context)
    check_cert('alt.example.com', bundles['example.com']['subj'], context)
    check_cert('www.alt.example.com', bundles['example.com']['subj'], context)
    check_cert('www.alt.example.ru', bundles['localhost.com']['subj'], context)

def test_tls_sni_duplicated_bundle():
    bundles = {
        "localhost.com": {
            "subj": "localhost.com",
            "alt_names": ["localhost.com", "alt2.localhost.com"],
        }
    }
    context = config_bundles(bundles)
    add_tls(["localhost.com", "localhost.com"])

    check_cert('localhost.com', bundles['localhost.com']['subj'], context)
    check_cert('alt2.localhost.com', bundles['localhost.com']['subj'], context)

def test_tls_sni_same_alt():
    bundles = {
        "localhost": {"subj": "subj1", "alt_names": ["same.altname.com"]},
        "example": {"subj": "subj2", "alt_names": ["same.altname.com"]},
    }
    context = config_bundles(bundles)
    add_tls(["localhost", "example"])

    check_cert('localhost', bundles['localhost']['subj'], context)
    check_cert('example', bundles['localhost']['subj'], context)

def test_tls_sni_empty_cn():
    bundles = {"localhost": {"alt_names": ["alt.localhost.com"]}}
    context = config_bundles(bundles)
    add_tls(["localhost"])

    resp, sock = client.get_ssl(
        headers={
            'Host': 'domain.com',
            'Content-Length': '0',
            'Connection': 'close',
        },
        start=True,
        context=context,
    )

    assert resp['status'] == 200
    assert (
        sock.getpeercert()['subjectAltName'][0][1] == 'alt.localhost.com'
    )

def test_tls_sni_invalid():
    _ = config_bundles({"localhost": {"subj": "subj1", "alt_names": ''}})
    add_tls(["localhost"])

    def check_certificate(cert):
        assert 'error' in client.conf(
            {"pass": "routes", "tls": {"certificate": cert}},
            'listeners/*:8080',
        )

    check_certificate('')
    check_certificate('blah')
    check_certificate([])
    check_certificate(['blah'])
    check_certificate(['localhost', 'blah'])
    check_certificate(['localhost', []])
