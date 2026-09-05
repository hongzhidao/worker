import shutil

from worker.applications.proto import ApplicationProto
from worker.option import option
from worker.utils import public_dir


class ApplicationRuby(ApplicationProto):
    def __init__(self, application_type='ruby'):
        self.application_type = application_type

    def prepare_env(self, script):
        shutil.copytree(
            option.test_dir + '/ruby/' + script,
            option.temp_dir + '/ruby/' + script,
        )

        public_dir(option.temp_dir + '/ruby/' + script)

    def load(self, script, name='config.ru', **kwargs):
        self.prepare_env(script)

        script_path = option.temp_dir + '/ruby/' + script

        app = {
            "type": self.get_application_type(),
            "processes": {"spare": 0},
            "working_directory": script_path,
            "script": script_path + '/' + name,
        }

        for key in [
            'hooks',
        ]:
            if key in kwargs:
                app[key] = kwargs[key]

        self._load_conf(
            {
                "listeners": {"*:8080": {"pass": "applications/" + script}},
                "applications": {script: app},
            },
            **kwargs
        )
