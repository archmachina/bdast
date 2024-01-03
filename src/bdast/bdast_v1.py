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
        if new_envs is None or not isinstance(new_envs, dict):
            raise Exception("Invalid type passed to merge_envs. Must be a dictionary")

        # Merge new_envs dictionary in to the current envs
        for key in new_envs.keys():
            self.envs[key] = str(new_envs[key])

        # Call merge for parent, if all_scopes required
        if all_scopes and self.parent is not None:
            self.parent.merge_envs(new_envs, all_scopes=True)

def template_if_string(val, mapping):
    if val is not None and isinstance(val, str):
        try:
            template = Template(val)
            return template.substitute(mapping)
        except KeyError as e:
            raise Exception(f"Missing key in template substitution: {e}")

    return val

def assert_type(obj, obj_type, message):
    if not isinstance(obj, obj_type):
        raise Exception(message)

def assert_not_none(obj, message):
    if obj is None:
        raise Exception(message)

def assert_not_emptystr(obj, message):
    if obj is None or (isinstance(obj, str) and obj == ""):
        raise Exception(message)

def parse_bool(obj):
    if obj is None:
        raise Exception(f"None value passed to parse_bool")

    if isinstance(obj, bool):
        return obj

    obj = str(obj)

    if obj.lower() in [ "true", "1" ]:
        return True

    if obj.lower() in [ "false", "0" ]:
        return False

    raise Exception(f"Unparseable value ({obj}) passed to parse_bool")

def merge_spec_envs(spec, state, all_scopes=False):
    logger = logging.getLogger(__name__)

    if not isinstance(spec, dict):
        raise Exception("spec passed to merge_spec_envs is not a dictionary")

    if not isinstance(state, ScopeState):
        raise Exception("Invalid ScopeState passed to merge_spec_envs")

    # Extract inline env definitions. Use env vars from state for templating
    envs = spec_extract_value(spec, "env", default={}, template_map=state.envs)
    assert_type(envs, dict, "env is not a dictionary")

    # Extract var definitions from file
    env_files = spec_extract_value(spec, "env_files", default=[], template_map=state.envs)
    assert_type(env_files, list, "env_files is not a list")

    for file in env_files:
        file = str(file)

        if file == "":
            raise Exception("Empty file name specified in env_files")

        with open(file, "r") as file:
            content = yaml.safe_load(file)

        if not isinstance(content, dict):
            raise Exception(f"Yaml read from file ({file}) is not a dictionary")

        # Merge vars in to existing envs dictionary
        for key in content.keys():
            envs[key] = str(content[key])

    state.merge_envs(envs, all_scopes=all_scopes)
    logger.debug(f"envs: {envs}")

def spec_extract_value(spec, key, *, template_map, failemptystr=False, default=None):
    # Check that we have a valid spec
    if spec is None or not isinstance(spec, dict):
        raise Exception(f"spec is missing or is not a dictionary")

    # Check type for template_map
    if template_map is not None and not isinstance(template_map, dict):
        raise Exception("Invalid type passed as template_map")

    # Handle a missing key in the spec
    if key not in spec or spec[key] == None:
        # Key is not present or the value is null/None
        # Return the default, if specified
        if default is not None:
            return default

        # Key is not present or null and no default, so raise an exception
        raise KeyError(f"Missing key \"{key}\" in spec or value is null")

    # Retrieve value
    val = spec[key]

    # string specific processing
    if val is not None and isinstance(val, str):
        # Template the string
        if template_map is not None:
            val = template_if_string(val, template_map)

        # Check if we have an empty string and should fail
        if failemptystr and val == "":
            raise Exception("Value for key \"{key}\" is empty, but a value is required")

    # Perform string substitution for other types
    if template_map is not None and val is not None:
        if isinstance(val, list):
            val = [template_if_string(x, template_map) for x in val]

        if isinstance(val, dict):
            for key in val.keys():
                val[key] = template_if_string(val[key], template_map)

    return val

