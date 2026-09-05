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

Worker accepts HTTP requests and passes each listener directly to an
application. It can also run behind an external reverse proxy.

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

## Run

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
    "listeners": {
        "127.0.0.1:8080": {
            "pass": "applications/example"
        }
    },
    "applications": {
        "example": {
            "type": "python",
            "path": "/srv/example",
            "module": "wsgi"
        }
    }
}
EOF
```

## Manage Applications

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
