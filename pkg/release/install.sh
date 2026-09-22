#!/bin/sh
set -eu

usage() {
    printf '%s\n' \
        'Usage: sh install.sh [python|php|all] [--prefix DIRECTORY] [--version VERSION]' \
        '                    [--build ubuntu24.04|debian13]' \
        'Defaults: all (Python + PHP), ./worker-all, latest release, Ubuntu 24.04 build.' \
        'Installs into a new directory without sudo. Existing directories are never replaced.'
}
fail() { printf '%s\n' "$*" >&2; exit 1; }
flavor=all
prefix=
version=
build=ubuntu24.04
case "${1:-}" in python|php|all) flavor=$1; shift ;; esac
while [ "$#" -gt 0 ]; do
    case "$1" in
        --help|-h) usage; exit 0 ;;
        --prefix|--version|--build)
            [ "$#" -ge 2 ] && [ -n "$2" ] || fail "Missing value for $1"
            case "$1" in --prefix) prefix=$2 ;; --version) version=${2#v} ;; --build) build=$2 ;; esac
            shift 2 ;;
        *) fail "Unknown option: $1" ;;
    esac
done
[ "$(uname -s)" = Linux ] || fail 'These packages require Linux; use a Linux VM or build from source.'
case "$(uname -m)" in
    x86_64) arch=amd64 ;; aarch64|arm64) arch=arm64 ;;
    *) fail 'Only Linux x86_64 and aarch64 are supported.' ;;
esac
case "$build" in ubuntu24.04) minimum=2.39 ;; debian13) minimum=2.41 ;; *) fail 'Unknown build system.' ;; esac
glibc=$(getconf GNU_LIBC_VERSION 2>/dev/null) || fail 'glibc is required; Alpine/musl is unsupported.'
glibc=${glibc#glibc }
new_enough() {
    awk -v actual="$glibc" -v required="$1" 'BEGIN {
        if (actual !~ /^[0-9]+\.[0-9]+$/ || required !~ /^[0-9]+\.[0-9]+$/) exit 1;
        split(actual, a, "."); split(required, b, ".");
        exit !(a[1] > b[1] || (a[1] == b[1] && a[2] >= b[2]));
    }'
}
new_enough "$minimum" || fail "This build requires glibc $minimum+; detected $glibc. Use a supported OS or build from source."
for tool in curl tar sha256sum mktemp mv; do
    command -v "$tool" >/dev/null || fail "Required command not found: $tool"
done
base=https://github.com/hongzhidao/worker/releases/latest/download
if [ -n "$version" ]; then
    printf '%s\n' "$version" | awk '/^[0-9]+\.[0-9]+\.[0-9]+$/ {found=1} END {exit !found}' || fail 'Version must be MAJOR.MINOR.PATCH.'
    base=https://github.com/hongzhidao/worker/releases/download/v$version
fi
base=${WORKER_DOWNLOAD_BASE_URL:-$base}
prefix=${prefix:-./worker-$flavor}
[ ! -e "$prefix" ] && [ ! -L "$prefix" ] || fail "Destination exists: $prefix. Choose a new --prefix."
mkdir -p -- "$(dirname -- "$prefix")"
parent=$(CDPATH= cd -- "$(dirname -- "$prefix")" && pwd -P)
prefix=$parent/$(basename -- "$prefix")
temporary=$(mktemp -d "$parent/.worker-download.XXXXXXXX")
trap 'rm -rf -- "$temporary"' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM HUP
download() {
    curl --fail --location --silent --show-error --retry 3 --connect-timeout 15 \
        --max-time 600 --proto '=https,file' --proto-redir '=https' "$base/$1" --output "$2"
}
download downloads.tsv "$temporary/downloads.tsv" || fail 'Cannot read the release download index. Check the release URL and network connection.'
artifact=
digest=
tab=$(printf '\t')
while IFS="$tab" read -r row_build row_arch row_flavor row_glibc row_file row_hash; do
    if [ "$row_build" = "$build" ] && [ "$row_arch" = "$arch" ] && [ "$row_flavor" = "$flavor" ]; then
        [ -z "$artifact" ] || fail 'The release contains duplicate matching packages.'
        artifact=$row_file
        digest=$row_hash
        new_enough "$row_glibc" || fail "Package requires glibc $row_glibc+; detected $glibc."
    fi
