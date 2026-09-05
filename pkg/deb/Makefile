#!/usr/bin/make

include ../../version

DEFAULT_VERSION := $(NXT_VERSION)
DEFAULT_RELEASE := 1

VERSION ?= $(DEFAULT_VERSION)
RELEASE ?= $(DEFAULT_RELEASE)

PACKAGE_VENDOR = Worker Project <hongzhidao@gmail.com>

SRCDIR=	worker-$(VERSION)

CODENAME = $(shell lsb_release -cs)

BUILD_DEPENDS_worker = build-essential debhelper devscripts fakeroot libxml2-utils lintian lsb-release xsltproc
BUILD_DEPENDS = $(BUILD_DEPENDS_worker)

MODULES=

# Ubuntu 21.10
ifeq ($(CODENAME),impish)
include Makefile.php
include Makefile.python27
include Makefile.python39
include Makefile.python310
include Makefile.go
include Makefile.ruby
endif

# Ubuntu 21.04
ifeq ($(CODENAME),hirsute)
include Makefile.php
include Makefile.python27
include Makefile.python39
include Makefile.go
include Makefile.ruby
endif

# Ubuntu 20.04
ifeq ($(CODENAME),focal)
include Makefile.php
include Makefile.python27
include Makefile.python38
include Makefile.go
include Makefile.ruby
endif

# Ubuntu 18.04
ifeq ($(CODENAME),bionic)
include Makefile.php
include Makefile.python27
include Makefile.python36
include Makefile.python37
include Makefile.python38
include Makefile.go
include Makefile.ruby
endif

# Debian 11
ifeq ($(CODENAME),bullseye)
include Makefile.php
include Makefile.python27
include Makefile.python39
include Makefile.go
include Makefile.ruby
endif

# Debian 10
ifeq ($(CODENAME),buster)
include Makefile.php
include Makefile.python27
include Makefile.python37
include Makefile.go
include Makefile.ruby
endif

CONFIGURE_ARGS_COMMON=\
	--prefix=/usr \
	--state=/var/lib/worker \
	--control="unix:/var/run/control.worker.sock" \
	--pid=/var/run/worker.pid \
	--log=/var/log/worker.log \
	--tmp=/var/tmp \
	--user=worker \
	--group=worker \
	--tests

CONFIGURE_ARGS=$(CONFIGURE_ARGS_COMMON)

export CR=\\n

default:
	@echo "valid targets: all modules worker $(addprefix worker-, $(MODULES)) test test-debug clean"

all: check-build-depends-all worker modules

modules: $(addprefix worker-, $(MODULES))

check-build-depends-%:
	@{ \
	case "$*" in \
		all) pkgs="$(BUILD_DEPENDS)" ;; \
		worker) pkgs="$(BUILD_DEPENDS_worker)" ;; \
		*) pkgs="$(BUILD_DEPENDS_worker) $(BUILD_DEPENDS_$*)" ;; \
	esac ; \
	not_installed= ; \
	for pkg in $${pkgs}; do \
		i=$$(dpkg-query -f '$${db:Status-Status}' -W $${pkg}:$$(dpkg --print-architecture) 2>/dev/null) ; \
		if [ $$? -ne 0 -o "$${i}" != "installed" ]; then \
			i=$$(dpkg-query -f '$${db:Status-Status}' -W $${pkg}:all 2>/dev/null) ; \
			if [ $$? -ne 0 -o "$${i}" != "installed" ]; then \
				not_installed="$${not_installed} $${pkg}" ; \
			fi; \
		fi ; \
	done ; \
	if test -n "$${not_installed}" ; then \
		echo "" >&2 ; \
		echo "The following packages are required in order to proceed:" >&2 ; \
		echo "" >&2 ; \
		echo $${not_installed} >&2 ; \
		echo "" >&2 ; \
		exit 1 ; \
	fi \
	}
	touch $@

debuild/$(SRCDIR)/debian:
	@{ \
	set -e ; \
	mkdir -p debuild/$(SRCDIR) ; \
	cp -pr debian debuild/$(SRCDIR) ; \
	echo '11' > debuild/$(SRCDIR)/debian/compat ; \
	mkdir -p debuild/$(SRCDIR)/debian/source ; \
	echo '3.0 (quilt)' > debuild/$(SRCDIR)/debian/source/format ; \
	cat debian/control.in | sed \
		-e "s#%%PACKAGE_VENDOR%%#$(PACKAGE_VENDOR)#g" \
	> debuild/$(SRCDIR)/debian/control ; \
        cat debian/rules.in | sed \
                -e "s#%%CONFIGURE_ARGS%%#$(CONFIGURE_ARGS)#g" \
        > debuild/$(SRCDIR)/debian/rules ; \
	chmod +x debuild/$(SRCDIR)/debian/rules ; \
	}

