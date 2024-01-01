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

class CommonState:
    def __init__(self, spec={}):
        self.spec = spec

class ScopeState:
    def __init__(self, *, parent=None):
        self.parent = parent

        # Copy parent vars, if specified
        if self.parent is not None:
            # Create a new env scope, independent of the parents env vars
            self.envs = self.parent.envs.copy()
            self.common = self.parent.common

            return

        # Create a new env state and common state
        self.envs = os.environ.copy()
        self.common = CommonState()

    def merge_envs(self, new_envs, all_scopes=False):
        # Validate parameters
        print(type(new_envs))
        if new_envs is None or not isinstance(new_envs, dict):
            raise Exception('Invalid type passed to merge_envs. Must be a dictionary')

        # Merge new_envs dictionary in to the current envs
        for key in new_envs.keys():
            self.envs[key] = str(new_envs[key])

        # Call merge for parent, if all_scopes required
        if all_scopes and self.parent is not None:
            parent.merge_envs(new_envs, all_scopes=True)

def template_if_string(val, mapping):
    if val is not None and isinstance(val, str):
        template = Template(val)
        return template.substitute(mapping)

    return val

def assert_type(obj, obj_type, message):
    if not isinstance(obj, obj_type):
        raise Exception(message)

def spec_extract_value(spec, key, *, template_map, default=None, required=False, failemptystr=False):
    # Check that we have a valid spec
    if spec is None or not isinstance(spec, dict):
        raise Exception(f'spec is missing or is not a dictionary')

    # Check type for template_map
    if template_map is not None and not isinstance(template_map, dict):
        raise Exception('Invalid type passed as template_map')

    # Handle a missing key in the spec
    if key not in spec:
        if required:
            raise KeyError(f'Missing key \'{key}\' in spec')
        return default

    # Retrieve value
    val = spec[key]

    # string specific processing
    if val is not None and isinstance(val, str):
        # Template the string
        if template_map is not None:
            val = template_if_string(val, template_map)

        # Check if we have an empty string and should fail
        if failemptystr and val == '':
            raise Exception('Value for key \'{key}\' is empty, but a value is required')

    # Perform string substitution for other types
    if template_map is not None and val is not None:
        if isinstance(val, list):
            val = [template_if_string(x, template_map) for x in val]

        if isinstance(val, dict):
            for key in val.keys():
                val[key] = template_if_string(val[key], template_map)

    return val

def process_spec_v1_step_semver(step_name, step, state, validate_only) -> int:
    logger = logging.getLogger(__name__)

    # Merge environment variables in early
    step_env = spec_extract_value(step, 'env', default={}, template_map=state['environ'])
    assert_type(step_env, dict, 'env is not a dictionary')

    for key in step_env.keys():
        state['environ'][key] = str(step_env[key])

    required = bool(spec_extract_value(step, 'required', default=False, template_map=state['environ']))
    sources = spec_extract_value(step, 'sources', default=[], template_map=state['environ'])
    assert_type(sources, list, 'step sources is not a list')

    strip_regex = spec_extract_value(step, 'strip_regex', default=['$refs/tags/', '^v'],
        template_map=state['environ'])
    assert_type(strip_regex, list, 'step strip_regex is not a list')

    semver_regex = '^(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\.(?P<patch>0|[1-9]\d*)(?:-(?P<prerelease>(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?(?:\+(?P<buildmetadata>[0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$'

    # Stop now if we're only validating
    if validate_only:
        return 0

    for env_name in sources:
        env_name = str(env_name)

        source = state['environ'].get(env_name, '')
        logger.info(f'Checking {env_name}/{source}')

        # Strip any components matching strip_regex
        for regex_item in strip_regex:
            source = re.sub(regex_item, '', source)

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

