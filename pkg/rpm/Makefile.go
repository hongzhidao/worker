MODULES+=		go
MODULE_SUFFIX_go=	go

MODULE_SUMMARY_go=	Go module for Worker

MODULE_VERSION_go=	$(VERSION)
MODULE_RELEASE_go=	1

MODULE_CONFARGS_go=	go --go-path=%{gopath}
MODULE_MAKEARGS_go=	go
MODULE_INSTARGS_go=	go-install-src

MODULE_SOURCES_go=	worker.example-go-app \
			worker.example-go-config

ifeq ($(OSVER), centos6)
BUILD_DEPENDS_go=	epel-release golang
else ifneq (,$(findstring $(OSVER),opensuse-leap opensuse-tumbleweed))
BUILD_DEPENDS_go=	go1.9
else
BUILD_DEPENDS_go=	golang
endif

BUILD_DEPENDS+=		$(BUILD_DEPENDS_go)

ifneq (,$(findstring $(OSVER),opensuse-leap opensuse-tumbleweed))
define MODULE_DEFINITIONS_go
BuildArch: noarch
Requires: worker-devel == $(VERSION)-$(RELEASE)%{?dist}
BuildRequires: $(BUILD_DEPENDS_go)
%define gopath /usr/share/go/contrib
endef
else
define MODULE_DEFINITIONS_go
BuildArch: noarch
Requires: worker-devel == $(VERSION)-$(RELEASE)%{?dist}
BuildRequires: $(BUILD_DEPENDS_go)
endef
endif
export MODULE_DEFINITIONS_go

define MODULE_PREINSTALL_go
QA_SKIP_BUILD_ROOT=1
export QA_SKIP_BUILD_ROOT

%{__mkdir} -p %{buildroot}%{_datadir}/doc/worker-go/examples/go-app
%{__install} -m 644 -p %{SOURCE100} \
    %{buildroot}%{_datadir}/doc/worker-go/examples/go-app/let-my-people.go
%{__install} -m 644 -p %{SOURCE101} \
    %{buildroot}%{_datadir}/doc/worker-go/examples/worker.config
endef
export MODULE_PREINSTALL_go

define MODULE_FILES_go
%dir %{gopath}/src/github.com/hongzhidao/worker/go
%{gopath}/src/github.com/hongzhidao/worker/go/*
endef
export MODULE_FILES_go

define MODULE_POST_go
cat <<BANNER
----------------------------------------------------------------------

The $(MODULE_SUMMARY_go) has been installed.

To check the sample app, run these commands:

 GOPATH=%{gopath} go build -o /tmp/go-app /usr/share/doc/worker-go/examples/go-app/let-my-people.go
 sudo service worker start
 cd /usr/share/doc/%{name}/examples
 sudo curl -X PUT --data-binary @worker.config --unix-socket /var/run/worker/control.sock http://localhost/config
 curl http://localhost:8500/

Online documentation is available at https://github.com/hongzhidao/worker

----------------------------------------------------------------------
BANNER
endef
export MODULE_POST_go
