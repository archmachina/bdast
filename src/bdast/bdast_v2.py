"""
"""

import logging
import os
import re
import shlex
import subprocess
import sys
import copy
import glob

import requests
import yaml
import obslib

from .exception import BdastArgumentException
from .exception import BdastLoadException
from .exception import BdastRunException

logger = logging.getLogger(__name__)

EVAL_IGNORE_VARS = ["bdast", "env"]

def val_arg(val, message):
    if not val:
        raise BdastArgumentException(message)


def val_load(val, message):
    if not val:
        raise BdastLoadException(message)


def val_run(val, message):
    if not val:
        raise BdastRunException(message)


def log_raw(msg):
    print(msg, flush=True)


def get_obslib_session(template_vars, bdast_vars=None):

    # Validate incoming parameters
    val_arg(isinstance(template_vars, dict), "Invalid template_vars passed to get_obslib_session")
    val_arg(isinstance(bdast_vars, (dict, type(None))), "Invalid bdast_vars passed to get_obslib_session")

    if bdast_vars is None:
        bdast_vars = {}

    # Make sure the template vars have some mandatory fields
    template_vars = template_vars.copy()
    template_vars["env"] = os.environ.copy()
    template_vars["bdast"] = bdast_vars

    return obslib.Session(template_vars, ignore_list=EVAL_IGNORE_VARS)

def process_step_nop(action_state, impl_config):

    # Validate incoming parameters
    val_arg(isinstance(action_state, ActionState), "Invalid action state passed to process_step_nop")
    val_arg(isinstance(impl_config, dict), "Invalid impl config passed to process_step_nop")

    # Nothing to actually do, since 'nop'

    # Validate no remaining keys on configuration
    val_run(len(impl_config)  == 0, f"Expected an empty configuration for nop. Found keys: {impl_config.keys()}")


def process_step_url(action_state, impl_config):

    # Headers - headers for the request
    headers = obslib.extract_property(impl_config, "headers", on_missing=None)
    headers = action_state.session.resolve(headers, (dict, type(None)), on_none={})
    for key in headers:
        headers[key] = action_state.session.resolve(headers[key], str)

    # Url - endpoint to communicate with
    url = obslib.extract_property(impl_config, "url")
    url = action_state.session.resolve(url, str)

    # Method - request method (get, post, etc.)
    method = obslib.extract_property(impl_config, "method", on_missing="post")
    method = action_state.session.resolve(method, str)

    # Body - content to send with the request
    body = obslib.extract_property(impl_config, "body", on_missing=None)
    body = action_state.session.resolve(body, (str, type(None)))

    # Store - variable to store the result
    store = obslib.extract_property(impl_config, "store", on_missing=None)
    store = action_state.session.resolve(store, (str, type(None)))

    # Perform request
    args = {
        "method": method,
        "url": url,
        "timeout": (10, 30),
        "headers": headers,
    }

    if body is not None:
        args["data"] = body

    response = requests.request(**args)
    response.raise_for_status()

    logger.info("Request successful")
    logger.debug("Response code: %s", response.status_code)
    logger.debug("Response text: %s", response.text)

    # Only store result if requested
    if store is not None and store != "":
        # What we should provide back to the caller
        result = {
            "text": response.text,
            "headers": response.headers,
            "status_code": response.status_code,
        }

        # Update vars with the request result
        action_state.update_vars({ store: result })

