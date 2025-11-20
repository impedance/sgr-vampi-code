all: clean format sdist
	ls -lah dist

wheel:
	pipx run build --wheel .

whl_file = $(shell ls dist/*.whl)

install: clean wheel
	pip3 install $(whl_file) --user

test:
	uv run pytest -q

format:
	pre-commit run --all-files

clean:
	rm -rf build
	rm -rf *.egg-info
	rm -rf dist
	pip3 uninstall sgr-deep-research UNKNOWN -y
