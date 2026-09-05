#!/bin/sh
set -eu
python_packages='python3-dev python3-venv'
php_packages='bison re2c libssl-dev libxml2-dev libonig-dev libzip-dev libicu-dev libcurl4-openssl-dev libsqlite3-dev libpng-dev libjpeg-dev libfreetype-dev libsodium-dev libargon2-dev zlib1g-dev'
case "${1:-}" in
    python) runtime_packages=$python_packages ;;
    php) runtime_packages=$php_packages ;;
    all) runtime_packages="$python_packages $php_packages" ;;
    *) printf 'Usage: install-build-deps.sh python|php|all\n' >&2; exit 2 ;;
esac
export DEBIAN_FRONTEND=noninteractive
apt-get update
# Package names above are fixed lists, intentionally split into separate arguments.
apt-get install -y --no-install-recommends build-essential git ca-certificates \
    curl pkg-config libcap-dev libpcre2-dev python3 util-linux $runtime_packages