def process_step_semver(action_state, impl_config):

    # Check incoming parameters
    val_arg(isinstance(action_state, ActionState), "Invalid action state passed to process_spec_semver")
    val_arg(isinstance(impl_config, dict), "Invalid impl config passed to process_spec_semver")

    # Required - whether a result is required
    required = obslib.extract_property(impl_config, "required", on_missing=False)
    required = action_state.session.resolve(required, bool)

    # store - target variable for storing the semver information
    store = obslib.extract_property(impl_config, "store")
    store = action_state.session.resolve(store, str)

    if store == "":
        raise BdastRunException("store must have a value")

    # Sources - where to source the semver values
    sources = obslib.extract_property(impl_config, "sources", on_missing=None)
    sources = action_state.session.resolve(sources, (list, type(None)), depth=0, on_none=[])
    sources = [action_state.session.resolve(x, str) for x in sources]

    # Content to remove from the source prior to regex checking
    discard_regex = obslib.extract_property(impl_config, "discard", on_missing=["^refs/tags/"])
    discard_regex = action_state.session.resolve(discard_regex, (list, type(None)), depth=0, on_none=[])
    discard_regex = [action_state.session.resolve(x, str) for x in discard_regex]

    ignore_regex = obslib.extract_property(impl_config, "ignore", on_missing=["^v"])
    ignore_regex = action_state.session.resolve(ignore_regex, (list, type(None)), depth=0, on_none=[])
    ignore_regex = [action_state.session.resolve(x, str) for x in ignore_regex]

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

        # Strip any 'discard' components
        post_discard_source = source
        for regex_item in discard_regex:
            post_discard_source = re.sub(regex_item, "", post_discard_source)

        logger.debug("Source after discard strip: %s", post_discard_source)

        # Strip any 'ignore' components
        post_ignore_source = post_discard_source
        for regex_item in ignore_regex:
            post_ignore_source = re.sub(regex_item, "", post_ignore_source)

        logger.debug("Source after ignore strip: %s", post_ignore_source)

        # Check if this source is a semver match
        result = re.match(semver_regex, post_ignore_source)
        if result is None:
            logger.debug("Source (%s) is not a match", post_ignore_source)
            continue

        logger.info("Semver match on %s", post_ignore_source)

        # Assign semver components to environment vars
        result = {
            "source": source,
            "original": post_discard_source,
            "post_discard": post_discard_source,
            "post_ignore": post_ignore_source,
            "full": "" if result[0] is None else result[0],
            "major": "" if result[1] is None else result[1],
            "minor": "" if result[2] is None else result[2],
            "patch": "" if result[3] is None else result[3],
            "prerelease": "" if result[4] is None else result[4],
            "buildmeta": "" if result[5] is None else result[5],
            "is_prerelease": result[4] is not None,
        }

        log_raw(f"SEMVER version information: {result}")

        # Merge semver vars in to environment vars
        action_state.update_vars({ store: result })

        return

    # No matches found
    if required:
        raise BdastRunException("No semver matches found")

    logger.warning("No semver matches found")


def process_step_command(action_state, impl_config, step_type):

    # Check incoming parameters
    val_arg(isinstance(action_state, ActionState), "Invalid ActionState passed to process_step_command")
    val_arg(isinstance(impl_config, dict), "Invalid impl config passed to process_step_command")
    val_arg(isinstance(step_type, str), "Invalid step_type passed to process_step_command")

    # Shell - Whether to use shell parsing for the command
    shell = obslib.extract_property(impl_config, "shell", on_missing=False)
    shell = action_state.session.resolve(shell, bool)

    # Capture - whether to capture the command output
    capture = obslib.extract_property(impl_config, "capture", on_missing=None)
    capture = action_state.session.resolve(capture, (str, type(None)))

    # Capture_strip - whether to run 'strip' against the output
    capture_strip = obslib.extract_property(impl_config, "capture_strip", on_missing=False)
    capture_strip = action_state.session.resolve(capture_strip, bool)

    # Command line
    # This is mandatory
    cmd = obslib.extract_property(impl_config, "cmd")
    cmd = action_state.session.resolve(cmd, str)

    # Environment variables
    new_envs = obslib.extract_property(impl_config, "env", on_missing=None)
    new_envs = action_state.session.resolve(new_envs, (dict, type(None)), on_none={})
    for key in new_envs:
        new_envs[key] = action_state.session.resolve(new_envs[key], str)

    envs = os.environ.copy()
    envs.update(new_envs)

    # Arguments to subprocess.run
    subprocess_args = {
        "env": envs,
        "stdout": None,
        "stderr": subprocess.STDOUT,
        "shell": shell,
        "text": True,
    }

    # If we're capturing, stdout should come back via pipe
    if capture is not None and capture != "":
        subprocess_args["stdout"] = subprocess.PIPE

    # Override interpreter if the type is bash or pwsh
    if step_type == "command":

        # Interpreter - whether to use a specific interpreter for the command
        # Only extract interpreter key if the type is 'command'
        interpreter = obslib.extract_property(impl_config, "interpreter", on_missing=None)
        interpreter = action_state.session.resolve(interpreter, (str, type(None)))

    elif step_type == "pwsh":
        interpreter = "pwsh -noni -c -"
    elif step_type == "bash":
        interpreter = "bash"
    else:
        raise BdastRunException(f"Unknown cmd type on command: {str(step_type)}")

    # If an interpreter is defined, this is the executable to call instead
    if interpreter is not None and interpreter != "":
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
    debug_args = subprocess_args.copy()
    debug_args["env"] = "*hidden*"
    logger.debug("Subprocess args: %s", debug_args)

    sys.stdout.flush()
    proc = subprocess.run(call_args, check=False, **subprocess_args)

    # Check if the process failed
    if proc.returncode != 0:
        # If the subprocess was called with stdout PIPE, output it here
        if subprocess_args["stdout"] is not None:
            log_raw(str(proc.stdout))

        raise BdastRunException(f"Process exited with non-zero exit code: {proc.returncode}")

    # Capture the output, if requested
    if capture is not None and capture != "":
        stdout_capture = str(proc.stdout)

        if capture_strip:
            stdout_capture = stdout_capture.strip()

        # Update the action state vars with the result of the command
        action_state.update_vars({ capture: stdout_capture })

        log_raw(stdout_capture)


