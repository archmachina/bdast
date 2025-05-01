"""
"""

import logging
import os
import re
import shlex
import subprocess
import sys
import copy
from string import Template
from enum import Enum

import requests
import yaml
import obslib

from .exception import SpecRunException,SpecLoadException

logger = logging.getLogger(__name__)

class ActionState:
    def __init__(self, action_vars):

        # Check incoming parameters
        if not isinstance(action_vars, dict):
            raise SpecRunException("Invalid action_vars passed to ActionState")

        self.vars = {}
        self.update_vars(action_vars)

    def update_vars(self, new_vars):

        # Check parameters
        if not isinstance(new_vars, dict):
            raise SpecRunException("Invalid vars passed to ActionState update_vars")

        # Update vars
        for name in new_vars:
            self.vars[name] = copy.deepcopy(new_vars[name])

        # Add environment vars
        self.vars["env"] = os.environ.copy()

        # Recreate the template session
        self.session = obslib.Session(template_vars=obslib.eval_vars(self.vars))

def process_spec_step_github_release(action_state, impl_config):

    # Capture step properties
    headers = obslib.extract_property(impl_config, "headers", default={}, optional=True)
    headers = action_state.session.resolve(headers, (list, type(None)))
    if headers is None:
        headers = {}

    # Make sure all headers are str -> str
    temp = {}
    for key in headers:
        temp[str(key)] = str(headers[name])
    headers = temp

    url = obslib.extract_property(impl_config, "url")
    url = action_state.session.resolve(url, str)

    method = obslib.extract_property(impl_config, "method", default="post", optional=True)
    method = action_state.session.resolve(method, str)

    body = obslib.extract_property(impl_config, "body", default="", optional=True)
    body = action_state.session.resolve(body, str)

    response = requests.post(url, timeout=(10, 30), headers=headers, data=payload)
    response.raise_for_status()

    logger.info("Request successful")
    logger.debug("Response code: %s", response.status_code)
    logger.debug("Response text: %s", response.text)

def process_spec_step_semver(action_state, impl_config):

    # Capture step properties
    required = obslib.extract_property(impl_config, "required", default=False, optional=True)
    required = action_state.session.resolve(required, bool)

    sources = obslib.extract_property(impl_config, "sources", default=[], optional=True)
    sources = action_state.session.resolve(sources, (list, type(None)))
    if sources is None:
        sources = []

    strip_regex = obslib.extract_property(impl_config, "strip_regex", default=["^refs/tags/", "^v"], optional=True)
    strip_regex = action_state.session.resolve(strip_regex, (list, type(None)))

    # Regex for identifying and splitting semver strings
    # Reference: https://semver.org/
    semver_regex = r"^(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\."
    semver_regex += r"(?P<patch>0|[1-9]\d*)(?:-(?P<prerelease>"
    semver_regex += r"(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)"
    semver_regex += r"(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?"
    semver_regex += r"(?:\+(?P<buildmetadata>[0-9a-zA-Z-]+"
    semver_regex += r"(?:\.[0-9a-zA-Z-]+)*))?$"

    for source in sources:
        logger.info("Checking %s", source)

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

