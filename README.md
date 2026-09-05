# Worker

Worker is an application server for running and managing PHP, Python, Go, and
Ruby applications through a JSON control API.

- **Dynamic**: Configure, scale, and restart applications through the API so
  deployment systems can manage them automatically.
- **Multi-language**: Use a unified management approach for PHP, Python, Go,
  and Ruby, reducing duplicated deployment and maintenance tooling.
- **Observable**: Inspect request, connection, and application process
  statistics directly through the status API once applications are running.
- **High performance**: Keep the resource overhead of unified application
  management low. Performance claims must be backed by reproducible tests.

Worker accepts HTTP requests at application or target listening addresses.
Worker can also run behind an external reverse proxy.

## Download And Try

The installer, combined bundle, and persistent launcher below are prepared for the
next runtime release. The published [v0.1.0 packages](https://github.com/hongzhidao/worker/releases/tag/v0.1.0)
contain the earlier single-language launcher: extract the selected archive, enter
its directory, and run `./worker` to try its example.

On Linux x86_64 or ARM64 with glibc 2.39 or newer:

```sh
curl -fLO https://github.com/hongzhidao/worker/releases/latest/download/install.sh
sh install.sh all
./worker-all/worker --state ./worker-state
```

The installer detects CPU architecture, checks compatibility, verifies the package's
SHA256 checksum, and extracts it into `./worker-all`. It needs no sudo and never
replaces an existing directory. Worker and both language runtimes are included.

In another terminal in the same directory:

```sh
curl http://127.0.0.1:8080/   # Python example
curl http://127.0.0.1:8081/   # PHP example, in the same Worker instance
./worker-all/worker status --state ./worker-state
```

Change the Python application's process count while both apps are running:

```sh
curl --unix-socket ./worker-state/control.sock -X PUT --data '2' \
    http://localhost/config/applications/python/processes
./worker-all/worker config --state ./worker-state
```

Ctrl-C stops Worker. Starting it again with the same `--state` restores API changes.
Without `--state`, the launcher runs a temporary instance removed on shutdown.

| Package | Install command | Included applications |
| --- | --- | --- |
| Python + PHP | `sh install.sh all` | Both runtimes, one control and statistics API |
| Python | `sh install.sh python` | Python WSGI and ASGI |
| PHP | `sh install.sh php` | PHP scripts and front controllers |

Use `--prefix /path/to/new-directory` to choose the install location or `--version
MAJOR.MINOR.PATCH` to pin a release. The default build includes Python 3.12 and/or
PHP 8.3. `--build debian13` selects Python 3.13 and/or PHP 8.4 and requires glibc 2.41+.
Alpine/musl and older glibc are unsupported by these binary packages.

For manual downloads and `.deb` installation, use the download table on
[Releases](https://github.com/hongzhidao/worker/releases/latest).
Check your host with `uname -m` and `getconf GNU_LIBC_VERSION`.
Go and Ruby integrations are currently built from source.

## Run Your Application

For the combined package, select a language for a single application:

```sh
# FastAPI: app in /srv/api/main.py, dependencies in /srv/api/vendor
./worker-all/python -m pip install --target /srv/api/vendor -r /srv/api/requirements.txt
./worker-all/worker --language python --app /srv/api --module main --callable app \
    --protocol asgi --python-path /srv/api/vendor --state ./api-state

# PHP: /srv/site/public/index.php
./worker-all/worker --language php --app /srv/site/public --state ./site-state
```

Run these alternatives separately, or select different `--listen` addresses.
Use `--config /path/to/apps.json` to configure several applications in one instance.
The startup output includes the control socket and ready-to-run statistics commands.
See the [application and service guide](pkg/release/BUNDLE_README.md) for Django,
multiple applications, persistent storage, static files, systemd, and upgrades.

## Build

A C toolchain and the development files for the selected language runtimes
are required. For a Python application:

```sh
./configure
./configure python --config=python3-config
make
```

Configure additional integrations before running `make`:

```sh
./configure php
./configure ruby
```

Go applications use the package in `go/`. Prepare its source and build
environment with:

```sh
./configure go --go-path="$PWD/build/go"
make go-install-src go-install-env
```

The C application library provides one execution context per `nxt_unit_init()`
call. The `nxt_unit_ctx_alloc()` API for additional thread contexts has been
removed. Go continues to process requests concurrently using the shared context.

## Run From Source

Start the daemon in the foreground with a local control socket:

```sh
mkdir -p build/state
build/workerd --no-daemon --modules build --state build/state \
    --pid build/worker.pid --log build/worker.log --tmp /tmp \
    --control unix:/tmp/control.worker.sock
```

The following configuration serves a Python WSGI application defined as
`application` in `/srv/example/wsgi.py`. The application directory must be
readable by the configured application user.

```sh
curl -X PUT --data-binary @- \
    --unix-socket /tmp/control.worker.sock \
    http://localhost/config/ <<'EOF'
{
    "applications": {
        "example": {
            "listen": "127.0.0.1:8080",
            "type": "python",
            "path": "/srv/example",
            "module": "wsgi"
        }
    }
}
EOF
```

## Manage Applications

The following commands use the source-build control socket above. With a runtime
package, substitute the control socket printed by `./worker`; with the quick start,
use `./worker-state/control.sock`. The combined example's application names are
`python` and `php`; a single-app launch uses `app`.

Applications without `targets` must specify exactly one `listen` address.
Python and PHP applications with `targets` must omit the application's `listen`;
each target must specify its own `listen`, and `targets` must not be empty.
Go and Ruby applications use the application-level `listen`.

Every `listen` must be a nonempty address string, not an array.
IPv4, IPv6, and Unix socket addresses are supported, for example
`127.0.0.1:8080`, `[::1]:8080`, and `unix:/tmp/example.sock`. Listening addresses
must be unique across all applications and targets; equivalent address spellings
are duplicates.
The top-level `listeners` object is no longer supported.

Change an application's listening address without restarting its processes:

```sh
curl -X PUT --data '"127.0.0.1:8081"' --unix-socket /tmp/control.worker.sock \
    http://localhost/config/applications/example/listen
```

If the new address cannot be bound, the previous configuration remains active.
Deleting an application releases all its listening addresses. Deleting a target
releases that target's address; deleting only a required `listen` field or the
last target is rejected. `{"applications": {}}` is a valid empty configuration.

For example, these Python targets share the application's process pool and
accept requests on separate ports:

```json
{
    "applications": {
        "example": {
            "type": "python",
            "path": "/srv/example",
            "targets": {
                "api": {"listen": "127.0.0.1:8080", "module": "api"},
                "admin": {"listen": "127.0.0.1:8081", "module": "admin"}
            }
        }
    }
}
```

Update `/config/applications/example/targets/api/listen` to move only the API
listener. Changing a target's listening address also preserves application
processes and in-flight requests.

Python and Ruby application processes each use a single request-handling thread.
The `threads` and `thread_stack_size` application options are not supported.
Use `processes` to scale request handling; ASGI also supports concurrent requests
within its event loop. Ruby's `on_thread_boot` and `on_thread_shutdown` hooks run
once per application process.

Set the application to two processes:

```sh
curl -X PUT --data '2' --unix-socket /tmp/control.worker.sock \
    http://localhost/config/applications/example/processes
```

Restart its processes after deploying new application code:

```sh
curl --unix-socket /tmp/control.worker.sock \
    http://localhost/control/applications/example/restart
```

Inspect the current configuration and runtime statistics:

```sh
curl --unix-socket /tmp/control.worker.sock http://localhost/config/
curl --unix-socket /tmp/control.worker.sock http://localhost/status
```

The status response includes total requests; accepted, active, idle, and
closed connections; and running, starting, and idle processes plus active
requests for each application.

## Source And License

Source: <https://github.com/hongzhidao/worker>

Worker is derived from NGINX Unit and licensed under the Apache License 2.0.
See [LICENSE](LICENSE) and [NOTICE](NOTICE).