def process_step_block(action_state, impl_config):

    # Check incoming parameters
    val_arg(isinstance(action_state, ActionState), "Invalid ActionState passed to process_step_command")
    val_arg(isinstance(impl_config, dict), "Invalid impl config passed to process_step_command")

    # Extract steps to execute
    steps = obslib.extract_property(impl_config, "steps", on_missing=None)
    steps = action_state.session.resolve(steps, (list, type(None)), depth=0, on_none=[])
    steps = [action_state.session.resolve(x, dict, depth=0) for x in steps]

    # For each of the steps, create a BdastStep
    # Dependencies aren't supported on these steps
    inline_step_count = 1
    for item in steps:
        # Extract the step name (required)
        step_name = obslib.extract_property(item, "name", on_missing=None)
        step_name = action_state.session.resolve(step_name, (str, type(None)))
        if step_name is None:
            step_name = f"__inline_{inline_step_count}"
            inline_step_count = inline_step_count + 1

        # Create a BdastStep
        step_obj = BdastStep(step_name, item, action_state, support_deps=False)

        # Execute the step
        step_obj.run()


def process_step_vars(action_state, impl_config):

    # Check incoming parameters
    val_arg(isinstance(action_state, ActionState), "Invalid ActionState passed to process_step_command")
    val_arg(isinstance(impl_config, dict), "Invalid impl config passed to process_step_command")

    # Extract steps to execute
    set_vars = obslib.extract_property(impl_config, "set", on_missing=None)
    set_vars = action_state.session.resolve(set_vars, (dict, type(None)), depth=0, on_none={})

    # Update vars for action state
    action_state.update_vars(set_vars)


class ActionState:
    def __init__(self, action_name, action_arg):

        # Check incoming parameters
        val_arg(isinstance(action_name, str), "Invalid action name passed to ActionState")
        val_arg(action_name != "", "Empty action name passed to ActionState")
        val_arg(isinstance(action_arg, str), "Invalid action arg passed to ActionState")

        self.action_name = action_name
        self.action_arg = action_arg

        # List of steps that are active in this action
        self.active_step_map = {}

        # Library of all known steps
        self.step_library = {}

        # Vars used in creation of an obslib session for templating
        self._vars = {}

        # Call update_vars to at least make sure a session exists, along with
        # the base env and bdast vars
        self.update_vars({})

    def update_vars(self, new_vars):

        # Check parameters
        val_arg(isinstance(new_vars, dict), "Invalid vars passed to ActionState update_vars")

        # Update vars
        self._vars.update(new_vars)

        # Ensure particular keys are set appropriately
        bdast_vars = {
            "action_name": self.action_name,
            "action_arg": self.action_arg
        }

        # Recreate the template session
        self.session = get_obslib_session(self._vars, bdast_vars)


