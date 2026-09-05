from worker.applications.lang.php import ApplicationPHP

prerequisites = {'modules': {'php': 'any'}, 'features': {'isolation': True}}

client = ApplicationPHP()


def test_php_isolation_rootfs(is_su, require, temp_dir):
    isolation = {'rootfs': temp_dir}

    if not is_su:
        require(
            {
                'features': {
                    'isolation': [
                        'unprivileged_userns_clone',
                        'user',
                        'mnt',
                        'pid',
                    ]
                }
            }
        )

        isolation['namespaces'] = {
            'mount': True,
            'credential': True,
            'pid': True,
        }

    client.load('empty', isolation=isolation)

    assert 'success' in client.conf(
        '"/app/php/empty"', 'applications/empty/root'
    )
    assert 'success' in client.conf(
        '"/app/php/empty"', 'applications/empty/working_directory'
    )

    assert client.get()['status'] == 200, 'empty rootfs'


def test_php_isolation_rootfs_extensions(is_su, require, temp_dir):
    isolation = {'rootfs': temp_dir}

    if not is_su:
        require(
            {
                'features': {
                    'isolation': [
                        'unprivileged_userns_clone',
                        'user',
                        'mnt',
                        'pid',
                    ]
                }
            }
        )

        isolation['namespaces'] = {
            'mount': True,
            'credential': True,
            'pid': True,
        }

    client.load('list-extensions', isolation=isolation)

    assert 'success' in client.conf(
        '"/app/php/list-extensions"', 'applications/list-extensions/root'
    )

    assert 'success' in client.conf(
        {'file': '/php/list-extensions/php.ini'},
        'applications/list-extensions/options',
    )

    assert 'success' in client.conf(
        '"/app/php/list-extensions"',
        'applications/list-extensions/working_directory',
    )

    extensions = client.getjson()['body']

    assert 'json' in extensions, 'json in extensions list'
    assert 'worker' in extensions, 'worker in extensions list'
