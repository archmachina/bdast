#!/usr/bin/env python3
"""
Build and Deployment Assistance - This module is the entrypoint for the command line tool
and will perform actions based on the content of a YAML specification file.
"""

import argparse
import logging
import os
import sys
import textwrap
import yaml

from . import bdast_v1
from . import bdast_v2

from .exception import SpecLoadException

logger = logging.getLogger(__name__)


WRAPPER = """\
#!/bin/bash

set -o pipefail
set -e

# Global settings
SCRIPT=$(readlink -f "${0}")
DIR=$(dirname "${SCRIPT}")
cd "${DIR}" || exit 1

# Configure and activate the virtual environment
python3 -m venv env
. ./env/bin/activate
python3 -m pip install --upgrade pip

# Install from requirements, if present
if [ -f requirements.txt ] ; then
  python3 -m pip install -r ./requirements.txt
fi

# If bdast is already installed from requirements, then this won't
# change it, otherwise it will install the latest version
python3 -m pip install bdast

exec bdast run "$@"

exit 1
"""


def load_spec(spec_file, action_name, action_arg):
    """
    Loads and parses the YAML specification from file, sets the working directory, and
    calls the appropriate processor for the version of the specification
    """

    # Check for spec file
    if spec_file is None or spec_file == "":
        raise SpecLoadException("Specification filename missing")

    if not os.path.isfile(spec_file):
        raise SpecLoadException(f"Spec file does not exist or is not a file: {spec_file}")

    # Convert to an absolute path
    spec_file = os.path.abspath(spec_file)

    # Load spec file
    logger.info("Loading spec: %s", spec_file)
    with open(spec_file, "r", encoding="utf-8") as file:
        spec = yaml.safe_load(file)

    # Make sure we have a dictionary
    if not isinstance(spec, dict):
        raise SpecLoadException("Parsed specification is not a dictionary")

    # Change directory to the spec file directory
    dir_name = os.path.dirname(spec_file)
    if dir_name != "":
        logger.debug("Changing to directory: %s", dir_name)
        os.chdir(dir_name)

    logger.info("Working directory: %s", os.getcwd())

    # Extract version number from the spec
    if "version" not in spec:
        raise SpecLoadException("Missing version key in spec")

    version = str(spec["version"])
    logger.info("Version from specification: %s", version)

    # Make sure action_arg is a string
    action_arg = str(action_arg) if action_arg is not None else ""

    # Process spec as a specific version
    if version == "1":
        logger.info("Processing spec as version 1")
        bdast_v1.process_spec(spec_file, action_name, action_arg)
    if version in ("2alpha"):
        logger.info("Processing spec as version 2")
        bdast_v2.process_spec(spec_file, action_name, action_arg)
    else:
        raise SpecLoadException(f"Invalid version in spec file: {version}")


def process_template(args):
    """
    Process the 'template' subcommand.

    This generates a sample template bdast configuration on stdout
    """

    # Header parts of the template
    print(textwrap.dedent("""\
    ---
    version: 1

    env:

    steps:

    """))

    # Actions
    print(textwrap.dedent("""\

    actions:

    """))

    return 0


def process_wrapper(args):
    """
    Process the 'wrapper' subcommand.

    This generates a sample wrapper script for running bdast on stdout
    """

    print(WRAPPER)

    return 0


def process_run(args):
    """
    Process the 'run' subcommand.

    Run bdast for the provided bdast configuration file, executing the requested action
    """

    try:
        load_spec(args.spec, args.action, " ".join(args.action_arg))
    except Exception as e:  # pylint: disable=broad-exception-caught
        if args.verbose:
            logger.error(e, exc_info=True, stack_info=True)
        else:
            logger.error(e)

        return 1

    logger.info("Processing completed successfully")

    return 0


def process_args() -> int:
    """
    Processes command line arguments and calls load_spec to load the actual specification from the
    filesystem.
    This function also performs exception handling based on command line arguments
    """

    # Create parser for command line arguments
    parser = argparse.ArgumentParser(
        prog="bdast", description="Build and Deployment Assistant", exit_on_error=False
    )

    # Common parser arguments
    parser.add_argument(
        "-v", "-d", action="store_true", dest="verbose", help="Enable verbose output"
    )

    parser.set_defaults(call_func=None)
    subparsers = parser.add_subparsers(dest="subcommand")

    # template subcommand
    sub_template = subparsers.add_parser(
        "template", help="Generate a sample configuration file"
    )
    sub_template.set_defaults(call_func=process_template)

    # wrapper subcommand
    sub_wrapper = subparsers.add_parser(
        "wrapper", help="Generate a wrapper script to create a venv and run bdast"
    )
    sub_wrapper.set_defaults(call_func=process_wrapper)

    # run subcommand
    sub_run = subparsers.add_parser(
        "run", help="Run an action from a bdast configuration"
    )
    sub_run.set_defaults(call_func=process_run)

    sub_run.add_argument(
        "-f",
        action="store",
        dest="spec",
        default="bdast.yaml",
        help="Path to bdast configuration file (default: bdast.yaml)",
    )

    sub_run.add_argument(action="store", dest="action", help="Action name")

    sub_run.add_argument(
        action="store",
        dest="action_arg",
        help="Action argument",
        nargs=argparse.REMAINDER,
    )

    # Parse command line arguments
    args = parser.parse_args()

    # Logging configuration
    level = logging.INFO
    if args.verbose:
        level = logging.DEBUG

    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")

    # Make sure we have a subcommand
    subcommand = args.subcommand
    if subcommand is None or subcommand == "" or args.call_func is None:
        logger.error("Missing or empty subcommand")
        return 1

    # Run subcommand
    return args.call_func(args)


def main():
    """
    Entrypoint for the module.
    Minor exception handling is performed, along with return code processing and
    flushing of stdout on program exit.
    """

    try:
        ret = process_args()
        sys.stdout.flush()
        sys.exit(ret)
    except Exception as e:  # pylint: disable=broad-exception-caught
        logging.getLogger(__name__).exception(e)
        sys.stdout.flush()
        sys.exit(1)


if __name__ == "__main__":
    main()