debuild/$(SRCDIR)/debian/changelog: ../../docs/changes.xml | debuild/$(SRCDIR)/debian
	cd ../../docs && make ../build/worker.deb-changelog
ifneq ($(DEFAULT_VERSION)$(DEFAULT_RELEASE), $(VERSION)$(RELEASE))
	cat ../../build/worker.deb-changelog | sed \
		-e "s/worker ($(DEFAULT_VERSION)-$(DEFAULT_RELEASE)~/worker ($(VERSION)-$(RELEASE)~/" \
		-e "s#%%CODENAME%%#$(CODENAME)#g" \
		> debuild/$(SRCDIR)/debian/changelog
else
	cat ../../build/worker.deb-changelog | sed \
		-e "s#%%CODENAME%%#$(CODENAME)#g" \
		> debuild/$(SRCDIR)/debian/changelog
endif

debuild/worker_$(VERSION).orig.tar.gz: | debuild/$(SRCDIR)/debian
	cd ../.. && tar -czf pkg/deb/debuild/$(SRCDIR).tar.gz \
		--transform "s#^#$(SRCDIR)/#" \
		LICENSE NOTICE CHANGES README configure auto src test version go docs/man/workerd.8.in
	mv debuild/$(SRCDIR).tar.gz debuild/worker_$(VERSION).orig.tar.gz
	cd debuild && tar zxf worker_$(VERSION).orig.tar.gz

worker: check-build-depends-worker debuild/worker_$(VERSION).orig.tar.gz debuild/$(SRCDIR)/debian/changelog
	@echo "===> Building $@ package"
	cd debuild/$(SRCDIR) && debuild -us -uc
	mkdir -p debs
	find debuild/ -maxdepth 1 -type f -exec cp {} debs/ \;
	ln -s debuild/$(SRCDIR)/build $@

debuild-%: debuild/worker_$(VERSION).orig.tar.gz ../../docs/changes.xml
	mkdir $@
	cp debuild/worker_$(VERSION).orig.tar.gz debuild-$*/worker-$(MODULE_SUFFIX_$*)_$(VERSION).orig.tar.gz
	cd $@ && tar zxf worker-$(MODULE_SUFFIX_$*)_$(VERSION).orig.tar.gz
	mkdir $@/$(SRCDIR)/debian
	echo '11' > $@/$(SRCDIR)/debian/compat
	mkdir $@/$(SRCDIR)/debian/source
	echo '3.0 (quilt)' > $@/$(SRCDIR)/debian/source/format
	cd ../../docs && make ../build/worker-$(MODULE_SUFFIX_$*).deb-changelog
ifneq ($(DEFAULT_VERSION)$(DEFAULT_RELEASE), $(VERSION)$(RELEASE))
	cat ../../build/worker-$(MODULE_SUFFIX_$*).deb-changelog | sed \
		-e "s/worker-$* ($(DEFAULT_VERSION)-$(DEFAULT_RELEASE)~/worker-$* ($(VERSION)-$(RELEASE)~/" \
		-e "s#%%CODENAME%%#$(CODENAME)#g" \
		> $@/$(SRCDIR)/debian/changelog
else
	cat ../../build/worker-$(MODULE_SUFFIX_$*).deb-changelog | sed \
		-e "s#%%CODENAME%%#$(CODENAME)#g" \
		> $@/$(SRCDIR)/debian/changelog
