"""
"""

import logging
import os
import re
import shlex
import subprocess
import sys
from string import Template

import requests
import yaml

from .bdast_exception import SpecRunException

logger = logging.getLogger(__name__)


class CommonState:
    def __init__(self, spec=None):
        if spec is None:
            spec = {}

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
            raise SpecRunException(
                "Invalid type passed to merge_envs. Must be a dictionary"
            )

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
            raise SpecRunException(f"Missing key in template substitution: {e}") from e

    return val


def log_raw(msg):
    print(msg, flush=True)


def assert_type(obj, obj_type, message):
    if not isinstance(obj, obj_type):
        raise SpecRunException(message)


def assert_not_none(obj, message):
    if obj is None:
        raise SpecRunException(message)


def assert_not_emptystr(obj, message):
    if obj is None or (isinstance(obj, str) and obj == ""):
        raise SpecRunException(message)


def parse_bool(obj) -> bool:
    if obj is None:
        raise SpecRunException("None value passed to parse_bool")

    if isinstance(obj, bool):
        return obj

    obj = str(obj)

    if obj.lower() in ["true", "1"]:
        return True

    if obj.lower() in ["false", "0"]:
        return False

    raise SpecRunException(f"Unparseable value ({obj}) passed to parse_bool")


def merge_spec_envs(spec, state, all_scopes=False):
    if not isinstance(spec, dict):
        raise SpecRunException("spec passed to merge_spec_envs is not a dictionary")

    if not isinstance(state, ScopeState):
        raise SpecRunException("Invalid ScopeState passed to merge_spec_envs")

    # Extract inline env definitions. Use env vars from state for templating
    envs = spec_extract_value(spec, "env", default={}, template_map=state.envs)
    assert_type(envs, dict, "env is not a dictionary")

    # Extract var definitions from file
    env_files = spec_extract_value(
        spec, "env_files", default=[], template_map=state.envs
    )
    assert_type(env_files, list, "env_files is not a list")

    for file in env_files:
        file = str(file)

        if file == "":
            raise SpecRunException("Empty file name specified in env_files")

        with open(file, "r", encoding="utf-8") as file:
            content = yaml.safe_load(file)

        if not isinstance(content, dict):
            raise SpecRunException(f"Yaml read from file ({file}) is not a dictionary")

        # Merge vars in to existing envs dictionary
        for key in content.keys():
            envs[key] = str(content[key])

    state.merge_envs(envs, all_scopes=all_scopes)
    logger.debug("envs: %s", envs)


def spec_extract_value(spec, key, *, template_map, failemptystr=False, default=None):
    # Check that we have a valid spec
    if spec is None or not isinstance(spec, dict):
        raise SpecRunException("spec is missing or is not a dictionary")

    # Check type for template_map
    if template_map is not None and not isinstance(template_map, dict):
        raise SpecRunException("Invalid type passed as template_map")

    # Handle a missing key in the spec
    if key not in spec or spec[key] is None:
        # Key is not present or the value is null/None
        # Return the default, if specified
        if default is not None:
            return default

        # Key is not present or null and no default, so raise an exception
        raise KeyError(f'Missing key "{key}" in spec or value is null')

    # Retrieve value
    val = spec[key]

    # string specific processing
    if val is not None and isinstance(val, str):
        # Template the string
        if template_map is not None:
            val = template_if_string(val, template_map)

        # Check if we have an empty string and should fail
        if failemptystr and val == "":
            raise SpecRunException(
                f'Value for key "{key}" is empty, but a value is required'
            )

    # Perform string substitution for other types
    if template_map is not None and val is not None:
        if isinstance(val, list):
            val = [template_if_string(x, template_map) for x in val]

        if isinstance(val, dict):
            for val_key in val.keys():
                val[val_key] = template_if_string(val[val_key], template_map)

    return val