class BdastStep:
    def __init__(self, step_name, step_def, action_state, support_deps=True):

        # Check incoming parameters
        val_arg(isinstance(step_name, str), "Invalid step name passed to BdastStep")
        val_arg(step_name != "", "Empty step name passed to BdastStep")
        val_arg(isinstance(step_def, dict), "Spec provided to BdastStep is not a dictionary")
        val_arg(isinstance(action_state, ActionState), "Invalid action state passed to BdastStep")

        # Save incoming parameters
        # Duplicate the step definition to allow validation of keys
        step_def = step_def.copy()
        self._step_name = step_name
        self._action_state = action_state
        session = action_state.session

        if support_deps:
            # Extract dependency properties
            self.depends_on = obslib.extract_property(step_def, "depends_on", on_missing=None)
            self.depends_on = session.resolve(self.depends_on, (list, type(None)), depth=0, on_none=[])
            self.depends_on = {session.resolve(x, str) for x in self.depends_on}

            self.required_by = obslib.extract_property(step_def, "required_by", on_missing=None)
            self.required_by = session.resolve(self.required_by, (list, type(None)), depth=0, on_none=[])
            self.required_by = {session.resolve(x, str) for x in self.required_by}

            self.before = obslib.extract_property(step_def, "before", on_missing=None)
            self.before = session.resolve(self.before, (list, type(None)), depth=0, on_none=[])
            self.before = {session.resolve(x, str) for x in self.before}

            self.after = obslib.extract_property(step_def, "after", on_missing=None)
            self.after = session.resolve(self.after, (list, type(None)), depth=0, on_none=[])
            self.after = {session.resolve(x, str) for x in self.after}

        # Extract description
        self.desc = obslib.extract_property(step_def, "desc", on_missing=None)
        self.desc = session.resolve(self.desc, (str, type(None)), on_none="")

        # Extract when
        self.when = obslib.extract_property(step_def, "when", on_missing=None)
        self.when = session.resolve(self.when, (list, str, type(None)), depth=0, on_none=[])
        if isinstance(self.when, str):
            self.when = [self.when]

        self.when = [session.resolve(x, str) for x in self.when]

        # There should be single key or none left on the step.
        # With a single key, this is the command type to run.
        # With no keys remaining, the step is implicitly 'nop'
        val_load(len(step_def) <= 1, f"Expected single key or none for task, found: {step_def.keys()}")

        # If there is no step defined, make it 'nop' with an empty implementation configuration
        if len(step_def) == 0:
            self._step_type = "nop"
            self._impl_config = {}
            return

        # Extract the step type
        self._step_type = list(step_def.keys())[0]

        # Validate step type
        val_load(isinstance(self._step_type, str), "Step name is not a string")
        val_load(self._step_type != "", "Empty step name")

        # Extract the implementation specific configuration
        self._impl_config = obslib.extract_property(step_def, self._step_type)
        self._impl_config = session.resolve(self._impl_config, (dict, type(None)), depth=0, on_none={})

    def run(self):

        # Session from action state
        action_state = self._action_state
        session = action_state.session

        log_raw("")
        msg = f"**************** STEP {self._step_name}"
        if self.desc != "":
            msg = msg + f" : {self.desc}"
        log_raw(msg)

        # Check whether to run this step
        for condition in self.when:
            result = session.resolve("{{" + condition + "}}", bool)
            if not result:
                logger.info("Skipping step due to conditional")
                return

        # Load the specific step type here
        if self._step_type in ("command", "bash", "pwsh"):
            process_step_command(action_state, self._impl_config, self._step_type)
        elif self._step_type == "semver":
            process_step_semver(action_state, self._impl_config)
        elif self._step_type == "url":
            process_step_url(action_state, self._impl_config)
        elif self._step_type == "nop":
            process_step_nop(action_state, self._impl_config)
        elif self._step_type == "block":
            process_step_block(action_state, self._impl_config)
        elif self._step_type == "vars":
            process_step_vars(action_state, self._impl_config)
        else:
            raise BdastRunException(f"unknown step type: {self._step_type}")

        # Make sure the implementation extracted all properties and there are
        # no remaining unknown properties
        val_run(len(self._impl_config) == 0, f"Unknown properties in step config: {self._impl_config.keys()}")

