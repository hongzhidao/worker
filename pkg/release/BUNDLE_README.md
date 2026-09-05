# Worker Runtime Bundle

This package includes Worker, its language modules, language runtimes, and shared
libraries. Linux with the CPU architecture and minimum glibc version in
`manifest.json` is required. No compiler or system Python/PHP is needed.
Alpine/musl is unsupported. Application dependencies remain separate.

## First Run

From the extracted directory:

```sh
./worker --state ./state
```

In another terminal in that directory:

```sh
curl http://127.0.0.1:8080/
./worker status --state ./state
./worker config --state ./state
```

The **all** bundle runs Python on 8080 and PHP on 8081 in the same Worker instance.
Its applications are named `python` and `php`; single-language bundles use `app`.
Use `--php-listen 127.0.0.1:8082` to change the combined example's second address.
The startup output prints the control socket and commands to query it.

For the combined example, change the Python process count:

```sh
curl --unix-socket ./state/control.sock -X PUT --data '2' \
    http://localhost/config/applications/python/processes
```

Ctrl-C stops the server and its application processes. Start with the same `--state`
to restore API configuration, including process counts and listening addresses.
Without `--state`, configuration is temporary and removed on shutdown.
Persistent state requires `flock`, provided by util-linux on Debian/Ubuntu.

`--control /path/to/control.sock` overrides the control socket. It must be a filesystem
Unix socket in an existing directory. With `--state`, it defaults to
`STATE_DIRECTORY/control.sock`. Each concurrent instance needs its own state,
control socket, and listening addresses.

## Python Applications

Single-language bundles infer the language. Add `--language python` when using the
combined bundle. The examples below start separate instances; run them separately
or assign distinct `--listen` addresses.

### FastAPI

For `/srv/api/main.py` containing a FastAPI instance named `app`:

```sh
./python -m pip install --target /srv/api/vendor -r /srv/api/requirements.txt
./worker --language python --app /srv/api --module main --callable app \
    --protocol asgi --python-path /srv/api/vendor --state ./api-state
```

### Django

For `/srv/site/manage.py` and `/srv/site/mysite/wsgi.py`:

```sh
./python -m pip install --target /srv/site/vendor -r /srv/site/requirements.txt
PYTHONPATH=/srv/site/vendor ./python /srv/site/manage.py migrate
PYTHONPATH=/srv/site/vendor ./python /srv/site/manage.py collectstatic --noinput
./worker --language python --app /srv/site --module mysite.wsgi \
    --python-path /srv/site/vendor --state ./django-state
```

Configure Django's `ALLOWED_HOSTS`, database, and `STATIC_ROOT` for the deployment.
The default callable is `application`. Generic WSGI apps use `--module wsgi`;
ASGI apps also need `--protocol asgi` and the appropriate `--callable`.
Native dependencies need wheels compatible with the bundled Python, CPU, and glibc.
The bundle does not include development headers or a compiler.

## PHP Applications

For a front controller at `/srv/site/public/index.php`:

```sh
./php /srv/site/composer.phar install --working-dir=/srv/site
./worker --language php --app /srv/site/public --script index.php --state ./php-state
```

Use `--script auto` for per-file scripts. `./php --version` prints the runtime version;
available extensions are listed in `manifest.json` and `runtime/php.ini`.

## Several Applications

The combined bundle accepts a JSON file such as this:

```json
{
  "applications": {
    "api": {
      "type": "python",
      "listen": "127.0.0.1:8080",
      "path": ["/srv/api", "/srv/api/vendor"],
      "working_directory": "/srv/api",
      "module": "main",
      "callable": "app",
      "protocol": "asgi",
      "processes": 2
    },
    "site": {
      "type": "php",
      "listen": "127.0.0.1:8081",
      "root": "/srv/site/public",
      "working_directory": "/srv/site",
      "script": "index.php",
      "processes": 2
    }
  }
}
```

```sh
./worker --config /srv/apps.json --state ./state
./worker status --state ./state
```