done < "$temporary/downloads.tsv"
[ -n "$artifact" ] || fail "No $flavor package for $build/$arch in this release."
case "$artifact" in *[!a-zA-Z0-9._-]*) fail 'Invalid artifact name in download index.' ;; esac
case "$artifact" in worker-*.tar.gz) ;; *) fail 'Invalid artifact type in download index.' ;; esac
case "$digest" in *[!a-fA-F0-9]*) fail 'Invalid SHA256 in download index.' ;; esac
[ "${#digest}" -eq 64 ] || fail 'Invalid SHA256 length in download index.'
printf 'Downloading %s\n' "$artifact"
download "$artifact" "$temporary/$artifact"
printf '%s  %s\n' "$digest" "$artifact" > "$temporary/checksum"
(cd "$temporary" && sha256sum --check checksum)

# Validate archive member names before extraction.  Release archives are
# trusted by checksum, but refusing traversal and absolute names keeps the
# installer safe when pointed at a mirror or local file URL.
tar -tzf "$temporary/$artifact" | awk '
    /^\// || /(^|\/)\.\.(\/|$)/ { bad = 1 }
    END { exit bad }
' || fail 'Package contains an unsafe archive path.'
mkdir "$temporary/bundle"
tar -xzf "$temporary/$artifact" --strip-components=1 --no-same-owner --no-same-permissions -C "$temporary/bundle"

bundle=$temporary/bundle
[ -x "$bundle/worker" ] || fail 'Package does not contain an executable Worker launcher.'
[ -f "$bundle/manifest.json" ] || fail 'Package does not contain manifest.json.'
[ -f "$bundle/bundle.env" ] || fail 'Package does not contain bundle.env.'
[ -x "$bundle/bin/workerd" ] || fail 'Package does not contain an executable bin/workerd.'
[ -x "$bundle/bin/curl" ] || fail 'Package does not contain an executable bin/curl.'
[ -d "$bundle/modules" ] || fail 'Package does not contain modules/.'
[ -d "$bundle/runtime" ] || fail 'Package does not contain runtime/.'

# bundle.env is generated by the release builder and is deliberately checked
# without sourcing data from the downloaded archive.
grep -Fqx "WORKER_FLAVOR=$flavor" "$bundle/bundle.env" \
    || fail 'Package flavor does not match the requested flavor.'
grep -Fqx "WORKER_ARCH=$arch" "$bundle/bundle.env" \
    || fail 'Package architecture does not match the host.'
grep -Eq "^WORKER_GLIBC_MIN=" "$bundle/bundle.env" \
    || fail 'Package does not declare a glibc minimum.'
if [ -n "$version" ]; then
    grep -Fqx "WORKER_VERSION=$version" "$bundle/bundle.env" \
        || fail 'Package version does not match the requested version.'
fi

case "$flavor" in
    python)
        [ -x "$bundle/python" ] || fail 'Python package does not contain its python launcher.'
        [ -x "$bundle/runtime/bin/python" ] || fail 'Python package does not contain runtime/bin/python.'
        find "$bundle/modules" -maxdepth 1 -type f -name 'python*.worker.so' -print -quit | grep -q . \
            || fail 'Python package does not contain a Python Worker module.'
        ;;
    php)
        [ -x "$bundle/php" ] || fail 'PHP package does not contain its php launcher.'
        [ -x "$bundle/runtime/bin/php" ] || fail 'PHP package does not contain runtime/bin/php.'
        find "$bundle/modules" -maxdepth 1 -type f -name 'php*.worker.so' -print -quit | grep -q . \
            || fail 'PHP package does not contain a PHP Worker module.'
        ;;
    all)
        [ -x "$bundle/python" ] || fail 'Combined package does not contain its python launcher.'
        [ -x "$bundle/php" ] || fail 'Combined package does not contain its php launcher.'
        [ -x "$bundle/runtime/bin/python" ] || fail 'Combined package does not contain runtime/bin/python.'
        [ -x "$bundle/runtime/bin/php" ] || fail 'Combined package does not contain runtime/bin/php.'
        find "$bundle/modules" -maxdepth 1 -type f -name 'python*.worker.so' -print -quit | grep -q . \
            || fail 'Combined package does not contain a Python Worker module.'
        find "$bundle/modules" -maxdepth 1 -type f -name 'php*.worker.so' -print -quit | grep -q . \
            || fail 'Combined package does not contain a PHP Worker module.'
        ;;
esac
"$bundle/worker" --version >/dev/null 2>&1 \
    || fail 'Worker launcher failed its version check.'
mv -T --no-clobber -- "$bundle" "$prefix"
[ ! -d "$temporary/bundle" ] || fail "Destination appeared during download: $prefix"
printf 'Installed: %s\nStart:\n  ' "$prefix"
printf "'%s'" "$(printf '%s' "$prefix/worker" | sed "s/'/'\\\\''/g")"
printf ' --state ./worker-state\n'
