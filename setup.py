import os

from setuptools import find_packages, setup

with open("README.md") as readme_file:
    README = readme_file.read()

setup_args = {
    "name": "bdast",
    "version": os.environ["BUILD_VERSION"],
    "description": "Build and Deployment Assistant",
    "long_description_content_type": "text/markdown",
    "long_description": README,
    "license": "MIT",
    "packages": find_packages(where="src", include=["bdast", "bdast.*"]),
    "author": "Jesse Reichman",
    "keywords": ["Build", "Deployment", "Assistant"],
    "url": "https://github.com/archmachina/bdast",
    "download_url": "https://pypi.org/project/bdast/",
    "entry_points": {"console_scripts": ["bdast = bdast:main"]},
    "package_dir": {"": "src"},
    "install_requires": ["requests>=2.0.0", "PyYAML>=5.0.0"],
}

if __name__ == "__main__":
    setup(**setup_args, include_package_data=True)
