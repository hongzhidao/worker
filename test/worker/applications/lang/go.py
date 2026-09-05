import os
import subprocess

from worker.applications.proto import ApplicationProto
from worker.option import option


class ApplicationGo(ApplicationProto):
    @staticmethod
    def prepare_env(script, name='app', static=False):
        try:
            subprocess.check_output(['which', 'go'])
        except subprocess.CalledProcessError:
            return None

        if not os.path.exists(option.temp_dir + '/go'):
            os.mkdir(option.temp_dir + '/go')

        env = os.environ.copy()
        env['GOPATH'] = option.current_dir + '/build/go'
        env['GOCACHE'] = option.cache_dir + '/go'
        env['GO111MODULE'] = 'auto'

        if static:
            args = [
                'go',
                'build',
                '-tags',
                'netgo',
                '-ldflags',
                '-extldflags "-static"',
                '-o',
                option.temp_dir + '/go/' + name,
                option.test_dir + '/go/' + script + '/' + name + '.go',
            ]
        else:
            args = [
                'go',
                'build',
                '-o',
                option.temp_dir + '/go/' + name,
                option.test_dir + '/go/' + script + '/' + name + '.go',
            ]

        if option.detailed:
            print("\n$ GOPATH=" + env['GOPATH'] + " " + " ".join(args))

        try:
            output = subprocess.check_output(
                args, env=env, stderr=subprocess.STDOUT
            )

        except KeyboardInterrupt:
            raise

        except subprocess.CalledProcessError:
            return None

        return output

    def load(self, script, name='app', **kwargs):
        static_build = False

        wdir = option.test_dir + "/go/" + script
        executable = option.temp_dir + "/go/" + name

        if 'isolation' in kwargs and 'rootfs' in kwargs['isolation']:
            wdir = "/go/"
            executable = "/go/" + name
            static_build = True

        ApplicationGo.prepare_env(script, name, static=static_build)

        conf = {
            "applications": {
                script: {
                    "listen": kwargs.pop('listen', '*:8080'),
                    "type": "external",
                    "processes": {"spare": 0},
                    "working_directory": wdir,
                    "executable": executable,
                },
            },
        }

        self._load_conf(conf, **kwargs)
