MODULES+=		perl
MODULE_SUFFIX_perl=	perl

MODULE_SUMMARY_perl=	Perl module for Worker

MODULE_VERSION_perl=	$(VERSION)
MODULE_RELEASE_perl=	1

MODULE_CONFARGS_perl=	perl
MODULE_MAKEARGS_perl=	perl
MODULE_INSTARGS_perl=	perl-install

MODULE_SOURCES_perl=	worker.example-perl-app \
			worker.example-perl-config

ifneq (,$(findstring $(OSVER),opensuse-leap opensuse-tumbleweed sles))
BUILD_DEPENDS_perl=	perl
else
BUILD_DEPENDS_perl=	perl-devel perl-libs perl-ExtUtils-Embed
endif

BUILD_DEPENDS+=		$(BUILD_DEPENDS_perl)

define MODULE_DEFINITIONS_perl
BuildRequires: $(BUILD_DEPENDS_perl)
endef
export MODULE_DEFINITIONS_perl

define MODULE_PREINSTALL_perl
%{__mkdir} -p %{buildroot}%{_datadir}/doc/worker-perl/examples/perl-app
%{__install} -m 644 -p %{SOURCE100} \
    %{buildroot}%{_datadir}/doc/worker-perl/examples/perl-app/index.pl
%{__install} -m 644 -p %{SOURCE101} \
    %{buildroot}%{_datadir}/doc/worker-perl/examples/worker.config
endef
export MODULE_PREINSTALL_perl

define MODULE_FILES_perl
%{_libdir}/worker/modules/*
%{_libdir}/worker/debug-modules/*
endef
export MODULE_FILES_perl

define MODULE_POST_perl
cat <<BANNER
----------------------------------------------------------------------

The $(MODULE_SUMMARY_perl) has been installed.

To check out the sample app, run these commands:

 sudo service worker start
 cd /usr/share/doc/%{name}/examples
 sudo curl -X PUT --data-binary @worker.config --unix-socket /var/run/worker/control.sock http://localhost/config
 curl http://localhost:8600/

Online documentation is available at https://github.com/hongzhidao/worker

----------------------------------------------------------------------
BANNER
endef
export MODULE_POST_perl