class BdastAction:
    def __init__(self, action_name, action_spec, global_vars, steps):

        # Check incoming values
        val_arg(isinstance(action_name, str), "Invalid action name passed to BdastAction")
        val_arg(action_name != "", "Empty action name passed to BdastAction")
        val_arg(isinstance(action_spec, dict), "Invalid action spec passed to BdastAction")
        val_arg(isinstance(global_vars, dict), "Invalid global vars passed to BdastAction")
        val_arg(isinstance(steps, dict), "Invalid steps passed to BdastAction")

        # Save copies of parameters
        self._action_name = action_name
        self._vars = copy.deepcopy(global_vars)
        self._steps = copy.deepcopy(steps)
        action_spec = copy.deepcopy(action_spec)

        # Create a session based on the accumulated vars
        session = get_obslib_session(self._vars)

        # Extract vars from the action to merge in to the working vars
        action_vars = obslib.extract_property(action_spec, "vars", on_missing=None)
        action_vars = session.resolve(action_vars, (dict, type(None)), depth=0, on_none={})

        # Recreate the session with the merged in vars
        self._vars.update(action_vars)
        session = get_obslib_session(self._vars)

        # Extract steps from the action
        # Steps in the action can be either a string (referencing another step) or
        # a dict (inline step definition)
        action_steps = obslib.extract_property(action_spec, "steps", on_missing=None)
        action_steps = session.resolve(action_steps, (list, type(None)), depth=0, on_none=[])
        action_steps = [session.resolve(x, (dict, str), depth=0) for x in action_steps]
        self._action_steps = action_steps

        # Validate that there are no unknown properties for the action
        val_load(len(action_spec.keys()) == 0, f"Invalid properties on action: {action_spec.keys()}")

    def run(self, action_arg):

        # Validate incoming parameters
        val_arg(isinstance(action_arg, str), "Invalid action arg passed to BdastAction run")

        # Create an ActionState to hold the running state of the action
        action_state = ActionState(self._action_name, action_arg)
        action_state.update_vars(self._vars)

        # Copy known steps to the action state step library
        action_state.step_library.update(copy.deepcopy(self._steps))

        # Work with our own version of action steps
        action_steps = copy.deepcopy(self._action_steps)

        # Convert all inline step definitions to references to steps
        # in the step library
        action_steps = self._convert_inline_steps(action_state, action_steps)

        # Validate the action steps list
        #   Make sure each item in action steps is a string
        #   Make sure each item references a step in the step library
        #   Make sure there are no duplicate references
        seen_steps = set()
        for step_item in action_steps:
            val_run(isinstance(step_item, str), f"Invalid step item in action steps. Found {type(step_item)}")
            val_run(step_item in action_state.step_library, f"Step '{step_item}' does not exist")
            val_run(step_item not in seen_steps, f"Found duplicate step name in action steps: {step_item}")

            seen_steps.add(step_item)

        # Find all steps reachable from the initial step list
        self._find_reachable_steps(action_state, action_steps)

        # Normalise dependencies - Turn all dependencies in to
        # just depends_on references
        self._normalise_dependencies(action_state)

        ########
        # Apply ordering from step_order to steps
        prev_name = None
        for step_name in action_steps:
            if prev_name is not None:
                action_state.active_step_map[step_name].depends_on.add(prev_name)

            prev_name = step_name

        # Run the steps from the active step map
        self._run_active_steps(action_state)

    def _normalise_dependencies(self, action_state):

        # Validate incoming parameters
        val_arg(isinstance(action_state, ActionState), "Invalid action state passed to _normalise_dependencies")

        active_step_map = action_state.active_step_map
        for step_name in active_step_map:
            step_obj = active_step_map[step_name]

            # Add any 'after' references to 'depends_on', it the item exists
            # (after is a weak dependency - Only applies if the target step is going
            # to be run)
            for item in step_obj.after:
                if item in active_step_map:
                    # Make this step depend on the other step
                    step_obj.depends_on.add(item)

            step_obj.after.clear()

            # Convert a 'before' reference on this step to a 'depends_on'
            # reference on the referenced step
            for item in step_obj.before:
                if item in active_step_map:
                    # Make the other step depend on this step
                    active_step_map[item].depends_on.add(step_name)

            step_obj.before.clear()

            # Convert a 'required_by' reference on this step to a 'depends_on'
            # reference on the referenced step
            # This should already be in the active step map as it would have
            # been a reachable step
            for item in step_obj.required_by:
                val_run(item in active_step_map, f"Expected {item} in active step map, but was missing")

                # Make the other step depend on this step
                active_step_map[item].depends_on.add(step_name)

            step_obj.required_by.clear()

    def _find_reachable_steps(self, action_state, action_steps):

        # Validate incoming parameters
        val_arg(isinstance(action_state, ActionState), "Invalid action state passed to _find_reachable_steps")
        val_arg(isinstance(action_steps, list), "Invalid action steps passed to _find_reachable_steps")

        active_step_map = action_state.active_step_map
        step_queue = action_steps.copy()
        while len(step_queue) > 0:
            step_name = step_queue.pop(0)

            if step_name in active_step_map:
                # We've already processed this step_name, so skip
                continue

            # Create a BdastStep and save it in the map
            active_step_map[step_name] = BdastStep(step_name, action_state.step_library[step_name], action_state)

            # Check depends_on and required_by. before and after do not implicitly load
            # a step
            for item in active_step_map[step_name].depends_on:
                step_queue.append(item)

            for item in active_step_map[step_name].required_by:
                step_queue.append(item)

    def _convert_inline_steps(self, action_state, action_steps):

        # Validate incoming parameters
        val_arg(isinstance(action_state, ActionState), "Invalid action state passed to _convert_inline_steps")
        val_arg(isinstance(action_steps, list), "Invalid action steps passed to _convert_inline_steps")

        # For each inline step definition, register it in the step library
        # and convert the entry to a str reference to it
        new_action_steps = []
        inline_step_count = 1
        for step_item in action_steps:

            # Only process 'dict', so an inline step definition
            if not isinstance(step_item, dict):
                new_action_steps.append(step_item)
                continue

            # Extract (/remove) the name from the step definition
            step_name = obslib.extract_property(step_item, "name", on_missing=None)
            step_name = action_state.session.resolve(step_name, (str, type(None)))

            # If it doesn't have a name, create an inline name
            if step_name is None:
                step_name = f"__inline_{inline_step_count}"
                inline_step_count = inline_step_count + 1

            # Check that this step name isn't a global step. Disallow shadowing of
            # global steps as this would just be confusing.
            val_run(step_name not in action_state.step_library, f"Inline step has identical name to global step: {step_name}")

            # Store the inline step in the step_library
            action_state.step_library[step_name] = step_item

            # Add to the new action_steps list
            new_action_steps.append(step_name)

        # Return the new action_steps list
        return new_action_steps

    def _run_active_steps(self, action_state):

        # Validate incoming parameters
        val_arg(isinstance(action_state, ActionState), "Invalid ActionState passed to _process_active_steps")

        active_step_map = action_state.active_step_map
        completed = set()
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

                raise BdastRunException("Could not resolve step dependencies")

            # Run the step
            active_step_map[step_match].run()

            # Record the step as completed
            completed.add(step_match)
            active_step_map.pop(step_match)


