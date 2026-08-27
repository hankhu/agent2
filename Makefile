default: build publish
	rm -rf dist

build:
	uv build

publish:
	uv publish