The launcher supplies the bundled Python `home` and PHP `options.file` when omitted.
Explicit values are preserved. Use absolute application paths in JSON files.

Choose how configuration is managed:

- With `--state`, startup application flags initialize empty state. Subsequent starts
  restore API changes; startup flags do not overwrite them.
- With `--config`, the JSON file is applied on every start. API changes last until
  the next start with that file. Omit `--config` on later starts to retain API changes.

To restart application processes after deploying code:

```sh
curl --unix-socket ./state/control.sock http://localhost/control/applications/api/restart
```

## Reverse Proxy And Static Files

Worker serves application requests. A front proxy supplies TLS and static files.
For Django with `STATIC_ROOT=/srv/site/static`, an NGINX server can include:

```nginx
location /static/ {
    alias /srv/site/static/;
}
location / {
    proxy_pass http://127.0.0.1:8080;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

Configure the framework to trust forwarded headers only from your proxy. For PHP
frameworks, configure the proxy to serve the framework's public assets and forward
application requests to Worker; PHP files must be executed by Worker.

## Systemd Services

Install the selected `.deb` with `sudo apt install ./SELECTED_FILE.deb`. Commands and
services are named `worker-all`, `worker-python`, and `worker-php`. Services are
initially disabled. For the combined package:

```sh
sudo systemctl enable --now worker-all
sudo worker-all status --control /run/worker-all/control.sock
sudo journalctl -u worker-all -f
```

Set startup defaults in `/etc/default/worker-all` before the first start, or manage
applications through its control API. Set `WORKER_CONFIG=/etc/worker/apps.json` to
apply a configuration file on each start. The JSON file and application code must
be readable by the service's dynamic user. Keep code outside home directories.

The service provides persistent application storage through `WORKER_DATA_DIR`,
which is `/var/lib/worker-all/data` for the combined package. Configure uploads,
SQLite databases, and other persistent app data under that directory. Worker state
is separate, at `/var/lib/worker-all/state`. The systemd `CACHE_DIRECTORY` points to
`/var/cache/worker-all`. These directories are owned by the service account and
remain usable after restarts and upgrades. Other filesystem locations are read-only
to the service unless explicitly allowed in a systemd override.

For Django SQLite settings, for example:

```python
import os
from pathlib import Path

DATABASES["default"]["NAME"] = Path(os.environ["WORKER_DATA_DIR"]) / "db.sqlite3"
```

Run migrations under the service account using a systemd `ExecStartPre` override,
with the same environment and data directory. Changing permissions on app code
does not make it writable inside the service's read-only filesystem.

Use the corresponding `worker-python` or `worker-php` paths for single-language
services. All services default to 8080; choose distinct addresses if running several.

## Upgrade

Back up your application data and export the live configuration with `./worker config
--state ./state`. For `.deb`, install the selected newer package with `apt`; an active
service restarts, preserving its state and application data. An inactive service
stays inactive. Removing the package stops its service and keeps persistent data.

For tar bundles, stop Worker and replace the bundle at the same absolute install
path, keeping application code, data, and `--state` outside that directory. Keeping
the path preserves saved Python runtime references. To relocate the bundle, start
with a JSON configuration whose Python `home` and PHP `options.file` are omitted,
so the launcher supplies the new runtime paths. Upgrading a bundled runtime requires
a new Worker release; system Python/PHP updates do not update this bundle.

`WORKER_APP`, `WORKER_LANGUAGE`, `WORKER_LISTEN`, `WORKER_PHP_LISTEN`, `WORKER_MODULE`,
`WORKER_CALLABLE`, `WORKER_PROTOCOL`, `WORKER_PYTHON_PATH`, `WORKER_SCRIPT`,
`WORKER_STATE`, `WORKER_CONTROL`, and `WORKER_CONFIG` supply defaults for the matching
command-line options. The process runs as the account that launches it.

Dependency versions and source locations are in `manifest.json` and `SOURCES.md`;
copyright notices are in `licenses/`.
