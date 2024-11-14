"""Unit tests for salt_test"""
import argparse
import io

import salt_test


def test_prepare_argparser():
    parser = salt_test.prepare_argparser()
    args = parser.parse_args(
        [
            "-s",
            "skipped.toml",
            "-c",
            "config.toml",
            "-f",
            "classic",
            "unit",
            "--",
            "--slow",
        ]
    )
    assert args == argparse.Namespace(
        skiplist="skipped.toml",
        config="config.toml",
        directory=None,
        package_flavor="classic",
        test_group="unit",
        pytest_args=["--slow"],
    )

    args = parser.parse_args(
        ["-s", "skipped.toml", "-c", "config.toml", "-d", "/code/", "functional"]
    )
    assert args == argparse.Namespace(
        skiplist="skipped.toml",
        directory="/code/",
        config="config.toml",
        package_flavor="bundle",
        test_group="functional",
        pytest_args=[],
    )


skiplist_empty = io.BytesIO(
    b"""\
"""
)
skiplist = io.BytesIO(
    b"""\
[ignore]
unit = [
	"tests/unit/modules/test_boto3_elasticsearch.py",
	"tests/unit/modules/test_boto3_route53.py",
	"tests/unit/modules/test_boto_route53.py",
	"tests/unit/utils/test_boto3mod.py",
]
[skip]
unit = [
	"tests/unit/test_config.py::SampleConfTest::test_conf_master_sample_is_commented",
	"tests/unit/test_config.py::ConfigTestCase::test_load_minion_config_from_environ_var",
	"tests/unit/test_config.py::APIConfigTestCase::test_api_config_log_file_values",
	"tests/unit/test_config.py::APIConfigTestCase::test_api_config_prepend_root_dirs_return",
	"tests/unit/cli/test_support.py::ProfileIntegrityTestCase::test_jobs_trace_template_profile",
]
functional = [
	"tests/pytests/functional/channel/test_server.py::test_pub_server_channel[transport(zeromq)]",
	"tests/pytests/functional/modules/test_sdb.py::test_setting_sdb_values_with_text_and_bytes_should_retain_data_types[bang]",
	"tests/pytests/functional/modules/test_sdb.py::test_setting_sdb_values_with_text_and_bytes_should_retain_data_types[expected_value2]",
]
"""
)


def test_parse_skiplist():
    groups = ["unit", "integration", "functional", "scenarios"]
    empty = salt_test.parse_skiplist(skiplist_empty, groups)
    assert empty == {
        "unit": {"ignore": [], "skip": []},
        "integration": {"ignore": [], "skip": []},
        "functional": {"ignore": [], "skip": []},
        "scenarios": {"ignore": [], "skip": []},
    }

    populated = salt_test.parse_skiplist(skiplist, groups)
    assert populated == {
        "unit": {
            "ignore": [
                "tests/unit/modules/test_boto3_elasticsearch.py",
                "tests/unit/modules/test_boto3_route53.py",
                "tests/unit/modules/test_boto_route53.py",
                "tests/unit/utils/test_boto3mod.py",
            ],
            "skip": [
                "tests/unit/test_config.py::SampleConfTest::test_conf_master_sample_is_commented",
                "tests/unit/test_config.py::ConfigTestCase::test_load_minion_config_from_environ_var",
                "tests/unit/test_config.py::APIConfigTestCase::test_api_config_log_file_values",
                "tests/unit/test_config.py::APIConfigTestCase::test_api_config_prepend_root_dirs_return",
                "tests/unit/cli/test_support.py::ProfileIntegrityTestCase::test_jobs_trace_template_profile",
            ],
        },
        "integration": {"ignore": [], "skip": []},
        "functional": {
            "ignore": [],
            "skip": [
                "tests/pytests/functional/channel/test_server.py::test_pub_server_channel[transport(zeromq)]",
                "tests/pytests/functional/modules/test_sdb.py::test_setting_sdb_values_with_text_and_bytes_should_retain_data_types[bang]",
                "tests/pytests/functional/modules/test_sdb.py::test_setting_sdb_values_with_text_and_bytes_should_retain_data_types[expected_value2]",
            ],
        },
        "scenarios": {"ignore": [], "skip": []},
    }
