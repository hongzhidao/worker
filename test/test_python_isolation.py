import pytest
from worker.applications.lang.python import ApplicationPython
from worker.option import option
from worker.utils import findmnt
from worker.utils import waitformount
from worker.utils import waitforunmount

prerequisites = {'modules': {'python': 'any'}, 'features': {'isolation': True}}


client = ApplicationPython()


def test_python_isolation_rootfs(is_su, require, temp_dir):
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

    client.load('ns_inspect', isolation=isolation)

    assert not (
        client.getjson(url=f'/?path={temp_dir}')['body']['FileExists']
    ), 'temp_dir does not exists in rootfs'

    assert client.getjson(url='/?path=/proc/self')['body'][
        'FileExists'
    ], 'no /proc/self'

    assert not (
        client.getjson(url='/?path=/dev/pts')['body']['FileExists']
    ), 'no /dev/pts'

    assert not (
        client.getjson(url='/?path=/sys/kernel')['body']['FileExists']
    ), 'no /sys/kernel'

    ret = client.getjson(url='/?path=/app/python/ns_inspect')

    assert ret['body']['FileExists'], 'application exists in rootfs'

def test_python_isolation_rootfs_no_language_deps(require, temp_dir):
    require({'privileged_user': True})

    isolation = {'rootfs': temp_dir, 'automount': {'language_deps': False}}
    client.load('empty', isolation=isolation)

    python_path = temp_dir + '/usr'

    assert findmnt().find(python_path) == -1
    assert client.get()['status'] != 200, 'disabled language_deps'
    assert findmnt().find(python_path) == -1

    isolation['automount']['language_deps'] = True

    client.load('empty', isolation=isolation)

    assert findmnt().find(python_path) == -1
    assert client.get()['status'] == 200, 'enabled language_deps'
    assert waitformount(python_path), 'language_deps mount'

    client.conf({"applications": {}})

    assert waitforunmount(python_path), 'language_deps unmount'

def test_python_isolation_procfs(require, temp_dir):
    require({'privileged_user': True})

    isolation = {'rootfs': temp_dir, 'automount': {'procfs': False}}

    client.load('ns_inspect', isolation=isolation)

    assert not (
        client.getjson(url='/?path=/proc/self')['body']['FileExists']
    ), 'no /proc/self'

    isolation['automount']['procfs'] = True

    client.load('ns_inspect', isolation=isolation)

    assert client.getjson(url='/?path=/proc/self')['body'][
        'FileExists'
    ], '/proc/self'