def process_spec_v1_step_github_release(step, state):
    # Capture step properties
    owner = str(
        spec_extract_value(step, "owner", failemptystr=True, template_map=state.envs)
    )
    logger.debug("owner: %s", owner)

    repo = str(
        spec_extract_value(step, "repo", failemptystr=True, template_map=state.envs)
    )
    logger.debug("repo: %s", repo)

    token = str(
        spec_extract_value(step, "token", failemptystr=True, template_map=state.envs)
    )
    # logger.debug("token: %s", token)
    logger.debug("token: ********")

    payload = str(
        spec_extract_value(step, "payload", failemptystr=True, template_map=state.envs)
    )
    logger.debug("payload: %s", payload)

    api_version = str(
        spec_extract_value(
            step,
            "api_version",
            default="2022-11-28",
            failemptystr=True,
            template_map=state.envs,
        )
    )
    logger.debug("api_version: %s", api_version)

    # Construct URL for post
    url = f"https://api.github.com/repos/{owner}/{repo}/releases"
    logger.info("Repo URL: %s", url)

    # Headers for post
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "Authorization": f"token {token}",
        "Content-Type": "application/json",
        "X-GitHub-Api-Version": api_version,
    }

    logger.debug("Post url: %s", url)
    str_headers = str(headers)
    str_headers = str_headers.replace(token, "********")
    logger.debug("Post headers: %s", str_headers)
    logger.debug("Post payload: %s", payload)

    logger.info("Performing post against github")
    response = requests.post(url, timeout=(10, 30), headers=headers, data=payload)
    response.raise_for_status()

    logger.info("Request successful")
    logger.debug("Response code: %s", response.status_code)
    logger.debug("Response text: %s", response.text)


def process_spec_v1_step_semver(step, state):
    # Capture step properties
    required = parse_bool(
        spec_extract_value(step, "required", default=False, template_map=state.envs)
    )
    logger.debug("required: %s", required)

    sources = spec_extract_value(step, "sources", default=[], template_map=state.envs)
    assert_type(sources, list, "step sources is not a list")
    logger.debug("sources: %s", sources)

    strip_regex = spec_extract_value(
        step, "strip_regex", default=["^refs/tags/", "^v"], template_map=state.envs
    )
    assert_type(strip_regex, list, "step strip_regex is not a list")
    logger.debug("strip_regex: %s", strip_regex)

    # Regex for identifying and splitting semver strings
    # Reference: https://semver.org/
    semver_regex = r"^(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\."
    semver_regex += r"(?P<patch>0|[1-9]\d*)(?:-(?P<prerelease>"
    semver_regex += r"(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)"
    semver_regex += r"(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?"
    semver_regex += r"(?:\+(?P<buildmetadata>[0-9a-zA-Z-]+"
    semver_regex += r"(?:\.[0-9a-zA-Z-]+)*))?$"

    for env_name in sources:
        env_name = str(env_name)

        if env_name not in state.envs:
            logger.debug("Env var %s not present", env_name)
            continue

        source = state.envs[env_name]
        logger.info("Checking %s/%s", env_name, source)

        # Strip any components matching strip_regex
        for regex_item in strip_regex:
            source = re.sub(regex_item, "", source)

        logger.debug("Source post-regex strip: %s", source)

        # Check if this source is a semver match
        result = re.match(semver_regex, source)
        if result is None:
            logger.debug("Source (%s) is not a match", source)
            continue

        logger.info("Semver match on %s", source)

        # Assign semver components to environment vars
        env_vars = {
            "SEMVER_ORIG": source,
            "SEMVER_FULL": "" if result[0] is None else result[0],
            "SEMVER_MAJOR": "" if result[1] is None else result[1],
            "SEMVER_MINOR": "" if result[2] is None else result[2],
            "SEMVER_PATCH": "" if result[3] is None else result[3],
            "SEMVER_PRERELEASE": "" if result[4] is None else result[4],
            "SEMVER_BUILDMETA": "" if result[5] is None else result[5],
        }

        # Determine if this is a prerelease
        if env_vars["SEMVER_PRERELEASE"] != "":
            env_vars["SEMVER_IS_PRERELEASE"] = "1"
            env_vars["SEMVER_IS_PRERELEASE_WORD"] = "true"
        else:
            env_vars["SEMVER_IS_PRERELEASE"] = "0"
            env_vars["SEMVER_IS_PRERELEASE_WORD"] = "false"

        log_raw(f"SEMVER version information: {env_vars}")

        # Merge semver vars in to environment vars
        state.merge_envs(env_vars, all_scopes=True)

        return

    # No matches found
    if required:
        raise SpecRunException("No semver matches found")

    logger.warning("No semver matches found")


