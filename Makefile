default: build publish

build:
	uv build

publish:
	uv publish

clean:
	rm -rf dist