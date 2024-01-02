#!/usr/bin/env python3

import os
import sys
import argparse
import json
import re
import subprocess
import shlex
import logging
import yaml
import tempfile
from string import Template
import traceback

import bdast_v1

def process_args() -> int:
    # Create parser for command line arguments
    parser = argparse.ArgumentParser(
        prog='bdast',
        description='Build and Deployment Assistant',
        exit_on_error=False
    )

    # Parser configuration
    parser.add_argument('-v',
        action='store_true',
        dest='verbose',
        help='Enable verbose output')

    parser.add_argument(action='store',
        dest='spec',
        help='YAML spec file containing build or deployment definition')

    parser.add_argument(action='store',
        dest='action',
        help='Action name')

    args = parser.parse_args()

    # Store the options here to allow modification depending on options
    verbose = args.verbose
    spec_file = args.spec
    action_name = args.action

    # Logging configuration
    level = logging.INFO
    if verbose:
        level = logging.DEBUG
    logging.basicConfig(level=level, format='%(levelname)s: %(message)s')
    logger = logging.getLogger(__name__)

    # Check for spec file
    if spec_file is None or spec_file == '':
        logger.error('Specification file not supplied')
        return 1

    if not os.path.isfile(spec_file):
        logger.error('Spec file does not exist or is not a file')
        return 1

    # Load spec file
    logger.info(f'Loading spec: {spec_file}')
    try:
        with open(spec_file, 'r') as file:
            spec = yaml.safe_load(file)
    except Exception as e:
        if verbose:
            logger.exception(e)
        logger.error(f'Failed to load and parse yaml spec file: {e}')
        return 1

    # Change directory to the spec file directory
    dir_name = os.path.dirname(spec_file)
    if dir_name != '':
        try:
            os.chdir(dir_name)
        except Exception as e:
            logger.error(f'Could not change to spec directory {dir_name}: {e}')
            return 1

    logger.info(f'Working directory: {os.getcwd()}')

    # Extract version number from the spec
    try:
        version = str(spec.get('version'))
    except Exception as e:
        if verbose:
            logger.exception(e)
        logger.error(f'Failed to read version information from spec: {e}')
        return 1

    # Process spec as a specific version
    try:
        if version == '1':
            logger.info('Processing spec as version 1')
            bdast_v1.process_spec_v1(spec, action_name)
        else:
            logger.error(f'Invalid version in spec file: {version}')
            return 1
    except Exception as e:
        if verbose:
            logger.exception(e)
        logger.error(f'Failed processing spec with exception: {e}')
        return 1

    return 0

def main():
    try:
        ret = process_args()
        sys.stdout.flush()
        sys.exit(ret)
    except Exception as e:
        logging.getLogger(__name__).exception(e)
        sys.stdout.flush()
        sys.exit(1)

if __name__ == '__main__':
    main()

