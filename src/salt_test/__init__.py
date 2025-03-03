"""Run Salt Test Suite by test group.

Test groups are:
- unit
- functional
- integration
- scenarios

Tests can be ignored or skipped by means of a skiplist TOML file. Ignored test files are
not collected by pytest. Skipped tests are collected but not executed by pytest. It's
recommended to skip tests only when needed and select them individually.

A config can be used to set arguments to pass to pytest, as well as to define additional
test groups.

This pytest wrapper can execute different pytest Python flavors, including a special
"bundle" flavor. The Python flavor for pytest corresponds to the Python flavor of the Salt
test suite.
"""

import contextlib
import io
import os
import re
import subprocess
import sys
import typing
from urllib.error import HTTPError
import urllib.request
from argparse import ArgumentParser

try:
    import tomllib  # available in Python 3.11+

    toml = tomllib
except ImportError:
    import tomli

    toml = tomli


DEFAULT_CONFIG = {
    "unit": {"dirs": ["tests/unit/", "tests/pytests/unit/"], "pytest_args": []},
    "functional": {"dirs": ["tests/pytests/functional"], "pytest_args": []},
    "integration": {
        "dirs": ["tests/integration/", "tests/pytests/integration/"],
        "pytest_args": [],
    },
    "scenarios": {"dirs": ["tests/pytests/scenarios/"], "pytest_args": ["--slow"]},
}


VENV_ENV_PARAMS = {
    "CPATH",
    "LD_LIBRARY_PATH",
    "PYTHONHOME",
    "PYTHONSTARTUP",
    "SALT_CONFIG_DIR",
    "VENV_PIP_TARGET",
    "VIRTUAL_ENV",
}


def parse_skiplist(
    file: typing.BinaryIO, groups: typing.Iterable[str]
) -> typing.Dict[str, typing.List[str]]:
    """Reads skiplist and returns a dictionary.

    The dictionary fills in missing test groups to guarantee [] access.
    """
    raw_dict = toml.load(file)
    # raw_dict: {"ignore": {$group: [...]}, "skip": { $group: [...]}}
    ignored_files = raw_dict.get("ignore", {})
    skipped_tests = raw_dict.get("skip", {})

    # skiplist: {$group: {"ignore": [...], "skip": [...]}}
    skiplist = {}
    for group in groups:
        skiplist[group] = {
            "ignore": ignored_files.get(group, []),
            "skip": skipped_tests.get(group, []),
        }
    return skiplist


def parse_config(file: typing.BinaryIO):
    """Reads the config and returns a dictionary.

    The dictionary fills in missing test groups to guarantee [] access.
    """
    raw_dict = toml.load(file)
    # raw_dict: {groups: {$group: {"dirs": [...], "pytest_args": [...]}

    config = {}
    for group in raw_dict["groups"]:
        config[group]["dirs"] = group["dirs"]
        config[group]["pytest_args"] = group.get("pytest_args", [])

    return config


def resolve_testsuite_flavor(flavor: str) -> str:
    """Resolve flavor if it's a capability.

    Flavor could be "python3" without any installed package being called python3. This is
    the case for openSUSE Tumbleweed, where a versioned flavor provides the RPM symbol
    "python3".
    """
    if flavor == "python3":
        completed = subprocess.run(
            ["rpm", "-q", "--whatprovides", "python3-salt-testsuite"],
            stdout=subprocess.PIPE,
            encoding="utf-8",
            check=False,
        )
        if completed.returncode == 0:
            return completed.stdout.split("-")[0]
    return flavor


def flavor_filelist(flavor: str) -> typing.List[str]:
    """Return filelist of a given flavor package (rpm or deb)."""
    if flavor == "bundle":
        pkg = "venv-salt-minion-testsuite"
    else:
        pkg = f"{flavor}-salt-testsuite"

    rpm_cmd = ["rpm", "-q", "-l", pkg]
    dpkg_cmd = ["dpkg", "-L", pkg]
    filelist = []
    for cmd in (rpm_cmd, dpkg_cmd):
        with contextlib.suppress(FileNotFoundError):
            completed = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                encoding="utf-8",
                check=False,
            )
            if completed.returncode == 0:
                filelist = completed.stdout.split()
                break

    return filelist


def find_testsuite_root(flavor: str) -> str:
    """Find root of the Salt test suite for the given flavor."""
    pkg_files = flavor_filelist(flavor)
    root = None
    for file in pkg_files:
        match = re.match(r"(/usr/lib/.*/site-packages/salt-testsuite)", file)
        if match:
            root = match.group(0)
            break

    if root is None:
        raise RuntimeError(f'Test suite for flavor "{flavor}" not installed.')

    return root


def flavor_pytest_cmd(flavor: str) -> typing.List[str]:
    """Compute pytest command for a given Python flavor.

    Different flavors can be co-installed, we should use the same Python flavor
    for running `pytest` that is being tested.
    """
    if flavor == "bundle":
        return ["/usr/lib/venv-salt-minion/bin/pytest"]
    else:
        match = re.match(r"python(\d+)$", flavor)
        if match is not None:
            ver = match.groups()[0]
            if len(ver) == 1:
                return ["/usr/bin/python3", "-m", "pytest"]
            else:
                return [f"/usr/bin/pytest-{ver[0]}.{ver[1:]}"]
    return ["/usr/bin/pytest"]


