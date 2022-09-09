#################
# Makefile to automate workflows used to instantiate Go-based dev environment
# and perform tasks required throughout the development process
#
# needs 
# - docker-ce
# - containerlab
#################

APPNAME = support
CLASSNAME = Support

LABFILE = dev.clab.yml
TESTLABFILE = test.clab.yml
BIN_DIR = $$(pwd)/build
BINARY = $$(pwd)/build/$(APPNAME)

# absolute path of a directory that hosts makefile
ROOT_DIR:=$(shell dirname $(realpath $(firstword $(MAKEFILE_LIST))))


# when make is called with `make cleanup=1 some-target` the CLEANUP var will be set to `--cleanup`
# this is used in clab destroy commands to remove the clab-dev lab directory 
CLEANUP=
ifdef cleanup
	CLEANUP := --cleanup
endif

# create dev .gitignore
.ONESHELL:
.gitignore:
	cat <<- EOF > $@
	/*
	!.gitignore
	!.gen
	!LICENSE
	!Makefile
	!README.md
	!requirements.txt
	!.vscode
	.vscode/*
	!.vscode/tasks.json
	EOF

################### Help ###################
# Targets with ## are displayed in the help
help : Makefile
	@echo "Makefile to automate workflows used to instantiate Go-based dev environment"
	@echo "and perform tasks required throughout the development process"
	@echo
	@echo "Useful targets:"
	@sed -n 's/^## //p' Makefile

################### Python dependencies #################
## update-app            :      use when new dependencies are introduced and you need to re-create the venv
update-app: venv remote-venv restart-app

# create venv and install dependencies
venv:
	python3 -m venv .venv
	. .venv/bin/activate && \
	pip3 install -U pip wheel && \
	pip3 install -r requirements.txt

# python wheels to install same deps on remote venv built with srlinux image to guarantee compatibility with NOS
.PHONY: wheels
wheels:
	docker run --rm -v $$(pwd):/work -w /work --entrypoint 'bash' ghcr.io/nokia/srlinux:latest -c \
	"sudo python3 -m pip install -U -qqq pip wheel && sudo python3 -m pip wheel pip wheel -r requirements.txt --no-cache -qqq --wheel-dir $(APPNAME)/wheels"

# setting up venv on srl1/srl2 containers
remote-venv: wheels
	cd lab; \
	sudo clab exec -t $(LABFILE) --label clab-node-kind=srl --cmd \
	"bash -c \"sudo python3 -m venv /opt/${APPNAME}/.venv && source /opt/${APPNAME}/.venv/bin/activate && python3 -m pip install -qqq --no-cache --no-index /opt/${APPNAME}/wheels/pip* && python3 -m pip install -qqq --no-cache --no-index /opt/${APPNAME}/wheels/*\""

################### Containerlab targets ###################

## redeploy-all          :      restart lab
redeploy-all: redeploy-lab deploy_app

# Alias for redeploy-all
deploy-all: redeploy-all

# Redeploy lab
redeploy-lab: destroy-lab deploy-lab

# Launch lab
deploy-lab:
	mkdir -p logs/srl1 logs/srl2
	cd lab; \
	sudo clab dep -t $(LABFILE)

## destroy-lab           :      destroy lab
destroy-lab:
	cd lab; \
	sudo clab des -t $(LABFILE) $(CLEANUP); \
	sudo rm -f .*.clab.* \
	sudo rm -rf ../logs/*

################### Targets that interact with SR Linux ###################

# Deploy app on srl1/srl2
deploy_app: remote-venv update-appmgr-dir restart-app_mgr

## show-app-status       :      show agent status on all srl nodes
show-app-status:
	cd lab; \
	sudo clab exec -t $(LABFILE) --label clab-node-kind=srl --cmd 'sr_cli "show system application $(APPNAME)"'

# Reload the app-mgr on all srl nodes
reload-app_mgr:
	cd lab; \
	sudo clab exec -t $(LABFILE) --label clab-node-kind=srl --cmd 'sr_cli "tools system app-management application app_mgr reload"'

## restart-app	         :      restart agent on all srl nodes
restart-app:
	cd lab; \
	sudo clab exec -t $(LABFILE) --label clab-node-kind=srl --cmd 'sr_cli "tools system app-management application $(APPNAME) restart"'

# Update the app-mgr directory on all srl nodes to include the agent's yang model
update-appmgr-dir:
	cd lab; \
	sudo clab exec -t $(LABFILE) --label clab-node-kind=srl --cmd 'sudo bash -c "mkdir -p /etc/opt/srlinux/appmgr && cp /tmp/$(APPNAME).yml /etc/opt/srlinux/appmgr/$(APPNAME).yml"'

# Alias for reload-app_mgr
restart-app_mgr: reload-app_mgr

################### Build Targets ###################
## build-app             :      build agent binary
build-app: build-venv rpm


#Generate the venv used in the rpm
build-venv: wheels
	mkdir ${BIN_DIR}; \
	cd ${APPNAME}; \
	docker run --rm -v $$(pwd):/opt/${APPNAME} -w /opt/${APPNAME} --entrypoint 'bash' ghcr.io/nokia/srlinux:latest -c "sudo python3 -m venv .venv && source .venv/bin/activate && pip3 install --no-cache --no-index wheels/pip* && pip3 install --no-cache --no-index wheels/*"

# Build the rpm
rpm:
	docker run --rm -v $$(pwd):/tmp -w /tmp goreleaser/nfpm package \
	--config /tmp/nfpm.yml \
	--target /tmp/build \
	--packager rpm

################### Clean Targets ###################
## clean 		         :      remove all generated files
clean: destroy-lab destroy-test-lab remove-files .gitignore

remove-files:
	cd tests; \
	bash -O extglob -c 'sudo rm -r !(Dockerfile|requirements.txt)'; \
	cd ..; \
	sudo rm -rf logs build ${APPNAME} lab yang *.yml .venv *.py .gitignore wheels


################### Test Targets ###################
## automation-test       :      run tests in non-interactive mode (for CI)
automation-test: build-automated-test redeploy-all redeploy-test-lab
	docker exec -t clab-${APPNAME}-test-test1 robot -b/mnt/debug.txt test.robot

## test 		         :      run tests in interactive mode (for local dev), requires the lab and test lab to be deployed
test:
	docker exec -ti clab-${APPNAME}-test-test1 robot -b/mnt/debug.txt test.robot

## redeploy-all-and-test :    redeploy lab, redeploy test lab, run tests
redeploy-all-and-test: redeploy-all redeploy-test-lab
	docker exec -ti clab-${APPNAME}-test-test1 robot -b/mnt/debug.txt test.robot


######### Test lab deploy/destroy
redeploy-test-lab: destroy-test-lab deploy-test-lab

build-automated-test:
	cd tests;\ 
	docker build -t ${APPNAME}-tests .

deploy-test-lab:
	cd tests/lab;\
	sudo clab dep -t $(TESTLABFILE)

## destroy-test-lab      :      destroy test lab
destroy-test-lab:
	cd tests/lab;\
	sudo clab des -t $(TESTLABFILE) $(CLEANUP)

################### Lint Targets ###################
## lint                  :      run all linters (lint-yang, lint-python, lint-yaml can be used to run individual linters)
lint: lint-yang lint-yaml lint-python

## lint-yang             :      run yang linter
lint-yang:
	docker run --rm -v $$(pwd):/work ghcr.io/hellt/yanglint ${APPNAME}/yang/*.yang

## lint-yaml             :      run yaml linter
lint-yaml:
	docker run --rm -v $$(pwd):/data cytopia/yamllint -d relaxed .

## lint-python           :      run python linter (black)
lint-python:
	docker run --rm --volume $$(pwd)/${APPNAME}/:/src --workdir /src pyfound/black:latest_release black --check .


# lint an app and restart app_mgr without redeploying the lab
lint-restart: lint restart-app

################### Misc Targets ###################

## destroy-all-labs      :      destroy all labs
destroy-all-labs: destroy-lab destroy-test-lab

## generate-agent-files  :      generate new agent files from templates
generate-agent-files: venv
	mkdir -p logs/srl1 logs/srl2 build lab tests/lab $(APPNAME) $(APPNAME)/yang $(APPNAME)/wheels
	docker run --rm -e APPNAME=${APPNAME} -e CLASSNAME=${CLASSNAME} -v $$(pwd):/tmp hairyhenderson/gomplate:stable --input-dir /tmp/.gen --output-map='/tmp/{{ .in | strings.TrimSuffix ".tpl" }}'
	sudo chown -R $$(id -u):$$(id -g) .
	mv agent.yang ${APPNAME}/yang/${APPNAME}.yang
	mv agent-config.yml ${APPNAME}.yml
	mv dev.clab.yml lab/
	mv tests/$(TESTLABFILE) tests/lab
	mv main.py run.sh ${APPNAME}/
	mv base_agent.py ${APPNAME}/
	mv ${APPNAME}_agent.py ${APPNAME}/
	sed -i 's/${APPNAME}/${APPNAME}/g' Makefile
	cp .gen/.gitignore .