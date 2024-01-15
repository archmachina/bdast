#!/usr/bin/env python3
"""
Build and Deployment Assistance - This module is the entrypoint for the command line tool
and will perform actions based on the content of a YAML specification file.
"""

import argparse
import logging
import os
import sys

import yaml

from . import bdast_v1
from .bdast_exception import SpecLoadException

logger = logging.getLogger(__name__)


def load_spec(spec_file, actions):
    """
    Loads and parses the YAML specification from file, sets the working directory, and
    calls the appropriate processor for the version of the specification
    """

    # Check for spec file
    if spec_file is None or spec_file == "":
        raise SpecLoadException("Specification filename missing")

    if not os.path.isfile(spec_file):
        raise SpecLoadException("Spec file does not exist or is not a file")

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

    # Process spec as a specific version
    if version == "1":
        logger.info("Processing spec as version 1")
        bdast_v1.process_spec_v1(spec, actions)
    else:
        raise SpecLoadException(f"Invalid version in spec file: {version}")


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

    # Parser configuration
    parser.add_argument(
        "-v", action="store_true", dest="verbose", help="Enable verbose output"
    )

    parser.add_argument(
        "-d", action="store_true", dest="debug", help="Enable debug output"
    )

    parser.add_argument(
        action="store",
        dest="spec",
        help="YAML spec file containing build or deployment definition",
    )

    parser.add_argument(
        action="store", dest="actions", help="Action names", nargs=argparse.REMAINDER
    )

    args = parser.parse_args()

    # Store the options here to allow modification depending on options
    verbose = args.verbose
    debug = args.debug
    spec_file = args.spec
    actions = [str(x) for x in args.actions]

    # Logging configuration
    level = logging.WARNING
    if verbose:
        level = logging.INFO
    if debug:
        level = logging.DEBUG

    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")

    try:
        load_spec(spec_file, actions)
    except Exception as e:  # pylint: disable=broad-exception-caught
        if debug:
            logger.error(e, exc_info=True, stack_info=True)
        else:
            logger.error(e)
        return 1

    logger.info("Processing completed successfully")
    return 0


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
