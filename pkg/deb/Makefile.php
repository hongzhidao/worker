MODULES+=		php
MODULE_SUFFIX_php=	php

MODULE_SUMMARY_php=	PHP module for Worker

MODULE_VERSION_php=	$(VERSION)
MODULE_RELEASE_php=	1

MODULE_CONFARGS_php=	php
MODULE_MAKEARGS_php=	php
MODULE_INSTARGS_php=	php-install

MODULE_SOURCES_php=	worker.example-php-app \
			worker.example-php-config

ifneq (,$(findstring $(CODENAME),trusty jessie))
BUILD_DEPENDS_php=	php5-dev libphp5-embed
MODULE_BUILD_DEPENDS_php=,php5-dev,libphp5-embed
MODULE_DEPENDS_php=,libphp5-embed
else
BUILD_DEPENDS_php=	php-dev libphp-embed
MODULE_BUILD_DEPENDS_php=,php-dev,libphp-embed
MODULE_DEPENDS_php=,libphp-embed
endif

BUILD_DEPENDS+=		$(BUILD_DEPENDS_php)

define MODULE_PREINSTALL_php
	mkdir -p debian/worker-php/usr/share/doc/worker-php/examples/phpinfo-app
	install -m 644 -p debian/worker.example-php-app debian/worker-php/usr/share/doc/worker-php/examples/phpinfo-app/index.php
	install -m 644 -p debian/worker.example-php-config debian/worker-php/usr/share/doc/worker-php/examples/worker.config
endef
export MODULE_PREINSTALL_php

define MODULE_POST_php
cat <<BANNER
----------------------------------------------------------------------

The $(MODULE_SUMMARY_php) has been installed.

To check out the sample app, run these commands:

 sudo service worker restart
 cd /usr/share/doc/worker-$(MODULE_SUFFIX_php)/examples
 sudo curl -X PUT --data-binary @worker.config --unix-socket /var/run/control.worker.sock http://localhost/config
 curl http://localhost:8300/

Online documentation is available at https://github.com/hongzhidao/worker

----------------------------------------------------------------------
BANNER
endef
export MODULE_POST_php