def process_spec_v1_step_semver(step_name, step, state) -> int:
    logger = logging.getLogger(__name__)

    # Capture step properties
    required = parse_bool(spec_extract_value(step, "required", default=False, template_map=state.envs))
    logger.debug(f"required: {required}")

    sources = spec_extract_value(step, "sources", default=[], template_map=state.envs)
    assert_type(sources, list, "step sources is not a list")
    logger.debug(f"sources: {sources}")

    strip_regex = spec_extract_value(step, "strip_regex", default=["^refs/tags/", "^v"],
        template_map=state.envs)
    assert_type(strip_regex, list, "step strip_regex is not a list")
    logger.debug(f"strip_regex: {strip_regex}")

    # Regex for identifying and splitting semver strings
    # Reference: https://semver.org/
    semver_regex = "^(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\.(?P<patch>0|[1-9]\d*)(?:-(?P<prerelease>(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?(?:\+(?P<buildmetadata>[0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$"

    for env_name in sources:
        env_name = str(env_name)

        if env_name not in state.envs:
            logger.debug(f"Env var {env_name} not present")
            continue

        source = state.envs[env_name]
        logger.info(f"Checking {env_name}/{source}")

        # Strip any components matching strip_regex
        for regex_item in strip_regex:
            source = re.sub(regex_item, "", source)

        logger.debug(f"Source post-regex strip: {source}")

        # Check if this source is a semver match
        result = re.match(semver_regex, source)
        if result is None:
            logger.debug(f"Source ({source}) is not a match")
            continue

        logger.info(f"Semver match on {source}")

        # Assign semver components to environment vars
        env_vars = {
            "SEMVER_ORIG": source,
            "SEMVER_FULL": "" if result[0] is None else result[0],
            "SEMVER_MAJOR": "" if result[1] is None else result[1],
            "SEMVER_MINOR": "" if result[2] is None else result[2],
            "SEMVER_PATCH": "" if result[3] is None else result[3],
            "SEMVER_PRERELEASE": "" if result[4] is None else result[4],
            "SEMVER_BUILDMETA": "" if result[5] is None else result[5]
        }

        # Determine if this is a prerelease
        if env_vars["SEMVER_PRERELEASE"] != "":
            env_vars["SEMVER_IS_PRERELEASE"] = "1"
        else:
            env_vars["SEMVER_IS_PRERELEASE"] = "0"

        print(f"SEMVER version information: {env_vars}")

        # Merge semver vars in to environment vars
        state.merge_envs(env_vars, all_scopes=True)

        return

    # No matches found
    if required:
        raise Exception("No semver matches found")
    else:
        logger.warning("No semver matches found")


def process_spec_v1_step_command(step_name, step, state) -> int:
    logger = logging.getLogger(__name__)

    # Capture relevant properties for this step
    step_type = str(spec_extract_value(step, "type", template_map=state.envs, failemptystr=True))
    # logger.debug(f"type: {step_type}")

    step_shell = parse_bool(spec_extract_value(step, "shell", template_map=state.envs, default=False))
    logger.debug(f"shell: {step_shell}")

    step_capture = str(spec_extract_value(step, "capture", template_map=state.envs, default=""))
    logger.debug(f"capture: {step_capture}")

    step_interpreter = str(spec_extract_value(step, "interpreter", template_map=state.envs, default=""))
    logger.debug(f"interpreter: {step_interpreter}")

    step_command = str(spec_extract_value(step, "command", template_map=None, failemptystr=True))
    logger.debug(f"command: {step_command}")

    # Arguments to subprocess.run
    subprocess_args = {
        "env": state.envs.copy(),
        "stdout": None,
        "stderr": subprocess.STDOUT,
        "shell": step_shell
    }

    # If we're capturing, stdout should come back via pipe
    if step_capture != "":
        subprocess_args["stdout"] = subprocess.PIPE

    # Override interpreter if the type is bash or pwsh
    if step_type == "pwsh":
        step_interpreter = "pwsh -noni -c -"
    elif step_type == "bash":
        step_interpreter = "bash"

    # If an interpreter is defined, this is the executable to call instead
    if step_interpreter != "":
        call_args = step_interpreter
        subprocess_args["text"] = True
        subprocess_args["input"] = step_command
    else:
        call_args = step_command
        subprocess_args["stdin"] = subprocess.DEVNULL

    # If shell is not true, then we need to split the string for the call to subprocess.run
    if not step_shell:
        call_args = shlex.split(call_args)

    logger.debug(f"Call arguments: {call_args}")
    logger.debug(f"Subprocess args: {subprocess_args}")

    sys.stdout.flush()
    proc = subprocess.run(call_args, **subprocess_args)

    # Check if the process failed
    if proc.returncode != 0:
        # If the subprocess was called with stdout PIPE, output it here
        if subprocess_args["stdout"] is not None:
            print(proc.stdout.decode("ascii"))

        raise Exception(f"Process exited with non-zero exit code: {proc.returncode}")

    elif step_capture:
        # If we're capturing output from the step, put it in the environment now
        stdout_capture = proc.stdout.decode("ascii")
        state.merge_envs({step_capture: stdout_capture}, all_scopes=True)
        print(stdout_capture)

