import os
import ssl
import subprocess

from worker.applications.proto import ApplicationProto
from worker.option import option


class ApplicationTLS(ApplicationProto):
    def __init__(self):
        self._default_context = ssl.create_default_context()
        self._default_context.check_hostname = False
        self._default_context.verify_mode = ssl.CERT_NONE

    def certificate(self, name='default', load=True):
        self.openssl_conf()

        subprocess.check_output(
            [
                'openssl',
                'req',
                '-x509',
                '-new',
                '-subj',
                '/CN=' + name + '/',
                '-config',
                option.temp_dir + '/openssl.conf',
                '-out',
                option.temp_dir + '/' + name + '.crt',
                '-keyout',
                option.temp_dir + '/' + name + '.key',
            ],
            stderr=subprocess.STDOUT,
        )

        if load:
            self.certificate_load(name)

    def certificate_load(self, crt, key=None):
        if key is None:
            key = crt

        key_path = option.temp_dir + '/' + key + '.key'
        crt_path = option.temp_dir + '/' + crt + '.crt'

        with open(key_path, 'rb') as k, open(crt_path, 'rb') as c:
            return self.conf(k.read() + c.read(), '/certificates/' + crt)

    def get_ssl(self, **kwargs):
        context = kwargs.get('context', self._default_context)
        return self.get(wrapper=context.wrap_socket, **kwargs)

    def post_ssl(self, **kwargs):
        context = kwargs.get('context', self._default_context)
        return self.post(wrapper=context.wrap_socket, **kwargs)

    def get_server_certificate(self, addr=('127.0.0.1', 8080)):

        ssl_list = dir(ssl)

        if 'PROTOCOL_TLS' in ssl_list:
            ssl_version = ssl.PROTOCOL_TLS

        elif 'PROTOCOL_TLSv1_2' in ssl_list:
            ssl_version = ssl.PROTOCOL_TLSv1_2

        else:
            ssl_version = ssl.PROTOCOL_TLSv1_1

        return ssl.get_server_certificate(addr, ssl_version=ssl_version)

    def openssl_conf(self, rewrite=False, alt_names=None):
        alt_names = alt_names or []

        conf_path = option.temp_dir + '/openssl.conf'

        if not rewrite and os.path.exists(conf_path):
            return

        # Generates alt_names section with dns names
        a_names = "[alt_names]\n"
        for i, k in enumerate(alt_names, 1):
            k = k.split('|')

            if k[0] == 'IP':
                a_names += "IP.%d = %s\n" % (i, k[1])
            else:
                a_names += "DNS.%d = %s\n" % (i, k[0])

        # Generates section for sign request extension
        a_sec = """req_extensions = myca_req_extensions

[ myca_req_extensions ]
subjectAltName = @alt_names

{a_names}""".format(
            a_names=a_names
        )

        with open(conf_path, 'w') as f:
            f.write(
                """[ req ]
default_bits = 2048
encrypt_key = no
distinguished_name = req_distinguished_name
x509_extensions = myca_extensions

{a_sec}
[ req_distinguished_name ]

[ myca_extensions ]
basicConstraints = critical,CA:TRUE""".format(
                    a_sec=a_sec if alt_names else ""
                )
            )

    def load(self, script, name=None):
        if name is None:
            name = script

        script_path = option.test_dir + '/python/' + script

        self._load_conf(
            {
                "listeners": {"*:8080": {"pass": "applications/" + name}},
                "applications": {
                    name: {
                        "type": "python",
                        "processes": {"spare": 0},
                        "path": script_path,
                        "working_directory": script_path,
                        "module": "wsgi",
                    }
                },
            }
        )
