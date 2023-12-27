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

def process_spec_v1_step_semver(step_name, step, state, preprocess_only) -> int:
    logger = logging.getLogger(__name__)

    required = step.get('required', False)
    sources = step.get('sources', [])

    semver_regex = '^(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\.(?P<patch>0|[1-9]\d*)(?:-(?P<prerelease>(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?(?:\+(?P<buildmetadata>[0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$'

    # Validate parameters
    if required is None or not isinstance(required, bool):
        logger.error(f'Step({step_name}): Invalid value for required')
        return 1

    if sources is None or not isinstance(sources, list):
        logger.error(f'Step({step_name}): Invalid value for sources')
        return 1

    if preprocess_only:
        return 0

    for env_name in sources:
        env_name = str(env_name)

        source = state['environ'].get(env_name, '')
        logger.info(f'Checking {env_name}/{source}')

        # Check if this source is a semver match
        result = re.match(semver_regex, source)
        if result is None:
            continue

        logger.info(f'Semver match on {source}')

        # Assign semver components to environment vars
        env_vars = {
            'SEMVER_ORIG': source,
            'SEMVER_FULL': '' if result[0] is None else result[0],
            'SEMVER_MAJOR': '' if result[1] is None else result[1],
            'SEMVER_MINOR': '' if result[2] is None else result[2],
            'SEMVER_PATCH': '' if result[3] is None else result[3],
            'SEMVER_PRERELEASE': '' if result[4] is None else result[4],
            'SEMVER_BUILDMETA': '' if result[5] is None else result[5]
        }

        # Determine if this is a prerelease
        if env_vars['SEMVER_PRERELEASE'] != '':
            env_vars['SEMVER_IS_PRERELEASE'] = '1'
        else:
            env_vars['SEMVER_IS_PRERELEASE'] = '0'

        logger.info('SEMVER version information')
        print(env_vars)

        # Merge semver vars in to environment vars
        for key in env_vars:
            state['environ'][key] = env_vars[key]

        return 0

    # No matches found
    logger.error('No semver matches found')
    if required:
        return 1

    return 0

def process_spec_v1_action(action_name, action, state, preprocess_only) -> int:
    logger = logging.getLogger(__name__)

    # Capture relevant properties for this action
    action_steps = action.get('steps', [])

    # Validate parameters
    if action_steps is None or not isinstance(action_steps, list):
        logger.error(f'Action({action_name}): Invalid value for steps')
        return 1

    # Capture action environment variables from spec
    env = action.get('env', {})
    if not isinstance(env, dict):
        logger.error('Invalid value for action env')
        return 1

    if not preprocess_only:
        # Merge environment vars spec in to global environment vars
        for key in env.keys():
            state['environ'][key] = str(env[key])

    # Process steps in action
    for step_name in action_steps:
        if step_name not in state['spec']['steps']:
            logger.error(f'Action({action_name}): Reference to step that does not exist - {step_name}')
            return 1

        # Only continue with processing if we're not preprocess_only
        if preprocess_only:
            continue

        # Call the processor for this step
        print('')
        print(f'**************** STEP {step_name}')

        ret = process_spec_v1_step(step_name, state['spec']['steps'].get(step_name), state,
                preprocess_only=preprocess_only)

        if ret != 0:
            logger.error(f'Step returned non-zero: {ret}')

        print('')
        print(f'**************** END STEP {step_name}')
        print('')

        if ret != 0:
            return ret

    return 0

def process_spec_v1_step_command(step_name, step, state, preprocess_only) -> int:
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
        logger.error(f'Step({step_name}): Invalid value on step shell')
        return 1

    if step_type is None or not isinstance(step_command, str) or step_command == '':
        logger.error(f'Step({step_name}: Invalid value or empty step type')
        return 1

    if step_command is None or not isinstance(step_command, str) or step_command == '':
        logger.error(f'Step({step_name}): Invalid value or empty step command')
        return 1

    if step_capture is None or not isinstance(step_capture, str):
        logger.error(f'Step({step_name}): Invalid value on step capture')
        return 1

    if step_interpreter is None or not isinstance(step_interpreter, str):
        logger.error(f'Step({step_name}): Invalid value on step interpreter')
        return 1

    if step_env is None or not isinstance(step_env, dict):
        logger.error(f'Step({step_name}): Invalid value on step env')
        return 1

    # Remainder of the function is actual work, so return here
    if preprocess_only:
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
        if subprocess_args['stdout'] is not None:
            print(proc.stdout.decode('ascii'))

        logger.error(f'Process exited with non-zero exit code: {proc.returncode}')
    elif step_capture:
        # If we're capturing output from the step, put it in the environment now
        stdout_capture = proc.stdout.decode('ascii')
        state['environ'][step_capture] = str(stdout_capture)
        print(stdout_capture)

    return proc.returncode