endif
	if [ -f debian.module/copyright.worker-$(MODULE_SUFFIX_$*) ]; then \
		cp debian.module/copyright.worker-$(MODULE_SUFFIX_$*) debuild-$*/$(SRCDIR)/debian/copyright ; \
	else \
		cp debian/copyright debuild-$*/$(SRCDIR)/debian/ ; \
	fi
	@{ \
	set -e ; \
	for src in $(MODULE_SOURCES_$*); do \
		cp debian.module/$${src} $@/$(SRCDIR)/debian/ ; \
	done ; \
	definitions=`echo "$$MODULE_DEFINITIONS_$*" | sed -e ':a' -e 'N' -e '$$!ba' -e "s/\n/\$$CR/g"` ; \
	prebuild=`echo "$$MODULE_PREBUILD_$*" | sed -e ':a' -e 'N' -e '$$!ba' -e "s/\n/\$$CR/g"` ; \
	preinstall=`echo "$$MODULE_PREINSTALL_$*" | sed -e ':a' -e 'N' -e '$$!ba' -e "s/\n/\$$CR/g"` ; \
	postinstall=`echo "$$MODULE_POSTINSTALL_$*" | sed -e ':a' -e 'N' -e '$$!ba' -e "s/\n/\$$CR/g"` ; \
	post=`echo "$$MODULE_POST_$*" | sed -e ':a' -e 'N' -e '$$!ba' -e "s/\n/\$$CR/g"` ; \
	cat debian.module/$(if $(MODULE_NOARCH_$*),control-noarch.in,control.in) | sed \
                -e "s#%%NAME%%#worker-$(MODULE_SUFFIX_$*)#g" \
                -e "s#%%SUMMARY%%#$(MODULE_SUMMARY_$*)#g" \
                -e "s#%%CODENAME%%#$(CODENAME)#g" \
                -e "s#%%WORKER_VERSION%%#$(VERSION)#g" \
                -e "s#%%WORKER_RELEASE%%#$(RELEASE)#g" \
                -e "s#%%VERSION%%#$(MODULE_VERSION_$*)#g" \
                -e "s#%%RELEASE%%#$(MODULE_RELEASE_$*)#g" \
                -e "s#%%PACKAGE_VENDOR%%#$(PACKAGE_VENDOR)#g" \
                -e "s#%%MODULE_BUILD_DEPENDS%%#$(MODULE_BUILD_DEPENDS_$*)#g" \
                -e "s#%%MODULE_DEPENDS%%#$(MODULE_DEPENDS_$*)#g" \
        > $@/$(SRCDIR)/debian/control ; \
        cat debian.module/$(if $(MODULE_NOARCH_$*),rules-noarch.in,rules.in) | sed \
                -e "s#%%NAME%%#worker-$(MODULE_SUFFIX_$*)#g" \
                -e "s#%%CODENAME%%#$(CODENAME)#g" \
                -e "s#%%WORKER_VERSION%%#$(VERSION)#g" \
                -e "s#%%WORKER_RELEASE%%#$(RELEASE)#g" \
                -e "s#%%CONFIGURE_ARGS%%#$(CONFIGURE_ARGS_COMMON)#g" \
                -e "s#%%MODULE_CONFARGS%%#$(MODULE_CONFARGS_$*)#g" \
                -e "s#%%MODULE_MAKEARGS%%#$(MODULE_MAKEARGS_$*)#g" \
                -e "s#%%MODULE_INSTARGS%%#$(MODULE_INSTARGS_$*)#g" \
                -e "s#%%MODULE_DEFINITIONS%%#$${definitions}#g" \
                -e "s#%%MODULE_PREBUILD%%#$${prebuild}#g" \
                -e "s#%%MODULE_PREINSTALL%%#$${preinstall}#g" \
                -e "s#%%MODULE_POSTINSTALL%%#$${postinstall}#g" \
        > $@/$(SRCDIR)/debian/rules ; \
        cat debian.module/preinst.in | sed \
                -e "s#%%MODULE_POST%%#$$post#g" \
        > $@/$(SRCDIR)/debian/preinst ; \
        chmod +x $@/$(SRCDIR)/debian/rules ; \
	}

worker-%: check-build-depends-% | debuild-%
	@echo "===> Building $@ package"
	cd debuild-$*/$(SRCDIR) && debuild -us -uc
	mkdir -p debs
	find debuild-$*/ -maxdepth 1 -type f -exec cp {} debs/ \;
	ln -s debuild-$*/$(SRCDIR)/build $@

test: worker modules
	@{ \
	for so in `find debuild-*/worker-$(VERSION)/debian/build-worker/ -type f -name "*.so"`; do \
		soname=`basename $${so}` ; \
		test -h debuild/worker-$(VERSION)/debian/build-worker/build/$${soname} || \
		ln -fs `pwd`/$${so} debuild/worker-$(VERSION)/debian/build-worker/build/$${soname} ; \
	done ; \
	( cd debuild/worker-$(VERSION)/debian/build-worker && env python3 -m pytest --user=nobody $(PYTEST_ARGS) ) ; \
	}

test-debug: worker modules
	@{ \
	for so in `find debuild-*/worker-$(VERSION)/debian/build-worker-debug/ -type f -name "*.so"`; do \
		soname=`basename $${so}` ; \
		test -h debuild/worker-$(VERSION)/debian/build-worker-debug/build/$${soname} || \
		ln -fs `pwd`/$${so} debuild/worker-$(VERSION)/debian/build-worker-debug/build/$${soname} ; \
	done ; \
	( cd debuild/worker-$(VERSION)/debian/build-worker-debug && env python3 -m pytest --user=nobody $(PYTEST_ARGS) ) ; \
	}

clean:
	rm -rf debuild debuild-* debs ../../build
	rm -f check-build-depends-*
	find . -maxdepth 1 -type l -delete

.PHONY: default all modules test test-debug clean

.SECONDARY: $(addprefix check-build-depends-, $(MODULES)) $(addprefix debuild-, $(MODULES))
