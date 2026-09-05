# Worker Runtime Bundle

This package includes Worker, its language module, the Python or PHP runtime,
and their shared libraries. A compiler and a system Python/PHP installation are
not required. Linux with the architecture and minimum glibc version recorded in
`manifest.json` is required. Alpine/musl is not supported by these packages.

Start the included example with `./worker`. It listens on 127.0.0.1:8080 and runs
in the foreground. Ctrl-C stops the server and its application processes.

## Python

```sh
./worker --app /srv/myapp --module wsgi --callable application
./worker --app /srv/myapp --module asgi --protocol asgi
./python -m pip install --target /srv/myapp/vendor -r /srv/myapp/requirements.txt
./worker --app /srv/myapp --module wsgi --python-path /srv/myapp/vendor
```

Application dependencies are separate from the included language runtime.
Packages with native extensions need wheels compatible with this Python version,
architecture, and glibc. This bundle does not include a compiler or development SDK.

## PHP

```sh
./worker --app /srv/myapp/public --script index.php
./worker --app /srv/scripts --script auto
./php --version
./php /srv/myapp/composer.phar install
```

The default PHP entry point is `index.php` for every request. `--script auto`
enables per-file PHP scripts. Static assets should be served by a reverse proxy.
The packaged extensions are listed in `manifest.json` and `runtime/php.ini`.

## Operation

Use `--listen 0.0.0.0:8080` to accept external connections. The process runs as the
account that launches it. Its private control socket and state live in a temporary
directory removed on shutdown. App files and app data remain in your app directory.

`WORKER_APP`, `WORKER_LISTEN`, `WORKER_MODULE`, `WORKER_CALLABLE`, `WORKER_PROTOCOL`,
`WORKER_PYTHON_PATH`, and `WORKER_SCRIPT` provide environment defaults for the same
command-line options. Re-extract a new version into a separate directory and restart
with the same app arguments to upgrade. Keep app code and data outside the bundle.

The `.deb` edition installs the same bundle under `/opt/worker/python` or
`/opt/worker/php`, with `worker-python` or `worker-php` on PATH. Configure the service
in `/etc/default/worker-python` or `/etc/default/worker-php`, then run
`sudo systemctl enable --now worker-python` (or `worker-php`). Services are not
automatically enabled on installation. The service uses a dedicated dynamic user;
your app must be readable by that account. Both services default to port 8080,
so set different ports when running both.

Copyright notices are in `licenses/`; matching dependency source locations and
versions are in `SOURCES.md` and `manifest.json`.
