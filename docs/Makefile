#!/usr/bin/make

DEST=	../build
XSLS?=	xslscript.pl

PACKAGES=	worker 							\
		worker-php 						\
		worker-python worker-python2.7 worker-python3.4		\
		worker-python3.5 worker-python3.6 worker-python3.7		\
		worker-python3.8 worker-python3.9				\
		worker-python3.10 worker-python3.13			\
		worker-go worker-go1.7 worker-go1.8 worker-go1.9 worker-go1.10	\
		worker-go1.12 worker-go1.13					\
		worker-ruby

CURDATE:=$(shell date +"%Y-%m-%d")
CURTIME:=$(shell date +"%H:%M:%S %z")


all:		changes changelogs

changes:	$(DEST)/CHANGES

changelogs:	$(addsuffix .rpm-changelog, $(addprefix $(DEST)/, $(PACKAGES))) \
		$(addsuffix .deb-changelog, $(addprefix $(DEST)/, $(PACKAGES)))

$(DEST)/CHANGES:		changes.dtd				\
				changes.xml				\
				change_log_conf.xml			\
				changes.xslt

	mkdir -p $(DEST)

	xmllint --noout --valid changes.xml
	xsltproc --stringparam format generic				\
		--stringparam curdate '$(CURDATE)'			\
		--stringparam curtime '$(CURTIME)'			\
		-o $@ changes.xslt changes.xml

$(DEST)/%.rpm-changelog:	changes.dtd 				\
				changes.xml 				\
				change_log_conf.xml 			\
				changes.xslt
	mkdir -p $(DEST)
	xmllint --noout --valid changes.xml
	xsltproc --stringparam pkgname $* --stringparam format rpm	\
		--stringparam curdate '$(CURDATE)'			\
		--stringparam curtime '$(CURTIME)'			\
		-o $@ changes.xslt changes.xml

$(DEST)/%.deb-changelog:	changes.dtd 				\
				changes.xml 				\
				change_log_conf.xml 			\
				changes.xslt
	mkdir -p $(DEST)
	xmllint --noout --valid changes.xml
	xsltproc --stringparam pkgname $* --stringparam format deb	\
		--stringparam curdate '$(CURDATE)'			\
		--stringparam curtime '$(CURTIME)'			\
		-o $@ changes.xslt changes.xml

changes.xslt:	changes.xsls
	$(XSLS) -o $@ $<

clean:
	rm -rf $(DEST)
