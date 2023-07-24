
# make test <target>: run a specified test
# make cover: run all tests and generate code coverage
SHELL:=/bin/bash

ifeq (test,$(firstword $(MAKECMDGOALS)))
  # use the rest as arguments for "test"
  RUN_ARGS := $(wordlist 2,$(words $(MAKECMDGOALS)),$(MAKECMDGOALS))
  # ...and turn them into do-nothing targets
  $(eval $(RUN_ARGS):;@:)
endif

.PHONY: test
test:
	coverage run -m tests.$(RUN_ARGS)_test
	coverage html --omit "*venv*,*_test.py,tests/*"
	@#open htmlcov/index.html
	@printf "%-60s %10s\n" $(shell grep pc_cov ./htmlcov/*.html | sed 's/<span.*">//' | sed 's=</span>==') | sort -V

.PHONY: cover
cover:
	coverage run -m tests
	coverage html --omit "*venv*,*_test.py,tests/*"
	@#open htmlcov/index.html
	@printf "%-60s %10s\n" $(shell grep pc_cov ./htmlcov/*.html | sed 's/<span.*">//' | sed 's=</span>==') | sort -V

.PHONY: demo
demo:
	python -m daedalus build --minify --sourcemap ./examples/minesweeper.js --webroot="" ./build

.PHONY: serve_demo
serve_demo:
	python -m daedalus serve --minify ./examples/minesweeper.js

.PHONY: serve_test
serve_test:
	python -m daedalus serve daedalus_test