import json
import sys

root, app, listen, module, callable_name, protocol, extra_path = sys.argv[1:]
configuration = {
    'applications': {
        'app': {
            "listen": listen,
            'type': 'python',
            'home': root + '/runtime',
            'path': [app] + ([extra_path] if extra_path else []),
            'working_directory': app,
            'module': module,
            'callable': callable_name,
            'protocol': protocol,
            'processes': 1,
        },
    },
}
json.dump(configuration, sys.stdout)