def process_spec_v1_step(step_name, step, state, preprocess_only) -> int:
    logger = logging.getLogger(__name__)

    # Get parameters for this step
    step_type = step.get('type', 'command')

    # Validate parameters for the step
    if step_type is None or not isinstance(step_type, str) or step_type == '':
        logger.error(f'Step({step_name}): Invalid value for \'type\'')
        return 1

    # Determine which type of step this is and process
    if step_type == 'command' or step_type == 'pwsh' or step_type == 'bash':
        return process_spec_v1_step_command(step_name, step, state, preprocess_only=preprocess_only)
    elif step_type == 'semver':
        return process_spec_v1_step_semver(step_name, step, state, preprocess_only=preprocess_only)

    logger.error(f'Step({step_name}): Unknown step type: {step_type})')
    return 1

def process_spec_v1(spec, action_name) -> int:
    logger = logging.getLogger(__name__)

    # Process a version 1 specification file

    # State for processing
    state = {
        'environ': os.environ.copy(),
        'spec': spec
    }

    # Make sure we have a dictionary for the spec
    if not isinstance(spec, dict):
        logger.error('Specification is not a dictionary')
        return 1

    # Make sure we have a valid action name
    if action_name is None or action_name == '':
        logger.error('Invalid or empty action name specified')
        return 1

    # Capture global environment variables from spec
    env = state['spec'].get('env', {})
    if not isinstance(env, dict):
        logger.error('Invalid value for global env')
        return 1

    # Merge environment vars spec in to global environment vars
    for key in env.keys():
        state['environ'][key] = str(env[key])

    # Read in steps
    steps = state['spec'].get('steps', {})
    if not isinstance(steps, dict):
        logger.error('The steps key is not a dict')
        return 1

    # Read in actions
    actions = state['spec'].get('actions', {})
    if not isinstance(actions, dict):
        logger.error('The actions key is not a dict')
        return 1

    # Make sure the action name exists
    if action_name not in actions:
        logger.error(f'Action name ({action_name}) does not exist')
        return 1

    # Preprocess steps and actions to capture any semantic issues early
    logger.debug('Validating spec content')

    for key in steps.keys():
        ret = process_spec_v1_step(key, steps[key], state, preprocess_only=True)
        if ret != 0:
            return ret

    for key in actions.keys():
        ret = process_spec_v1_action(key, actions[key], state, preprocess_only=True)
        if ret != 0:
            return ret

    # Process action
    print('')
    print(f'**************** ACTION {action_name}')
    ret = process_spec_v1_action(action_name, actions[action_name], state, preprocess_only=False)
    print('**************** END ACTION')
    print('')

    return ret

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
    logger.debug(f'Loading spec: {spec_file}')
    try:
        with open(spec_file, 'r') as file:
            spec = yaml.safe_load(file)
    except Exception as e:
        logger.error(f'Failed to load and parse yaml spec file: {e}')
        return 1

    # Change directory to the spec file directory
    dir_name = os.path.dirname(spec_file)
    if dir_name != '':
        os.chdir(dir_name)

    logger.debug(f'Working directory: {os.getcwd()}')

    # Load parser for the spec version
    try:
        version = str(spec.get('version'))
    except Exception as e:
        logger.error(f'Failed to read version information from spec: {e}')
        return 1

    # Determine which version of spec to process as
    if version == '1':
        logger.debug('Processing spec file as version 1')
        ret = process_spec_v1(spec, action_name)
    else:
        logger.error(f'Invalid version in spec file: {version}')
        return 1

    # Print message if spec processing failed
    if ret != 0:
        logger.error(f'Processing of spec failed with code {ret}')

    return ret

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
