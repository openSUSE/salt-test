"""Run Salt Test Suite by test group."""
import os
import pathlib
import re
import subprocess
import sys
import typing
import urllib.request
from argparse import ArgumentParser, FileType
from collections import defaultdict

import toml

DEFAULT_CONFIG = {
    "unit": {"dirs": ["tests/unit/", "tests/pytests/unit/"]},
    "functional": {"dirs": ["tests/pytests/functional"]},
    "integration": {
        "dirs": ["tests/integration/", "tests/pytests/integration/"],
    },
    "scenarios": {"dirs": ["tests/pytests/scenarios/"], "pytest_args": ["--slow"]},
}

FLAVOR_RPM = {
    "classic": "python3-salt-testsuite",
    "bundle": "venv-salt-minion-testsuite",
}


def parse_skiplist(
    file: typing.TextIO, groups: typing.Iterable[str]
) -> typing.Dict[str, typing.List[str]]:
    """Reads skiplist and returns a dictionary.

    The dictionary fills in missing test groups to guarantee [] access.
    """
    raw_dict = toml.load(file)
    # raw_dict: {"ignore": {$group: [...]}, "skip": { $group: [...]}}
    ignored_files = raw_dict.get("ignore", {})
    skipped_tests = raw_dict.get("skip", {})

    skiplist = {}
    for group in groups:
        skiplist[group] = {
            "ignore": ignored_files.get(group, []),
            "skip": skipped_tests.get(group, []),
        }
    return skiplist


def parse_config(file: typing.TextIO):
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

    def _list_files(rpm: str) -> typing.List[str]:
        cp = subprocess.run(
            ["rpm", "-q", "-l", rpm],
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


def prepare_argparser(progname) -> ArgumentParser:
    parser = ArgumentParser(progname)
    parser.add_argument(
        "--skiplist",
        "-s",
        type=str,
        required=True,
        help="Specify location of skiplist (TOML).",
    )
    parser.add_argument(
        "--config", "-c", type=str, help="Specify location of config (TOML)."
    )
    parser.add_argument(
        "--package-flavor",
        "-f",
        choices=tuple(FLAVOR_RPM.keys()),
        default="bundle",
        help="Used to determine the Python environment that includes dependencies.",
    )
    parser.add_argument("test_group", help="Group of tests to run.")
    parser.add_argument(
        "pytest_args",
        nargs="*",
        help="Specify extra arguments for pytest, separated from 'test_group' by a single --.",
    )
    return parser


def update_env(env: os._Environ[str], bindir: str) -> dict:
    env_copy = env.copy()
    env_copy["PATH"] = f"{bindir}:{env_copy['PATH']}"
    return env_copy


def main(progname="salt-test"):
    parser = prepare_argparser(progname)
    args = parser.parse_args()

    if args.config:
        if args.config.startswith("http"):
            config_open = urllib.request.urlopen
        else:
            config_open = open

        with config_open(args.config) as f:
            config = parse_config(f)
    else:
        config = DEFAULT_CONFIG

    if args.skiplist.startswith("http"):
        skip_open = urllib.request.urlopen
    else:
        skip_open = open
    with skip_open(args.skiplist) as f:
        skiplist = parse_skiplist(f, config.keys())

    try:
        testsuite_root = find_testsuite_root(args.package_flavor)
    except RuntimeError as e:
        print(e)
        sys.exit(1)

    if args.root:
        cwd = args.root
    else:
        cwd = testsuite_root

    bindir = testsuite_root_to_bindir(testsuite_root)

    env = update_env(os.environ, bindir)
    cmd = pytest_cmd(args.group, skiplist, config, args.pytest_args)
    print("Running:", " ".join(cmd))
    subprocess.run(
        cmd,
        env=env,
        cwd=cwd,
    )


if __name__ == "__main__":
    main("salt_tests_launcher.py")