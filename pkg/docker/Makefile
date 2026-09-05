#!/usr/bin/make

include ../../version
include ../shasum.mak

DEFAULT_VERSION := $(NXT_VERSION)

VERSION ?= $(DEFAULT_VERSION)
EXPORT_DIR := $(VERSION)

MODULES ?= go node perl php python ruby

VARIANT ?= bullseye

VERSIONS_minimal ?=
CONTAINER_minimal ?= debian:$(VARIANT)-slim
CONFIGURE_minimal ?=
INSTALL_minimal ?=	version
define COPY_minimal
endef

VERSIONS_go ?=		1.17
VARIANT_go ?=		$(VARIANT)
$(foreach goversion, $(VERSIONS_go), $(eval CONTAINER_go$(goversion) = golang:$(goversion)-$(VARIANT_go)))
CONFIGURE_go ?=		go --go-path=$$GOPATH
INSTALL_go ?=		go-install-src libworker-install
define COPY_go
COPY --from=BUILDER /usr/lib/x86_64-linux-gnu/libworker.a /usr/lib/x86_64-linux-gnu/\n\$
COPY --from=BUILDER /usr/include/nxt_* /usr/include/\n\$
COPY --from=BUILDER /go/src/ /go/src/
endef

VERSIONS_node ?=	16
VARIANT_node ?=		$(VARIANT)
$(foreach nodeversion, $(VERSIONS_node), $(eval CONTAINER_node$(nodeversion) = node:$(nodeversion)-$(VARIANT_node)))
CONFIGURE_node ?=	nodejs --node-gyp=/usr/local/lib/node_modules/npm/bin/node-gyp-bin/node-gyp
INSTALL_node ?=		node node-install libworker-install
define COPY_node
COPY --from=BUILDER /usr/lib/x86_64-linux-gnu/libworker.a /usr/lib/x86_64-linux-gnu/\n\$
COPY --from=BUILDER /usr/include/nxt_* /usr/include/\n\$
COPY --from=BUILDER /usr/local/lib/node_modules/worker-http/ /usr/local/lib/node_modules/worker-http/
endef

VERSIONS_perl ?=	5.34
VARIANT_perl ?=		$(VARIANT)
$(foreach perlversion, $(VERSIONS_perl), $(eval CONTAINER_perl$(perlversion) = perl:$(perlversion)-$(VARIANT_perl)))
CONFIGURE_perl ?=	perl
INSTALL_perl ?=		perl-install
COPY_perl =

VERSIONS_php ?=		8.0
VARIANT_php ?=		cli-$(VARIANT)
$(foreach phpversion, $(VERSIONS_php), $(eval CONTAINER_php$(phpversion) = php:$(phpversion)-$(VARIANT_php)))
CONFIGURE_php ?=	php
INSTALL_php ?=		php-install
COPY_php =			RUN ldconfig

VERSIONS_python ?=	3.9
VARIANT_python ?=	$(VARIANT)
$(foreach pythonversion, $(VERSIONS_python), $(eval CONTAINER_python$(pythonversion) = python:$(pythonversion)-$(VARIANT_python)))
CONFIGURE_python ?=	python --config=/usr/local/bin/python3-config
INSTALL_python ?=	python3-install
COPY_python =

VERSIONS_ruby ?=	3.0
VARIANT_ruby ?=		$(VARIANT)
$(foreach rubyversion, $(VERSIONS_ruby), $(eval CONTAINER_ruby$(rubyversion) = ruby:$(rubyversion)-$(VARIANT_ruby)))
CONFIGURE_ruby ?=	ruby
INSTALL_ruby ?=		ruby-install
COPY_ruby =			RUN gem install rack

default:
	@echo "valid targets: all build dockerfiles push tag export clean"

MODVERSIONS = $(foreach module, $(MODULES), $(foreach modversion, $(shell for v in $(VERSIONS_$(module)); do echo $$v; done | sort -r), $(module)$(modversion))) minimal

modname = $(shell echo $1 | /usr/bin/tr -d '.01234567890-')

dockerfiles: $(addprefix Dockerfile., $(MODVERSIONS))
build: $(addprefix build-,$(MODVERSIONS))
tag: $(addprefix tag-,$(MODVERSIONS))
push: $(addprefix push-,$(MODVERSIONS))
export: $(addsuffix .tar.gz,$(addprefix $(EXPORT_DIR)/worker-$(VERSION)-,$(MODVERSIONS))) $(addsuffix .tar.gz.sha512, $(addprefix $(EXPORT_DIR)/worker-$(VERSION)-,$(MODVERSIONS)))

Dockerfile.%: ../../version
	@echo "===> Building $@"
	cat template.Dockerfile | sed \
			-e 's,@@VERSION@@,$(VERSION),g' \
			-e 's,@@CONTAINER@@,$(CONTAINER_$*),g' \
			-e 's,@@CONFIGURE@@,$(CONFIGURE_$(call modname, $*)),g' \
			-e 's,@@INSTALL@@,$(INSTALL_$(call modname, $*)),g' \
			-e 's,@@COPY@@,$(COPY_$(call modname, $*)),g' \
			> $@

build-%: Dockerfile.%
	docker pull $(CONTAINER_$*)
	docker build --no-cache -t worker:$(VERSION)-$* -f Dockerfile.$* .

tag-%: build-%
	docker tag worker:$(VERSION)-$* hongzhidao/worker:$(VERSION)-$*

push-%: tag-%
	docker push hongzhidao/worker:$(VERSION)-$*

$(EXPORT_DIR):
	mkdir -p $@

$(EXPORT_DIR)/worker-$(VERSION)-%.tar.gz: $(EXPORT_DIR) tag-%
	docker save hongzhidao/worker:$(VERSION)-$* | gzip > $@

$(EXPORT_DIR)/worker-$(VERSION)-%.tar.gz.sha512: $(EXPORT_DIR)/worker-$(VERSION)-%.tar.gz
	$(SHA512SUM) $< | sed 's,$(EXPORT_DIR)/,,' > $@

all: $(addprefix Dockerfile., $(MODVERSIONS))

clean:
	rm -f $(addprefix Dockerfile., $(MODVERSIONS))
	rm -rf $(EXPORT_DIR)

.PHONY: default build dockerfiles push tag export clean
