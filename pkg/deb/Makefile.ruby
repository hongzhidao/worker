MODULES+=		ruby
MODULE_SUFFIX_ruby=	ruby

MODULE_SUMMARY_ruby=	Ruby module for Worker

MODULE_VERSION_ruby=	$(VERSION)
MODULE_RELEASE_ruby=	1

MODULE_CONFARGS_ruby=	ruby
MODULE_MAKEARGS_ruby=	ruby
MODULE_INSTARGS_ruby=	ruby-install

MODULE_SOURCES_ruby=	worker.example-ruby-app \
			worker.example-ruby-config

BUILD_DEPENDS_ruby=	ruby-dev ruby-rack
BUILD_DEPENDS+=         $(BUILD_DEPENDS_ruby)

MODULE_BUILD_DEPENDS_ruby=,ruby-dev,ruby-rack

MODULE_DEPENDS_ruby=,ruby-rack

define MODULE_PREINSTALL_ruby
	mkdir -p debian/worker-ruby/usr/share/doc/worker-ruby/examples
	install -m 644 -p debian/worker.example-ruby-app debian/worker-ruby/usr/share/doc/worker-ruby/examples/ruby-app.ru
	install -m 644 -p debian/worker.example-ruby-config debian/worker-ruby/usr/share/doc/worker-ruby/examples/worker.config
endef
export MODULE_PREINSTALL_ruby

define MODULE_POST_ruby
cat <<BANNER
----------------------------------------------------------------------

The $(MODULE_SUMMARY_ruby) has been installed.

To check out the sample app, run these commands:

 sudo service worker restart
 cd /usr/share/doc/worker-$(MODULE_SUFFIX_ruby)/examples
 sudo curl -X PUT --data-binary @worker.config --unix-socket /var/run/control.worker.sock http://localhost/config
 curl http://localhost:8700/

Online documentation is available at https://github.com/hongzhidao/worker

----------------------------------------------------------------------
BANNER
endef
export MODULE_POST_ruby
