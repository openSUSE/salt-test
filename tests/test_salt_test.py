"""Unit tests for salt_tests.py"""
import salt_tests_launcher as stl
import argparse
import pytest

def test_prepare_argparser():
    parser = stl.prepare_argparser("salt-test")
    args = parser.parse_args(["-s", "skipped.toml", "-c", "config.toml", "-f", "classic", "unit", "--", "--slow"])
    assert args == argparse.Namespace(skiplist='skipped.toml', config='config.toml', package_flavor='classic', test_group='unit', pytest_args=["--slow"])

    args = parser.parse_args(["-s", "skipped.toml", "-c", "config.toml", "functional"])
    assert args == argparse.Namespace(skiplist='skipped.toml', config='config.toml', package_flavor='bundle', test_group='functional', pytest_args=[])