def process_spec_v1_step_command(step, state):
    # Capture relevant properties for this step
    step_type = str(
        spec_extract_value(step, "type", template_map=state.envs, failemptystr=True)
    )
    # logger.debug("type: %s", step_type)

    step_shell = parse_bool(
        spec_extract_value(step, "shell", template_map=state.envs, default=False)
    )
    logger.debug("shell: %s", step_shell)

    step_capture = str(
        spec_extract_value(step, "capture", template_map=state.envs, default="")
    )
    logger.debug("capture: %s", step_capture)

    step_interpreter = str(
        spec_extract_value(step, "interpreter", template_map=state.envs, default="")
    )
    logger.debug("interpreter: %s", step_interpreter)

    step_command = str(
        spec_extract_value(step, "command", template_map=None, failemptystr=True)
    )
    logger.debug("command: %s", step_command)

    # Arguments to subprocess.run
    subprocess_args = {
        "env": state.envs.copy(),
        "stdout": None,
        "stderr": subprocess.STDOUT,
        "shell": step_shell,
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

    logger.debug("Call arguments: %s", call_args)
    logger.debug("Subprocess args: %s", subprocess_args)

    sys.stdout.flush()
    proc = subprocess.run(call_args, check=False, **subprocess_args)

    # Check if the process failed
    if proc.returncode != 0:
        # If the subprocess was called with stdout PIPE, output it here
        if subprocess_args["stdout"] is not None:
            log_raw(proc.stdout.decode("ascii"))

        raise SpecRunException(
            f"Process exited with non-zero exit code: {proc.returncode}"
        )

    if step_capture:
        # If we're capturing output from the step, put it in the environment now
        stdout_capture = proc.stdout.decode("ascii")
        state.merge_envs({step_capture: stdout_capture}, all_scopes=True)
        log_raw(stdout_capture)


def process_spec_v1_step(step, state):
    # Create a new scope state
    state = ScopeState(parent=state)

    # Validate action type
    assert_type(step, dict, "Step is not a dictionary")

    # Merge environment variables in early
    merge_spec_envs(step, state)

    # Get parameters for this step
    step_type = str(
        spec_extract_value(step, "type", template_map=state.envs, failemptystr=True)
    )
    logger.debug("type: %s", step_type)

    # Determine which type of step this is and process
    if step_type in ("command", "pwsh", "bash"):
        process_spec_v1_step_command(step, state)
    elif step_type == "semver":
        process_spec_v1_step_semver(step, state)
    elif step_type == "github_release":
        process_spec_v1_step_github_release(step, state)
    else:
        raise SpecRunException(f"unknown step type: {step_type}")


def process_spec_v1_action(action, state):
    # Create a new scope state
    state = ScopeState(parent=state)

    # Validate action type
    assert_type(action, dict, "Action is not a dictionary")

    # Merge environment variables in early
    merge_spec_envs(action, state)

    # Capture steps for this action
    action_steps = spec_extract_value(
        action, "steps", default=[], template_map=state.envs
    )
    assert_type(action_steps, list, "action steps is not a list")
    for item in action_steps:
        if isinstance(item, (dict, str)):
            continue

        raise SpecRunException(f"Invalid value in steps list ({str(item)})")

    # Process steps in action
    for step_ref in action_steps:
        if isinstance(step_ref, str):
            if step_ref == "":
                raise SpecRunException("Empty step reference")

            if step_ref not in state.common.spec["steps"]:
                raise SpecRunException(
                    f"Reference to step that does not exist: {step_ref}"
                )

            step_name = step_ref
            step_ref = state.common.spec["steps"][step_name]
        else:
            step_name = spec_extract_value(
                step_ref, "name", template_map=None, failemptystr=True
            )

        # Call the processor for this step
        log_raw("")
        log_raw(f"**************** STEP {step_name}")

        process_spec_v1_step(step_ref, state)

        log_raw("")
        log_raw(f"**************** END STEP {step_name}")
        log_raw("")


def process_spec_v1(spec, action_name, action_arg):
    # Make sure we have a dictionary for the spec
    assert_type(spec, dict, "Specification is not a dictionary")

    # State for processing
    state = ScopeState()
    state.common.spec = spec

    # Make sure we have a valid action name
    assert_not_emptystr(action_name, "Invalid or empty action name specified")

    # Make sure action_arg is a string
    action_arg = str(action_arg) if action_arg is not None else ""
    state.envs["BDAST_ACTION_ARG"] = action_arg

    # Capture global environment variables from spec and merge
    merge_spec_envs(state.common.spec, state)

    # Read in steps
    steps = spec_extract_value(
        state.common.spec, "steps", default={}, template_map=None
    )
    assert_type(steps, dict, "global steps is not a dictionary")

    # Read in actions
    actions = spec_extract_value(
        state.common.spec, "actions", default={}, template_map=None
    )
    assert_type(actions, dict, "global actions is not a dictionary")

    # Make sure the action name exists
    if action_name not in actions:
        raise SpecRunException(f"Action name does not exist: {action_name}")

    # Process action
    log_raw("")
    log_raw(f"**************** ACTION {action_name}")
    process_spec_v1_action(actions[action_name], state)
    log_raw("**************** END ACTION")
    log_raw("")