def process_step_command(action_state, impl_config, step_type):

    # Check incoming parameters
    if not isinstance(action_state, ActionState):
        raise SpecRunException("Invalid ActionState passed to BdastStepCommand run")

    # Shell - Whether to use shell parsing for the command
    shell = obslib.extract_property(impl_config, "shell", default=False, optional=True)
    shell = action_state.session.resolve(shell, bool)

    # Interpreter - whether to use a specific interpreter for the command
    interpreter = obslib.extract_property(impl_config, "interpreter", default="", optional=True)
    interpreter = action_state.session.resolve(interpreter, str)

    # Capture - whether to capture the command output
    capture = obslib.extract_property(impl_config, "capture", default="", optional=True)
    capture = action_state.session.resolve(capture, (str, type(None)))
    if capture is None:
        capture = ""

    # Capture_strip - whether to run 'strip' against the output
    capture_strip = obslib.extract_property(impl_config, "capture_strip", default=False, optional=True)
    capture_strip = action_state.session.resolve(capture_strip, bool)

    # Command line
    cmd = obslib.extract_property(impl_config, "cmd")
    cmd = action_state.session.resolve(cmd, str)

    # Environment variables
    new_envs = obslib.extract_property(impl_config, "envs", default={}, optional=True)
    new_envs = action_state.session.resolve(new_envs, (dict, type(None)))
    if new_envs is None:
        new_envs = {}

    envs = os.environ.copy()
    for name in new_envs:
        envs[name] = str(new_envs[name])

    # Arguments to subprocess.run
    subprocess_args = {
        "env": envs,
        "stdout": None,
        "stderr": subprocess.STDOUT,
        "shell": shell,
        "text": True,
    }

    # If we're capturing, stdout should come back via pipe
    if capture != "":
        subprocess_args["stdout"] = subprocess.PIPE

    # Override interpreter if the type is bash or pwsh
    if step_type == "command":
        pass
    elif step_type == "pwsh":
        interpreter = "pwsh -noni -c -"
    elif step_type == "bash":
        interpreter = "bash"
    elif step_type != "":
        raise SpecRunException(f"Unknown cmd type on command: {step_type}")

    # If an interpreter is defined, this is the executable to call instead
    if interpreter != "":
        call_args = interpreter
        subprocess_args["input"] = cmd
    else:
        call_args = cmd
        subprocess_args["stdin"] = subprocess.DEVNULL

    # If we're not using shell interpretation, then split the command in to
    # a list of strings
    if not shell:
        call_args = shlex.split(call_args)

    logger.debug("Call arguments: %s", call_args)
    logger.debug("Subprocess args: %s", subprocess_args)

    sys.stdout.flush()
    proc = subprocess.run(call_args, check=False, **subprocess_args)

    # Check if the process failed
    if proc.returncode != 0:
        # If the subprocess was called with stdout PIPE, output it here
        if subprocess_args["stdout"] is not None:
            log_raw(str(proc.stdout))

        raise SpecRunException(f"Process exited with non-zero exit code: {proc.returncode}")

    if capture != "":
        # If we're capturing output from the step, put it in the environment now
        stdout_capture = str(proc.stdout)

        if capture_strip:
            stdout_capture = stdout_capture.strip()

        action_state.update_vars({ capture: stdout_capture })

        log_raw(stdout_capture)


class BdastStepSemver:
    def __init__(self, step_def):

        # Check incoming parameters
        if not isinstance(step_def, dict):
            raise SpecRunException("Invalid step definition passed to BdastStepSemver")


    def run(self, action_state):

        # Check incoming parameters
        if not isinstance(action_state, ActionState):
            raise SpecRunException("Invalid ActionState passed to BdastStepSemver run")


class BdastStepNop:
    def __init__(self, step_def):

        # Check incoming parameters
        if not isinstance(step_def, dict):
            raise SpecRunException("Invalid step definition passed to BdastStepNop")

    def run(self, action_state):

        # Check incoming parameters
        if not isinstance(action_state, ActionState):
            raise SpecRunException("Invalid ActionState passed to BdastStepNop run")

class BdastStep:
    def __init__(self, step_def, session):

        # Check incoming parameters
        if not isinstance(step_def, dict):
            raise SpecRunException("Spec provided to BdastStep is not a dictionary")

        if not isinstance(session, obslib.Session):
            raise SpecRunException("Invalid obslib Session passed to BdastStep")

        step_def = step_def.copy()

        # Extract dependency properties
        self.depends_on = obslib.extract_property(step_def, "depends_on", default=[], optional=True)
        self.depends_on = session.resolve(self.depends_on, (list, type(None)))
        if self.depends_on is None:
            self.depends_on = []
        self.depends_on = set([obslib.coerce_value(x, str) for x in self.depends_on])

        self.required_by = obslib.extract_property(step_def, "required_by", default=[], optional=True)
        self.required_by = session.resolve(self.required_by, (list, type(None)))
        if self.required_by is None:
            self.required_by = []
        self.required_by = set([obslib.coerce_value(x, str) for x in self.required_by])

        self.before = obslib.extract_property(step_def, "before", default=[], optional=True)
        self.before = session.resolve(self.before, (list, type(None)))
        if self.before is None:
            self.before = []
        self.before = set([obslib.coerce_value(x, str) for x in self.before])

        self.after = obslib.extract_property(step_def, "after", default=[], optional=True)
        self.after = session.resolve(self.after, (list, type(None)))
        if self.after is None:
            self.after = []
        self.after = set([obslib.coerce_value(x, str) for x in self.after])

        # There should be a single key left on the step, which will
        # be the step type to run.
        if len(step_def) < 1:
            raise SpecLoadException("Missing step type on step")

        if len(step_def) > 1:
            raise SpecLoadException(f"Too many keys remaining on step. Unknown step type. Keys: {step_def.keys()}")

        # Extract the step type
        self._step_type = list(step_def.keys())[0]
        if not isinstance(self._step_type, str) or self._step_type == "":
            raise SpecLoadException("Empty or non-string step name on step")

        # Extract the implementation specific configuration
        self._impl_config = obslib.extract_property(step_def, self._step_type, default={})
        self._impl_config = session.resolve(self._impl_config, (dict, type(None)), depth=0)
        if self._impl_config is None:
            self._impl_config = {}

    def run(self, action_state):

        # Check incoming parameters
        if not isinstance(action_state, ActionState):
            raise SpecRunException("Invalid ActionState passed to BdastStep run")

        # Load the specific step type here
        if self._step_type in ("command", "bash", "pwsh"):
            process_step_command(action_state, self._impl_config, self._step_type)
        elif self._step_type == "semver":
            process_step_semver(action_state, self._impl_config)
        elif self._step_type == "nop":
            process_step_nop(action_state, self._impl_config)
        else:
            raise SpecRunException(f"unknown step type: {self._step_type}")

        # Make sure the implementation extracted all properties and there are
        # no remaining unknown properties
        if len(self._impl_config) > 0:
            raise SpecLoadException(f"Unknown properties in step config: {step_subobj.keys()}")


