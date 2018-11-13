# Some simple testing tasks (sorry, UNIX only).

FLAGS=


flake:
#	python setup.py check -rms
	flake8 sockjs tests examples
	if python -c "import sys; sys.exit(sys.version_info<(3,6))"; then \
		black --check sockjs tests setup.py; \
	fi

fmt:
	black sockjs tests setup.py


develop:
	python setup.py develop

test: flake develop
	pytest $(FLAGS) ./tests/

vtest: flake develop
	pytest -s -v $(FLAGS) ./tests/

cov cover coverage: flake develop
	@py.test --cov=sockjs --cov-report=term --cov-report=html tests
	@echo "open file://`pwd`/coverage/index.html"

clean:
	rm -rf `find . -name __pycache__`
	rm -f `find . -type f -name '*.py[co]' `
	rm -f `find . -type f -name '*~' `
	rm -f `find . -type f -name '.*~' `
	rm -f `find . -type f -name '@*' `
	rm -f `find . -type f -name '#*#' `
	rm -f `find . -type f -name '*.orig' `
	rm -f `find . -type f -name '*.rej' `
	rm -f .coverage
	rm -rf coverage
	rm -rf build
	rm -rf cover
	make -C docs clean
	python setup.py clean

doc:
	make -C docs html
	@echo "open file://`pwd`/docs/_build/html/index.html"

.PHONY: all build venv flake test vtest testloop cov clean doc