def process_spec_v1_step(step_name, step, state) -> int:
    logger = logging.getLogger(__name__)

    # Create a new scope state
    state = ScopeState(parent=state)

    # Merge environment variables in early
    merge_spec_envs(step, state)

    # Get parameters for this step
    step_type = str(spec_extract_value(step, "type", template_map=state.envs, failemptystr=True))
    logger.debug(f"type: {step_type}")

    # Determine which type of step this is and process
    if step_type == "command" or step_type == "pwsh" or step_type == "bash":
        process_spec_v1_step_command(step_name, step, state)
    elif step_type == "semver":
        process_spec_v1_step_semver(step_name, step, state)
    else:
        raise Exception(f"unknown step type: {step_type}")

def process_spec_v1_action(action_name, action, state) -> int:
    logger = logging.getLogger(__name__)

    # Create a new scope state
    state = ScopeState(parent=state)

    # Merge environment variables in early
    merge_spec_envs(action, state)

    # Capture steps for this action
    action_steps = spec_extract_value(action, "steps", default=[], template_map=state.envs)
    assert_type(action_steps, list, "action steps is not a list")
    for item in action_steps:
        if isinstance(item, dict) or isinstance(item, str):
            continue

        raise Exception(f"Invalid value in steps list ({str(item)})")

    # Process steps in action
    for step_ref in action_steps:
        if isinstance(step_ref, str):
            if step_ref == "":
                raise Exception("Empty step reference")

            if step_ref not in state.common.spec["steps"]:
                raise Exception(f"Reference to step that does not exist: {step_name}")

            step_name = step_ref
            step_ref = state.common.spec["steps"][step_name]
        else:
            step_name = spec_extract_value(step_ref, "name", template_map=None, failemptystr=True)

        # Call the processor for this step
        print("")
        print(f"**************** STEP {step_name}")

        process_spec_v1_step(step_name, step_ref, state)

        print("")
        print(f"**************** END STEP {step_name}")
        print("")

def process_spec_v1(spec, action_name) -> int:
    logger = logging.getLogger(__name__)

    # Make sure we have a dictionary for the spec
    assert_type(spec, dict, "Specification is not a dictionary")

    # State for processing
    state = ScopeState()
    state.common.spec = spec

    # Make sure we have a valid action name
    assert_not_emptystr(action_name, "Invalid or empty action name specified")

    # Capture global environment variables from spec and merge
    merge_spec_envs(state.common.spec, state)

    # Read in steps
    steps = spec_extract_value(state.common.spec, "steps", default={}, template_map=None)
    assert_type(steps, dict, "global steps is not a dictionary")

    # Read in actions
    actions = spec_extract_value(state.common.spec, "actions", default={}, template_map=None)
    assert_type(actions, dict, "global actions is not a dictionary")

    # Make sure the action name exists
    if action_name not in actions:
        raise Exception(f"Action name does not exist: {action_name}")

    # Process action
    print("")
    print(f"**************** ACTION {action_name}")
    process_spec_v1_action(action_name, actions[action_name], state)
    print("**************** END ACTION")
    print("")

