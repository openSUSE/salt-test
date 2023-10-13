from setuptools import find_packages, setup

setup(
    name="salt-tests-launcher",
    version="1.0",
    install_requires=["toml"],
    package_dir={"": "src"},  # not needed for setuptools >= 61
    packages=find_packages(),
    entry_points={
        "console_scripts": [
            "salt-test = salt_tests_launcher:main",
        ]
    },
)
