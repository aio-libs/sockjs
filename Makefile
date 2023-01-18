# Some simple testing tasks (sorry, UNIX only).

FLAGS=


flake:
	flake8 sockjs tests examples

develop:
	pip install -e .[test]

test: flake develop
	pytest $(FLAGS) ./tests/

vtest: flake develop
	pytest -s -v $(FLAGS) ./tests/

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
	python setup.py clean

.PHONY: all flake test vtest clean