class BdastSpec:
    def __init__(self, spec):

        # Check incoming values
        val_arg(isinstance(spec, dict), "Spec supplied to BdastSpec is not a dictionary")

        # Reference to the deserialised specification
        # We'll try to make BdastSpec reusable, though it isn't currently reused
        spec = copy.deepcopy(spec)

        # Create a basic obslib session with no vars
        session = get_obslib_session(template_vars={})

        # Retrieve the global vars - This is only to allow vars to be used in the include directive
        # Leave the vars key in place so it can be used later by _merge_spec
        temp_vars = obslib.extract_property(spec, "vars", on_missing=None, remove=False)
        temp_vars = session.resolve(temp_vars, (dict, type(None)), depth=0, on_none={})

        # Recreate session with the global vars
        session = get_obslib_session(temp_vars)

        # Get a list of includes for this spec
        # Only resolve the root level object to a list, then individually
        # resolve each item to a string
        includes = obslib.extract_property(spec, "include", on_missing=None)
        includes = session.resolve(includes, (list, type(None)), depth=0, on_none=[])
        includes = [session.resolve(x, str) for x in includes]

        self._steps = {}
        self._actions = {}
        self._vars = {}

        for file_glob in includes:
            # Make sure we have a string-type include directive
            val_load(isinstance(file_glob, str), f"Invalid value in vars_file list. Must be string. Found {type(file_glob)}")

            # Load include spec
            matches = glob.glob(file_glob, recursive=True)
            for match in matches:
                with open(match, "r", encoding="utf-8") as file:
                    content = yaml.safe_load(file)

                # Merge vars, steps and actions from this spec
                self._merge_spec(content)

        # Merge our spec last to allow it to override steps, actions and vars
        self._merge_spec(spec)

    def _merge_spec(self, spec):

        # Validate arguments
        val_arg(isinstance(spec, dict), "Invalid spec passed to _merge_spec")

        # Create a basic obslib session with no vars
        session = get_obslib_session(template_vars={})

        # Retrieve the version from the spec
        # Version is mandatory - no missing or none value replacement
        version = obslib.extract_property(spec, "version")
        version = session.resolve(version, str)
        val_load(version in ("2", "2beta", "2alpha"), f"Invalid spec version: {version}")

        # Read the global vars from the spec file
        spec_vars = obslib.extract_property(spec, "vars", on_missing=None)
        spec_vars = session.resolve(spec_vars, (dict, type(None)), depth=0, on_none={})
        self._vars.update(spec_vars)

        # Recreate the session based specifically on this specs vars (not
        # the accumulated vars in self._vars)
        session = get_obslib_session(spec_vars)

        # Read the actions from the spec
        spec_actions = obslib.extract_property(spec, "actions", on_missing=None)
        spec_actions = session.resolve(spec_actions, (dict, type(None)), depth=0, on_none={})
        for key in spec_actions:
            spec_actions[key] = session.resolve(spec_actions[key], dict, depth=0)
        self._actions.update(spec_actions)

        # Read the steps from the spec
        spec_steps = obslib.extract_property(spec, "steps", on_missing=None)
        spec_steps = session.resolve(spec_steps, (dict, type(None)), depth=0, on_none={})
        for key in spec_steps:
            spec_steps[key] = session.resolve(spec_steps[key], (dict, type(None)), depth=0, on_none={})
        self._steps.update(spec_steps)

        # Make sure there are no other keys on this spec
        val_load(len(spec.keys()) == 0, f"Invalid keys on loaded spec: {spec.keys()}")

    def get_action(self, action_name):

        # Validate incoming parameters
        val_arg(isinstance(action_name, str), "Invalid action name passed to get_action")
        val_arg(action_name != "", "Empty action name passed to get_action")
        val_arg(action_name in self._actions, f"Action name '{action_name}' does not exist")

        # Create a new action, that will have a copy of the vars, steps and action
        # definition
        action = BdastAction(
            action_name,
            copy.deepcopy(self._actions[action_name]),
            copy.deepcopy(self._vars),
            copy.deepcopy(self._steps),
        )

        return action


def process_spec(spec_file, action_name, action_arg):

    # Validate arguments
    val_arg(spec_file is not None and spec_file != "", "Specification filename missing")
    val_arg(os.path.isfile(spec_file), "Spec file does not exist or is not a file")
    val_arg(isinstance(action_name, str), "Invalid action name specified")
    val_arg(action_name != "", "Empty action name specified")

    # Make sure action_arg is a string
    action_arg = str(action_arg) if action_arg is not None else ""

    # Load spec file
    logger.info("Loading spec: %s", spec_file)
    with open(spec_file, "r", encoding="utf-8") as file:
        spec = yaml.safe_load(file)

    # Make sure we have a dictionary
    val_load(isinstance(spec, dict), "Parsed specification is not a dictionary")

    # Create bdast spec
    bdast_spec = BdastSpec(spec)
    action = bdast_spec.get_action(action_name)

    # Run the action
    log_raw("")
    log_raw(f"**************** ACTION {action_name}")

    action.run(action_arg)

