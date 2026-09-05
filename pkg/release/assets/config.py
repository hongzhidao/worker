import json
import sys

if sys.argv[1] == '--config':
    root, filename = sys.argv[2:]
    with open(filename) as stream:
        configuration = json.load(stream)
    applications = configuration.get('applications', {}) if isinstance(configuration, dict) else {}
    for application in applications.values() if isinstance(applications, dict) else ():
        if not isinstance(application, dict) or not isinstance(application.get('type'), str):
            continue
        language = application['type'].split(' ', 1)[0]
        if language == 'python':
            application.setdefault('home', root + '/runtime')
        elif language == 'php' and isinstance(application.get('options', {}), dict):
            application.setdefault('options', {}).setdefault('file', root + '/runtime/php.ini')
    json.dump(configuration, sys.stdout)
    sys.exit(0)

php_listen = None
if sys.argv[1] == '--all':
    php_listen = sys.argv.pop(2)
    sys.argv.pop(1)

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
if php_listen is not None:
    configuration['applications']['python'] = configuration['applications'].pop('app')
    configuration['applications']['php'] = {
        'listen': php_listen, 'type': 'php', 'root': app,
        'working_directory': app, 'script': 'index.php', 'processes': 1,
        'options': {'file': root + '/runtime/php.ini'},
    }
json.dump(configuration, sys.stdout)
