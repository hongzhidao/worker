# Linux Runtime Releases

Release packages contain a complete Python or PHP environment, not just `workerd`.
Users do not need a compiler, development headers, or a system Python/PHP runtime.
Their application dependencies remain their own responsibility.

## Supported Builds

| Build system | Architecture | Python | PHP | Minimum host glibc |
| --- | --- | --- | --- | --- |
| Ubuntu 24.04 | amd64, arm64 | 3.12 | 8.3 | 2.39 |
| Debian 13 | amd64, arm64 | 3.13 | 8.4 | 2.41 |

These are glibc Linux builds. Alpine/musl and older glibc versions are unsupported.
The launcher checks architecture and glibc before loading the runtime. Patch
versions of Python come from the build distribution's security updates. PHP uses
the upstream security releases and verified source hashes pinned in `runtimes.json`,
with internal timezone data so it does not depend on host `/usr/share/zoneinfo`.
Every runtime version is recorded in `manifest.json`. Files are named with flavor, runtime version,
Worker version, build distribution, and architecture.

Each build produces a relocatable `.tar.gz`, a `.deb` containing the same runtime,
and SHA256 files. Python includes its standard library and pip; PHP includes common
extensions such as curl, mbstring, XML, PDO, MySQL, SQLite, intl, zip, and GD.
Installed extension names, library packages, licenses, and corresponding source
locations are included in the package. glibc is supplied by the host OS.

## User Workflow

Download a package from [Releases](https://github.com/hongzhidao/worker/releases),
verify its checksum, and extract it into its own directory. Start the included
example with `./worker`, or provide an application directory:

```sh
# Python WSGI (application in /srv/myapp/wsgi.py)
./worker --app /srv/myapp --module wsgi

# Python ASGI
./worker --app /srv/myapp --module asgi --protocol asgi

# PHP front controller
./worker --app /srv/myapp/public --script index.php
```

Both default to `127.0.0.1:8080`. Use `--listen 0.0.0.0:8080` for external access.
The bundled `./python` or `./php` runs scripts and dependency tooling. For Python,
`./python -m pip install --target /srv/myapp/vendor -r requirements.txt` installs
dependencies; pass `--python-path /srv/myapp/vendor` when starting Worker.

Install the `.deb` with `sudo apt install ./worker-<flavor>...deb`, then use
`worker-python` or `worker-php`. The optional systemd units are disabled initially;
configure `/etc/default/worker-python` or `/etc/default/worker-php` before enabling
the corresponding service. See [the bundled README](BUNDLE_README.md) for details.

## Build And Verify

On a supported Debian/Ubuntu build machine:

```sh
sudo sh pkg/release/install-build-deps.sh python
python3 pkg/release/build.py python --source-ref HEAD

sudo sh pkg/release/install-build-deps.sh php
python3 pkg/release/build.py php --source-ref HEAD
```

Builds use an isolated source directory under `build/`, preserving any existing
developer build. `--source-ref` selects committed core sources. Local worktree builds
are marked in the manifest; the publishing step rejects dirty builds.

The CI smoke test starts each artifact in a fresh base container with no language
runtime or compiler installed. It verifies relocation into a directory with spaces,
runtime startup, real GET/POST application requests, Python native modules and pip,
PHP extensions, and graceful shutdown. `.deb` files are installed with `dpkg` in a
fresh container before the same application checks run.

```sh
python3 pkg/release/smoke.py --container ubuntu:24.04 build/release/*.tar.gz build/release/*.deb
```

`smoke.py` also supports native development checks and `--chroot` checks inside a
private mount/network namespace. The latter requires root and is useful without Docker.

## Publish

`.github/workflows/release.yml` builds the eight distribution/architecture/flavor
combinations. Pull requests, main-branch pushes, and manual runs produce test
artifacts only. Pushing a tag such as `v0.1.0` whose version matches `version`
publishes a GitHub Release after every build and installation test succeeds.

The publisher verifies the complete matrix, source revision, clean build state,
and checksums, uploads all files to a draft release, then makes it public. Existing
releases are never overwritten. A failed upload leaves a draft for inspection;
remove that draft before rerunning the publication job. Use a new Worker patch tag
to publish updated bundled runtimes. Source changes do not publish anything until
a matching version tag is pushed.
