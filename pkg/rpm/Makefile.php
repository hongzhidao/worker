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

ifeq ($(OSVER), opensuse-tumbleweed)
BUILD_DEPENDS_php=	php7-devel php7-embed
else
BUILD_DEPENDS_php=	php-devel php-embedded
endif

BUILD_DEPENDS+=		$(BUILD_DEPENDS_php)

define MODULE_PREINSTALL_php
%{__mkdir} -p %{buildroot}%{_datadir}/doc/worker-php/examples/phpinfo-app
%{__install} -m 644 -p %{SOURCE100} \
    %{buildroot}%{_datadir}/doc/worker-php/examples/phpinfo-app/index.php
%{__install} -m 644 -p %{SOURCE101} \
    %{buildroot}%{_datadir}/doc/worker-php/examples/worker.config
endef
export MODULE_PREINSTALL_php

define MODULE_FILES_php
%{_libdir}/worker/modules/*
%{_libdir}/worker/debug-modules/*
endef
export MODULE_FILES_php

define MODULE_POST_php
cat <<BANNER
----------------------------------------------------------------------

The $(MODULE_SUMMARY_php) has been installed.

To check out the sample app, run these commands:

 sudo service worker start
 cd /usr/share/doc/%{name}/examples
 sudo curl -X PUT --data-binary @worker.config --unix-socket /var/run/worker/control.sock http://localhost/config
 curl http://localhost:8300/

Online documentation is available at https://github.com/hongzhidao/worker

----------------------------------------------------------------------
BANNER
endef
export MODULE_POST_php