def process_spec_v1_action(action_name, action, state, validate_only) -> int:
    logger = logging.getLogger(__name__)

    # Create a new scope state
    state = ScopeState(parent=state)

    # Merge environment variables in early
    action_envs = spec_extract_value(action, 'env', default={}, template_map=state.envs)
    assert_type(action_envs, dict, 'action envs is not a dictionary')
    action_env.merge_envs(action_envs)

    # Capture steps for this action
    action_steps = spec_extract_value(action, 'steps', default={}, template_map=state.envs)
    assert_type(action_steps, list, 'action steps is not a list')

    # Process steps in action
    for step_name in action_steps:
        if step_name not in state.common.spec['steps']:
            logger.error(f'Action({action_name}): Reference to step that does not exist - {step_name}')
            return 1

        # Only continue with processing if we're not validate_only
        if validate_only:
            continue

        # Call the processor for this step
        print('')
        print(f'**************** STEP {step_name}')

        ret = process_spec_v1_step(step_name, state.common.spec['steps'][step_name], state,
                validate_only=validate_only)

        if ret != 0:
            logger.error(f'Step returned non-zero: {ret}')

        print('')
        print(f'**************** END STEP {step_name}')
        print('')

        if ret != 0:
            return ret

    return 0

def process_spec_v1_step_command(step_name, step, state, validate_only) -> int:
    logger = logging.getLogger(__name__)

    # Capture relevant properties for this step
    step_type = step.get('type', '')
    # step_shell = step.get('shell', False)
    step_shell = bool(spec_extract_value(step, 'shell', default=False, template_map=state['environ']))
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
    if validate_only:
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

def process_spec_v1_step(step_name, step, state, validate_only) -> int:
    logger = logging.getLogger(__name__)

    # Create a new scope state
    state = ScopeState(parent=state)

    # Merge environment variables in early
    envs = spec_extract_value(step, 'env', default={}, template_map=state.envs)
    assert_type(envs, dict, 'step env is not a dictionary')
    state.merge_envs(envs)

    # Get parameters for this step
    step_type = spec_extract_value(step, 'type', template_map=state.envs, failemptystr=True)
    assert_type(step_type, str, 'Step type is not a string')

    # Determine which type of step this is and process
    if step_type == 'command' or step_type == 'pwsh' or step_type == 'bash':
        return process_spec_v1_step_command(step_name, step, state, validate_only=validate_only)
    elif step_type == 'semver':
        return process_spec_v1_step_semver(step_name, step, state, validate_only=validate_only)

    logger.error(f'Step({step_name}): Unknown step type: {step_type})')
    return 1

def process_spec_v1(spec, action_name) -> int:
    logger = logging.getLogger(__name__)

    # Make sure we have a dictionary for the spec
    assert_type(spec, dict, 'Specification is not a dictionary')

    # State for processing
    state = ScopeState()
    state.common.spec = spec

    # Make sure we have a valid action name
    if action_name is None or action_name == '':
        logger.error('Invalid or empty action name specified')
        return 1

    # Capture global environment variables from spec and merge
    envs = spec_extract_value(state.common.spec, 'env', default={},
        template_map=state.envs)
    assert_type(envs, dict, 'env is not a dictionary')
    state.merge_envs(envs)

    # Read in steps
    steps = spec_extract_value(state.common.spec, 'steps', default={},
        template_map=None)
    assert_type(steps, dict, 'steps is not a dictionary')

    # Read in actions
    actions = spec_extract_value(state.common.spec, 'actions', default={},
        template_map=None)
    assert_type(actions, dict, 'actions is not a dictionary')

    # Make sure the action name exists
    if action_name not in actions:
        logger.error(f'Action name ({action_name}) does not exist')
        return 1

    # Validate steps and actions to capture any semantic issues early
    logger.debug('Validating spec content')

    for key in steps.keys():
        ret = process_spec_v1_step(key, steps[key], state, validate_only=True)
        if ret != 0:
            return ret

    for key in actions.keys():
        ret = process_spec_v1_action(key, actions[key], state, validate_only=True)
        if ret != 0:
            return ret

    # Process action
    print('')
    print(f'**************** ACTION {action_name}')
    ret = process_spec_v1_action(action_name, actions[action_name], state, validate_only=False)
    print('**************** END ACTION')
    print('')

    return ret

