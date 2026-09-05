#!/usr/bin/make

include ../../version

VERSION ?= $(NXT_VERSION)
VERNUM ?= $(NXT_VERNUM)
NPM ?= npm

default:
	@echo "valid targets: all publish clean"

copy:
	cp -rp ../../src/nodejs/worker-http .
	echo '#define NXT_NODE_VERNUM ${VERNUM}' > worker-http/version.h
	mv worker-http/binding_pub.gyp worker-http/binding.gyp
	sed -e 's/"version"\s*:.*/"version": "${VERSION}",/' \
		worker-http/package.json > worker-http/package.json.tmp
	mv worker-http/package.json.tmp worker-http/package.json

publish: copy
	cd worker-http && $(NPM) publish

all: copy

clean:
	rm -rf worker-http

.PHONY: default all copy publish clean
