#!/usr/bin/make

include ../version
include shasum.mak

VERSION ?= $(NXT_VERSION)
RELEASE ?= 1

default:
	@echo "available targets: dist rpm deb docker"

dist:
	rm -f worker-$(VERSION).tar.gz
	cd .. && git archive \
		--output pkg/worker-$(VERSION).tar.gz \
		--prefix worker-$(VERSION)/ \
		--worktree-attributes \
		$(VERSION) ./
	$(SHA512SUM) worker-$(VERSION).tar.gz > worker-$(VERSION).tar.gz.sha512

rpm:
	@cd rpm && VERSION=$(VERSION) RELEASE=$(RELEASE) make all

deb:
	@cd deb && VERSION=$(VERSION) RELEASE=$(RELEASE) make all

docker:
	@cd docker && VERSION=$(VERSION) RELEASE=$(RELEASE) make all

clean:
	@cd rpm && make clean
	@cd deb && make clean
	@cd docker && make clean
	rm -f worker-$(VERSION).tar.gz
	rm -f worker-$(VERSION).tar.gz.sha512

.PHONY: default rpm deb docker clean