class BdastSpec:
    def __init__(self, spec):

        # Check incoming values
        if not isinstance(spec, dict):
            raise SpecRunException("Spec supplied to BdastSpec is not a dictionary")

        # Reference to the deserialised specification
        self._spec = copy.deepcopy(spec)

        # Create a basic obslib session with no vars
        self._session = obslib.Session(template_vars={})

        # Read the global vars from the spec file
        self._vars = obslib.extract_property(self._spec, "vars", default={}, optional=True)
        self._vars = self._session.resolve(self._vars, (dict, type(None)), depth=0)
        if self._vars is None:
            self._vars = {}

        # TODO: Read vars from a file

        # Create a new obslib session with vars read from the spec and files
        self._session = obslib.Session(template_vars=obslib.eval_vars(self._vars))

        # Read the actions from the spec
        self._actions = obslib.extract_property(self._spec, "actions", default={}, optional=True)
        self._actions = self._session.resolve(self._actions, (dict, type(None)), depth=1)
        if self._actions is None:
            self._actions = {}

        # Read the steps from the spec
        self._steps = obslib.extract_property(self._spec, "steps", default={}, optional=True)
        self._steps = self._session.resolve(self._steps, (dict, type(None)), depth=1)
        if self._steps is None:
            self._steps = {}

    def run(self, action_name, action_arg):

        # Check incoming values
        if not isinstance(action_name, str) or action_name == "":
            raise SpecRunException("Invalid action name passed to SpecAction")

        if not isinstance(action_arg, str):
            raise SpecRunException("Invalid action arg passed to SpecAction")

        # Retrieve the action. Make it a copy so we can check for invalid properties
        # without changing the original
        if action_name not in self._actions:
            raise SpecLoadException(f"Action name '{action_name}' does not exist")

        action = copy.deepcopy(self._actions[action_name])

        # Extract vars from the action to merge in to the working vars
        action_vars = obslib.extract_property(action, "vars", default={}, optional=True)
        action_vars = self._session.resolve(action_vars, (dict, type(None)), depth=0)
        if action_vars is None:
            action_vars = {}

        # Extract steps from the action
        action_steps = obslib.extract_property(action, "steps", default=[], optional=True)
        action_steps = self._session.resolve(action_steps, (list, type(None)), depth=1)
        if action_steps is None:
            action_steps = []

        # Validate that there are no unknown properties for the action
        if len(action.keys()) > 0:
            raise SpecLoadException(f"Invalid properties on action: {action.keys()}")

        ########
        # Here we will check for duplicate step name references (seen_step_names), preserve the
        # order of steps from the action (step_order), create a queue for processing dependencies
        # (step_queue), and create a working copy of the global steps, which includes the
        # ephemeral steps (step_library)
        seen_step_names = set()
        step_order = []
        step_queue = []
        step_library = self._steps.copy()

        for step_item in action_steps:

            if isinstance(step_item, str):

                # If it's a string, it's a reference to a global step
                step_name = step_item

                # Make sure the step name exists globally
                # Intentionally check 'self._steps' as we want to avoid check against names defined inline
                if step_item not in self._steps:
                    raise SpecLoadException(f"Step '{step_item}' does not exist")

            elif isinstance(step_item, dict):

                # If it's a dict, then it is an inline definition of a step
                # Extract (/remove) the name from the step definition
                step_name = obslib.extract_property(step_item, "name")
                step_name = self._session.resolve(step_name, str)

                # Check that this step name isn't a global step. Disallow shadowing of
                # global steps as this would just be confusing.
                if step_name in self._steps:
                    raise SpecLoadException(f"Inline step has identical name to global step: {step_name}")

                # Store the inline step in the step_library
                step_library[step_name] = step_item

            else:
                raise SpecLoadException(f"Invalid step defined in action with type {type(step_item)}")

            # Make sure there are no duplicate step references
            # This is because a step will implicitly depend on the prior when defined in the
            # action steps, so duplicate names will create an unresolvable set of dependencies
            if step_name in seen_step_names:
                raise SpecLoadException(f"Duplicate step name reference in action: {step_name}")

            seen_step_names.add(step_name)

            # Store the name in step_order, so that dependencies can be updated later
            step_queue.append(step_name)
            step_order.append(step_name)

        ########
        # Find all reachable steps and ensure they are present in the active_step_map
        # Also, create a BdastStep for each of the reachable steps (in active_step_map)
        active_step_map = {}
        while len(step_queue) > 0:
            step_name = step_queue.pop(0)

            # Make sure this step has a definition
            if step_name not in step_library:
                raise SpecLoadException(f"Reference to non-existant step: {step_name}")

            if step_name in active_step_map:
                # We've already processed this step_name, so skip
                continue

            # Create a BdastStep and save it in the map
            active_step_map[step_name] = BdastStep(step_library[step_name], self._session)

            # Check depends_on and required_by. before and after do not implicitly load
            # a step
            for item in active_step_map[step_name].depends_on:
                step_queue.append(item)

            for item in active_step_map[step_name].required_by:
                step_queue.append(item)

        # Now we have active_step_map, which includes all of the reachable steps

        ########
        # Normalise all of the dependencies and dependents for each step
        #
        # Move all of the dependencies to 'depends_on' to make later processing
        # easier
        for step_name in active_step_map:
            step_obj = active_step_map[step_name]

            # Add any 'after' references to 'depends_on', it the item exists
            # (after is a weak dependency - Only applies if the target step is going
            # to be run)
            for item in step_obj.after:
                if item in active_step_map:
                    step_obj.depends_on.add(item)

            step_obj.after.clear()

            # Convert a 'before' reference on this step to a 'depends_on'
            # reference on the referenced step
            for item in step_obj.before:
                if item in active_step_map:
                    active_step_map[item].depends_on.add(step_name)

            step_obj.before.clear()

            # Convert a 'required_by' reference on this step to a 'depends_on'
            # reference on the referenced step
            for item in step_obj.required_by:
                if item in active_step_map:
                    active_step_map[item].depends_on.add(step_name)

            step_obj.required_by.clear()

        ########
        # Apply ordering from step_order to steps
        prev_name = None
        for step_name in step_order:
            if prev_name is not None:
                active_step_map[step_name].depends_on.add(prev_name)

            prev_name = step_name

        ########
        # Process each step
        completed = set()
        action_state = ActionState(self._vars)
        while len(active_step_map) > 0:
            # Find a step that can be run
            step_match = None

            for step_name in active_step_map:
                step_obj = active_step_map[step_name]

                # Make sure any completed steps are removed from dependencies
                step_obj.depends_on.difference_update(completed)

                if len(step_obj.depends_on) == 0:
                    # Found a step that can be run
                    step_match = step_name
                    break

            # If we found nothing to run, then there may be a circular dependency
            if step_match is None:
                log_raw("Found steps with unresolvable dependencies:")
                for step_name in active_step_map:
                    log_raw(f"{step_name}: {active_step_map[step_name].depends_on}")

                raise SpecRunException(f"Could not resolve step dependencies")

            # Run the step
            log_raw("")
            log_raw(f"**************** STEP {step_match}")

            active_step_map[step_match].run(action_state)

            log_raw("")
            log_raw(f"**************** END STEP {step_match}")
            log_raw("")

            # Record the step as completed
            completed.add(step_match)
            active_step_map.pop(step_match)


def log_raw(msg):
    print(msg, flush=True)


def process_spec(spec_file, action_name, action_arg):

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

    # Make sure we have a valid action name
    if not isinstance(action_name, str) or action_name == "":
        raise SpecRunException("Invalid or empty action name specified")

    # Make sure action_arg is a string
    action_arg = str(action_arg) if action_arg is not None else ""

    # Create bdast spec
    bdast_spec = BdastSpec(spec)

    # Run the action
    log_raw("")
    log_raw(f"**************** ACTION {action_name}")

    bdast_spec.run(action_name, action_arg)

    log_raw("**************** END ACTION")
    log_raw("")

