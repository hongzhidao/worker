import shutil
from urllib.parse import quote

from worker.applications.proto import ApplicationProto
from worker.option import option
from worker.utils import public_dir


class ApplicationNode(ApplicationProto):
    def __init__(self, application_type='node', es_modules=False):
        self.application_type = application_type
        self.es_modules = es_modules

    def prepare_env(self, script):
        # copy application
        shutil.copytree(
            option.test_dir + '/node/' + script, option.temp_dir + '/node'
        )

        # copy modules
        shutil.copytree(
            option.current_dir + '/node/node_modules',
            option.temp_dir + '/node/node_modules',
        )

        public_dir(option.temp_dir + '/node')

    def load(self, script, name='app.js', **kwargs):
        self.prepare_env(script)

        if self.es_modules:
            arguments = [
                "node",
                "--loader",
                "worker-http/loader.mjs",
                "--require",
                "worker-http/loader",
                name,
            ]

        else:
            arguments = ["node", "--require", "worker-http/loader", name]

        self._load_conf(
            {
                "listeners": {
                    "*:8080": {"pass": "applications/" + quote(script, '')}
                },
                "applications": {
                    script: {
                        "type": "external",
                        "processes": {"spare": 0},
                        "working_directory": option.temp_dir + '/node',
                        "executable": '/usr/bin/env',
                        "arguments": arguments,
                    }
                },
            },
            **kwargs
        )
