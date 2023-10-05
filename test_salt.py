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

# group tests subdirectories
TEST_GROUPS = {
    "unit": {"test_dirs": ["tests/unit/", "tests/pytests/unit/"]},
    "functional": {"test_dirs": ["tests/pytests/functional"]},
    "integration": {
        "test_dirs": ["tests/integration/", "tests/pytests/integration/"],
    },
    "scenarios": {"test_dirs": ["tests/pytests/scenarions/"]},
}

FLAVOR_RPM = {
    "classic": "python3-salt-testsuite",
    "bundle": "venv-salt-minion-testsuite",
}


def parse_skiplist(file: typing.TextIO) -> typing.Dict[str, typing.List[str]]:
    """Reads skiplist and returns a dictionary.

    The dictionary fills in missing test groups to guarantee [] access.
    """
    raw_dict = toml.load(file)
    # raw_dict: {"ignore": {$group: [...]}, "skip": { $group: [...]}}
    ignored_files = raw_dict.get("ignore", {})
    skipped_tests = raw_dict.get("skip", {})

    skiplist = {}
    for group in TEST_GROUPS.keys():
        skiplist[group] = {
            "ignore": ignored_files.get(group, []),
            "skip": skipped_tests.get(group, []),
        }
    return skiplist


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


def pytest_cmd(
    args: typing.List[str], groups: typing.List[str], skiplist: dict, config: dict
):
    """Compose the correct command args for pytest."""
    cmd = ["pytest"]
    cmd.extend(args)
    for group in groups:
        for skipped_file in skiplist[group]["ignore"]:
            cmd.extend(["--ignore", skipped_file])
        for skipped_test in skiplist[group]["skip"]:
            cmd.extend(["--deselect", skipped_test])

    # test dirs should follow CLI flags
    for group in groups:
        cmd.extend(config[group]["test_dirs"])

    return cmd


def main():
    parser = ArgumentParser("test_salt.py")
    parser.add_argument("--skiplist", "-s", type=str, required=True)
    parser.add_argument(
        "--package-flavor", "-f", choices=tuple(FLAVOR_RPM.keys()), default="bundle"
    )
    parser.add_argument(
        "test_groups",
        nargs="+",
        choices=["unit", "functional", "integration", "scenarios", "all"],
    )
    args = parser.parse_args()
    groups = args.test_groups
    if groups == "all":
        groups = ["unit", "functional", "integration", "scenarios"]

    if args.skiplist.startswith("http"):
        opener = urllib.request.urlopen
    else:
        opener = open

    with opener(args.skiplist) as f:
        skiplist = parse_skiplist(f)

    testsuite_root = find_testsuite_root(args.package_flavor)
    bindir = testsuite_root_to_bindir(testsuite_root)
    env = os.environ.copy()
    env["PATH"] = f"{bindir}:{env['PATH']}"
    cmd = pytest_cmd(groups, skiplist, TEST_GROUPS)
    print("Running:", " ".join(cmd))
    subprocess.run(
        cmd,
        env=env,
        cwd=testsuite_root,
    )


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as e:
        print(e)
        sys.exit(1)