def pytest_cmd(
    group: str,
    skiplist: dict,
    config: dict,
    extra_args: typing.List[str],
    flavor="bundle",
):
    """Compose the correct command for pytest.

    The correct pytest command executes the test suite with the Python flavor
    corresponding to the package flavor. It deselects and ignores the tests
    according to the skiplist, and adds other cli args according to the config
    and CLI invocation.

    Args:
      group: The group of tests to execute, e.g. 'unit', or 'integration', ...
      skiplist: Dictionary that specifies files to ignore and tests to skip for the given
        'group'.
      config: Dictionary that specifies "pytest_args" for the given 'group'.
      extra_args: Arguments to pass through to pytest. The are merged with the args from 'config'.
      flavor: Used to determine the right pytest command, based on the Python flavor.
    """
    cmd = flavor_pytest_cmd(flavor)
    args = config[group]["pytest_args"] + extra_args
    cmd.extend(args)
    for skipped_file in skiplist[group]["ignore"]:
        cmd.extend(["--ignore", skipped_file])
    for skipped_test in skiplist[group]["skip"]:
        cmd.extend(["--deselect", skipped_test])

    # test dirs should follow CLI flags
    cmd.extend(config[group]["dirs"])

    return cmd


def prepare_argparser() -> ArgumentParser:
    parser = ArgumentParser("salt-test")
    parser.add_argument(
        "--skiplist",
        "-s",
        type=str,
        help="Specify location of skiplist (TOML). Can be a HTTP URL.",
    )
    parser.add_argument(
        "--config",
        "-c",
        type=str,
        help="Specify location of config (TOML). Can be a HTTP URL.",
    )
    parser.add_argument(
        "--package-flavor",
        "-f",
        default="bundle",
        help="Used to determine the Python environment that includes dependencies, e.g. 'bundle', 'python3', 'python311', ...",
    )
    parser.add_argument(
        "--directory",
        "-d",
        type=str,
        help="Root of test suite. Can be used to override the test suite root computed based on the --package-flavor.",
    )
    parser.add_argument("test_group", help="Group of tests to run.")
    parser.add_argument(
        "pytest_args",
        nargs="*",
        help="Specify extra arguments for pytest, separated from"
        " 'test_group' by a single --. They are merged with"
        " pytest_args specified in the config.",
    )
    return parser


def update_env(env: os._Environ, cwd: str, is_classic=False) -> dict:
    """Update PATH and PYTHONPATH env variables.

    PATH is modified to contain bindir as the first entry. This ensures that `pytest` can
    be found.
    PYTHONPATH is set to cwd. This ensures that the correct Salt code is tested.

    Args:
      env: Original environment variables
      cwd: Current working directory, determines where Python finds the Salt code base.
      is_classic: If True, the VENV_ENV_PARAMS environment variables are unset. Default: False
        This is required when the Salt Bundle's salt-test is used with --flavor=classic.
    """
    env_copy = env.copy()
    env_copy["PYTHONPATH"] = cwd
    if is_classic:
        for key in VENV_ENV_PARAMS:
            env_copy.pop(key, None)
    return env_copy


def main():
    parser = prepare_argparser()
    args = parser.parse_args()

    if args.config:
        if args.config.startswith("http"):
            try:
                with urllib.request.urlopen(args.config) as f:
                    config = parse_config(f)
            except HTTPError as e:
                raise AttributeError(f"URL '{args.config}' is not available") from e
        else:
            with open(args.config, "rb") as f:
                config = parse_config(f)
    else:
        config = DEFAULT_CONFIG

    if args.skiplist:
        if args.skiplist.startswith("http"):
            try:
                with urllib.request.urlopen(args.skiplist) as f:
                    skiplist = parse_skiplist(f, config.keys())
            except HTTPError as e:
                raise AttributeError(f"URL '{args.skiplist}' is not available") from e
        else:
            with open(args.skiplist, "rb") as f:
                skiplist = parse_skiplist(f, config.keys())
    else:
        skiplist = parse_skiplist(io.BytesIO(), config.keys())

    if args.package_flavor == "classic":
        args.package_flavor = "python3"

    flavor = resolve_testsuite_flavor(args.package_flavor)

    try:
        testsuite_root = find_testsuite_root(flavor)
    except RuntimeError as e:
        print(e)
        sys.exit(1)

    if args.directory:
        cwd = args.directory
    else:
        cwd = testsuite_root

    env = update_env(os.environ, cwd, args.package_flavor != "bundle")
    cmd = pytest_cmd(
        args.test_group, skiplist, config, args.pytest_args, flavor=args.package_flavor
    )
    print("Running:", " ".join(cmd))
    pytest_retcode = subprocess.run(
        cmd,
        env=env,
        cwd=cwd,
    ).returncode
    sys.exit(pytest_retcode)
