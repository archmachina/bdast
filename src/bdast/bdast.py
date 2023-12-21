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

def process_spec_v1_step_command(step, state, preprocess) -> int:
    logger = logging.getLogger(__name__)

    # Capture relevant properties for this step
    step_type = step.get('type', '')
    step_shell = step.get('shell', False)
    step_command = step.get('command', '')
    step_capture = step.get('capture', '')
    step_interpreter = step.get('interpreter', '')
    step_env = step.get('env', {})

    # Validate parameters
    if step_shell is None or not isinstance(step_shell, bool):
        logger.error('Invalid value on step shell')
        return 1

    if step_type is None or not isinstance(step_command, str) or step_command == '':
        logger.error('Invalid value or empty step type')
        return 1

    if step_command is None or not isinstance(step_command, str) or step_command == '':
        logger.error('Invalid value or empty step command')
        return 1

    if step_capture is None or not isinstance(step_capture, str):
        logger.error('Invalid value on step capture')
        return 1

    if step_interpreter is None or not isinstance(step_interpreter, str):
        logger.error('Invalid value or empty step interpreter')
        return 1

    if step_env is None or not isinstance(step_env, dict):
        logger.error('Invalid value or empty step env')
        return 1

    # Remainder of the function is actual work, so return here
    if preprocess:
        return 0

    # Arguments to subprocess.run
    subprocess_args = {
        'env': state['environ'].copy(),
        'stdout': None,
        'stderr': subprocess.STDOUT,
        'shell': step_shell
    }

    # Merge environment variables in to this step environment
    for key in step_env.keys():
        subprocess_args['env'][key] = str(step_env[key])

    # If we're capturing, stdout should come back via pipe
    if step_capture != '':
        subprocess_args['stdout'] = subprocess.PIPE

    # Override interpreter if the type is bash or pwsh
    if step_type == 'pwsh':
        step_interpreter = 'pwsh -noni -c -'
    elif step_type == 'bash':
        step_interpreter = 'bash'

    # If an interpreter is defined, this is the executable to call instead
    if step_interpreter is not None and step_interpreter != '':
        call_args = step_interpreter
        subprocess_args['text'] = True
        subprocess_args['input'] = step_command
    else:
        call_args = step_command
        subprocess_args['stdin'] = subprocess.DEVNULL

    # If shell is not true, then we need to split the string for the call to subprocess.run
    if not step_shell:
        call_args = shlex.split(call_args)

    logger.debug(f'Call arguments: {call_args}')
    sys.stdout.flush()
    proc = subprocess.run(call_args, **subprocess_args)

    # Check if the process failed
    if proc.returncode != 0:

        # If the subprocess was called with stdout PIPE, output it here
        if stdout is not None:
            print(proc.stdout.decode('ascii'))

        logger.error(f'Process exited with non-zero exit code: {proc.returncode}')
    else:
        # If we're capturing output from the step, put it in the environment now
        if step_capture:
            stdout_capture = proc.stdout.decode('ascii')
            state['environ'][step_capture] = str(stdout_capture)
            print(stdout_capture)

    return proc.returncode

def process_spec_v1_step(step, state, preprocess) -> int:
    logger = logging.getLogger(__name__)

    # Get parameters for this step
    step_name = step.get('name', '')
    step_type = step.get('type', 'command')

    # Validate parameters for the step
    if step_name is None or not isinstance(step_name, str) or step_name == '':
        logger.error('Invalid value or empty step name')
        return 1

    if step_type is None or not isinstance(step_type, str) or step_type == '':
        logger.error('Invalid value or empty step type')
        return 1

    # Status message, if we're actually processing the steps
    if not preprocess:
        logger.info(f'Processing step: {step_name}')

    # Determine which type of step this is and process
    if step_type == 'command' or step_type == 'pwsh' or step_type == 'bash':
        return process_spec_v1_step_command(step, state, preprocess)
    else:
        logger.error(f'Unknown step type: {step_type}')
        return 1

    return 0


def process_spec_v1(spec_content) -> int:
    logger = logging.getLogger(__name__)

    # Process a version 1 specification file

    # State for processing
    state = {
        'environ': os.environ.copy()
    }

    # Merge custom environment vars in
    if 'env' in spec_content:
        env = spec_content.get('env')
        if not isinstance(env, dict):
            logger.error('Invalid value for env')
            return 1

        # Merge definitions with current environment
        for key in env.keys():
            state['environ'][key] = str(env[key])

    # Read in steps
    steps = spec_content.get('steps', [])
    if not isinstance(steps, list):
        logger.error('The steps key is not a list')
        return 1

    # Preprocess steps to capture any semantic issues early
    for step in steps:
        ret = process_spec_v1_step(step, state, preprocess=True)
        if ret != 0:
            return ret

    # Process steps
    for step in steps:
        ret = process_spec_v1_step(step, state, preprocess=False)
        if ret != 0:
            return ret

def process_args() -> int:
    # Create parser for command line arguments
    parser = argparse.ArgumentParser(
        prog='bdast',
        description='Build and Deployment Assistant',
        exit_on_error=False
    )

    # Parser configuration
    parser.add_argument('-f',
        action='store',
        dest='spec',
        help='YAML spec file containing build or deployment definition')

    parser.add_argument('-v',
        action='store_true',
        dest='verbose',
        help='Enable verbose output')

    args = parser.parse_args()

    # Store the options here to allow modification depending on options
    verbose = args.verbose
    spec = args.spec

    # Logging configuration
    level = logging.INFO
    if verbose:
        level = logging.DEBUG
    logging.basicConfig(level=level, format='%(levelname)s: %(message)s')
    logger = logging.getLogger(__name__)

    # Check for spec file
    if spec is None or spec == '':
        logger.error('Empty specification supplied')
        return 1

    if not os.path.isfile(spec):
        logger.error('Spec file does not exist or is not a file')
        return 1

    # Change directory to the spec file directory
    dir_name = os.path.dirname(spec)
    if dir_name != '':
        os.chdir(dir_name)

    # Load spec file
    logger.debug(f'Loading spec: {spec}')
    try:
        with open(spec, 'r') as file:
            spec_content = yaml.safe_load(file)
    except Exception as e:
        logger.error(f'Failed to load and parse yaml spec file: {e}')
        return 1

    # Load parser for the spec version
    try:
        version = int(spec_content.get('version'))
    except Exception as e:
        logger.error(f'Failed to read version information from spec: {e}')
        return 1

    if version == 1:
        return process_spec_v1(spec_content)
    else:
        logger.error(f'Invalid version in spec file: {version}')
        return 1

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
