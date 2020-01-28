
# make test <target>: run a specified test
# make cover: run all tests and generate code coverage

ifeq (test,$(firstword $(MAKECMDGOALS)))
  # use the rest as arguments for "test"
  RUN_ARGS := $(wordlist 2,$(words $(MAKECMDGOALS)),$(MAKECMDGOALS))
  # ...and turn them into do-nothing targets
  $(eval $(RUN_ARGS):;@:)
endif

.PHONY: test
test:
	coverage run -m tests.$(RUN_ARGS)_test
	coverage html --omit "venv/*,tests/*"
	#open htmlcov/index.html

.PHONY: cover
cover:
	coverage run -m tests
	coverage html --omit "venv/*,*_test.py,tests/*"
	#open htmlcov/index.html

.PHONY: demo
demo:
	python -m daedalus build_html ./examples/minesweeper.js ./docs/index.html

.PHONY: serve_demo
serve_demo:
	python -m daedalus serve ./examples/minesweeper.js