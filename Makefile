.PHONY: all test test-python test-runtime runtime smoke clean

all: test

test: test-python test-runtime

test-python:
	PYTHONPATH=python python3 -m unittest discover -s tests/python -v

test-runtime:
	$(MAKE) -C tests/c test

runtime:
	$(MAKE) -f mk/runtime-library.mk all

smoke:
	$(MAKE) -C tests/c -f wswan-smoke.mk all
	$(MAKE) -C tests/c -f wswan-sram-smoke.mk all

clean:
	$(MAKE) -C tests/c clean
	$(MAKE) -C tests/c -f wswan-smoke.mk clean
	$(MAKE) -C tests/c -f wswan-sram-smoke.mk clean
	$(MAKE) -f mk/runtime-library.mk clean
	rm -rf build dist python/*.egg-info python/*/__pycache__ tests/python/__pycache__
