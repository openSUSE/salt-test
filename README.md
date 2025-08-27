# `salt-test`

`salt-test` is a test suite launcher for Salt's test suite by "test group". It takes a `skiplist` that defines which tests files to ignore and which tests to skip. `salt-test` expects the Salt test suite installed via the `python3-salt-testsuite`/`venv-salt-minion-testsuite` rpms. By default, `venv-salt-minion-testsuite` is used (`--package-flavor bundle`). 

## Usage
The basic usage is `salt-test --skiplist skiplist.toml <test group>`.

For example, to run unit tests with our openSUSE skiplist you can use:
```sh
salt-test --skiplist https://raw.githubusercontent.com/openSUSE/salt-test-skiplist/main/skipped_tests.toml unit
```

Of course, a skiplist can also be a local file:
```sh
salt-test --skiplist skipped.toml unit
```

Extra arguments that are passed through to `pytest` can be specified after the "test group" and the separator`--`. This feature can be used to enable e.g. slow or destructive integration tests:
```sh
salt-test --skiplist skipped.toml integration -- --slow
```

To run the a version of the test suite that's not packaged yet (the test suite package must _still_ be installed to provide dependencies), you can use the `--directory` parameter:
```sh
salt-test --skiplist skipped.toml --directory /code/ functional
```

To test non-bundled Salt versions, use the `--package-flavor` argument, for example:
```sh
# Run tests from the python3-salt-testsuite RPM/deb
salt-test --package-flavor python3 --skiplist skipped.toml unit
# Run tests from the python311-salt-testsuite RPM/deb
salt-test --package-flavor python311 --skiplist skipped.toml integration
# Run tests from the python313-salt-testsuite RPM/deb
salt-test --package-flavor python313 --skiplist skipped.toml functional
```


# Test requirements

- `pytest`
