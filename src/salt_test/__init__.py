"""Run Salt Test Suite by test group."""

import os
import pathlib
import re
import subprocess
import sys
import typing
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

FLAVOR_RPM = {
    "classic": "python3-salt-testsuite",
    "bundle": "venv-salt-minion-testsuite",
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


def find_testsuite_root(flavor: str) -> str:
    """Find root of test suite based.

    :param flavor: One of "classic", "bundle".
    """

    def _list_files(pkg: str) -> typing.List[str]:
        try:
            cp = subprocess.run(
                ["rpm", "-q", "-l", pkg],
                stdout=subprocess.PIPE,
                encoding="utf-8",
            )
        except FileNotFoundError:
            cp = subprocess.run(
                ["dpkg", "-L", pkg],
                stdout=subprocess.PIPE,
                encoding="utf-8",
            )
        if cp.returncode != 0:
            return []
        return cp.stdout.split()

    pkg = FLAVOR_RPM[flavor]
    pkg_files = _list_files(pkg)
    root = None
    for file in pkg_files:
        match = re.match(r"(/usr/lib/.*/site-packages/salt-testsuite)", file)
        if match:
            root = match.group(0)
            break

    if root is None:
        raise RuntimeError(f'Test suite for flavor "{flavor}" not installed.')

    return root


def testsuite_root_to_bindir(root: str) -> str:
    """Compute /bin from the testsuite root.

    This is needed to use the correct pytest executable.
    """
    p = pathlib.Path(root)
    while p.name != "lib":
        p = p.parent
    # p now ends with /lib, therefore bin is a sibling
    return str(p.parent / "bin")


def pytest_cmd(group: str, skiplist: dict, config: dict, extra_args: typing.List[str]):
    """Compose the correct command args for pytest."""
    cmd = ["pytest"]
    if not extra_args:
        extra_args = config[group]["pytest_args"]
    cmd.extend(extra_args)
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
        required=True,
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
        choices=tuple(FLAVOR_RPM.keys()),
        default="bundle",
        help="Used to determine the Python environment that includes dependencies.",
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
        help="Specify extra arguments for pytest, separated from 'test_group' by a single --.",
    )
    return parser


def update_env(env: os._Environ, bindir: str, cwd: str, is_classic=False) -> dict:
    """Update PATH and PYTHONPATH env variables.

    PATH is modified to contain bindir as the first entry. This ensures that `pytest` can
    be found.
    PYTHONPATH is set to cwd. This ensures that the correct Salt code is tested.

    Args:
      env: Original environment variables
      bindir: Path to a the bin/ directory where pytest is located.
      cwd: Current working directory, determines where Python finds the Salt code base.
      is_classic: If True, the VENV_ENV_PARAMS environment variables are unset. Default: False
        This is required when the Salt Bundle's salt-test is used with --flavor=classic.
    """
    env_copy = env.copy()
    env_copy["PATH"] = f"{bindir}:{env_copy['PATH']}"
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
            with urllib.request.urlopen(args.config) as f:
                config = parse_config(f)
        else:
            with open(args.config, "rb") as f:
                config = parse_config(f)
    else:
        config = DEFAULT_CONFIG

    if args.skiplist.startswith("http"):
        with urllib.request.urlopen(args.skiplist) as f:
            skiplist = parse_skiplist(f, config.keys())
    else:
        with open(args.skiplist, "rb") as f:
            skiplist = parse_skiplist(f, config.keys())

    try:
        testsuite_root = find_testsuite_root(args.package_flavor)
    except RuntimeError as e:
        print(e)
        sys.exit(1)

    if args.directory:
        cwd = args.directory
    else:
        cwd = testsuite_root

    bindir = testsuite_root_to_bindir(testsuite_root)

    env = update_env(os.environ, bindir, cwd, args.package_flavor == "classic")
    cmd = pytest_cmd(args.test_group, skiplist, config, args.pytest_args)
    print("Running:", " ".join(cmd))
    pytest_retcode = subprocess.run(
        cmd,
        env=env,
        cwd=cwd,
    ).returncode
    sys.exit(pytest_retcode)
