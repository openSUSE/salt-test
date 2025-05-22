from setuptools import find_packages, setup

setup(
    name="salt-test",
    version="1.5",
    install_requires=["tomli;python_version<'3.11'"],
    package_dir={"": "src"},  # not needed for setuptools >= 61
    packages=find_packages("src"),
    entry_points={
        "console_scripts": [
            "salt-test = salt_test:main",
        ]
    },
)
