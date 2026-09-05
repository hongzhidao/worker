MODULES+=		go
MODULE_SUFFIX_go=	go

MODULE_SUMMARY_go=	Go module for Worker

MODULE_VERSION_go=	$(VERSION)
MODULE_RELEASE_go=	1

MODULE_CONFARGS_go=	go --go-path=/usr/share/gocode
MODULE_MAKEARGS_go=	go
MODULE_INSTARGS_go=	go-install-src

MODULE_SOURCES_go=	worker.example-go-app \
			worker.example-go-config

BUILD_DEPENDS_go=	golang
BUILD_DEPENDS+=		$(BUILD_DEPENDS_go)

MODULE_BUILD_DEPENDS_go=,golang
MODULE_DEPENDS_go=,golang,worker-dev (= $(VERSION)-$(RELEASE)~$(CODENAME))

MODULE_NOARCH_go=	true

define MODULE_PREINSTALL_go
	mkdir -p debian/worker-go/usr/share/doc/worker-go/examples/go-app
	install -m 644 -p debian/worker.example-go-app debian/worker-go/usr/share/doc/worker-go/examples/go-app/let-my-people.go
	install -m 644 -p debian/worker.example-go-config debian/worker-go/usr/share/doc/worker-go/examples/worker.config
endef
export MODULE_PREINSTALL_go

define MODULE_POST_go
cat <<BANNER
----------------------------------------------------------------------

The $(MODULE_SUMMARY_go) has been installed.

To check out the sample app, run these commands:

 GOPATH=/usr/share/gocode go build -o /tmp/go-app /usr/share/doc/worker-$(MODULE_SUFFIX_go)/examples/go-app/let-my-people.go
 sudo service worker restart
 cd /usr/share/doc/worker-$(MODULE_SUFFIX_go)/examples
 sudo curl -X PUT --data-binary @worker.config --unix-socket /var/run/control.worker.sock http://localhost/config
 curl http://localhost:8500/

Online documentation is available at https://github.com/hongzhidao/worker

----------------------------------------------------------------------
BANNER
endef
export MODULE_POST_go
