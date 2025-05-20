
import pytest
import os
import bdast
import jinja2

from bdast import bdast_v2
from bdast.bdast_v2 import ActionState

from bdast.exception import BdastRunException
from bdast.exception import BdastLoadException
from bdast.exception import BdastArgumentException

class TestActionState:
    def test_param1(self):
        # Check invalid action name

        with pytest.raises(BdastArgumentException):
            action_state = ActionState(None, "")

    def test_param2(self):
        # Check invalid action name

        with pytest.raises(BdastArgumentException):
            action_state = ActionState("", "")

    def test_param3(self):
        # Check invalid action arg

        with pytest.raises(BdastArgumentException):
            action_state = ActionState("test", None)

    def test_param4(self):
        # Check valid parameters

        action_state = ActionState("test", "")

        assert action_state is not None

    def test_env1(self):
        # Check environment variables

        os.environ["TESTER"] = "67"

        action_state = ActionState("test", "")

        assert action_state is not None
        assert action_state.session.resolve("{{ env.TESTER }}") == "67"

    def test_env2(self):
        # Check environment variables

        os.environ.pop("TESTER", None)

        action_state = ActionState("test", "")

        assert action_state is not None

        with pytest.raises(jinja2.exceptions.UndefinedError):
            action_state.session.resolve("{{ env.TESTER }}") == "67"

    def test_bdast_var1(self):
        # Check for bdast variable and content

        action_state = ActionState("test", "")

        action_state.session.resolve("{{ bdast.action_name }}") == "test"
        action_state.session.resolve("{{ bdast.action_arg }}") == ""

    def test_bdast_var2(self):
        # Check for bdast variable and content

        action_state = ActionState("other", "arg1")

        action_state.session.resolve("{{ bdast.action_name }}") == "other"
        action_state.session.resolve("{{ bdast.action_arg }}") == "arg1"

    def test_var1(self):
        # Check presence of var

        action_state = ActionState("test", "")

        assert "other" not in action_state._vars

        action_state.update_vars({"other": 54})

        assert "other" in action_state._vars
        assert isinstance(action_state._vars["other"], int)
        assert action_state._vars["other"] == 54

    def test_var2(self):
        # Validate bdast var cannot be overwritten

        action_state = ActionState("test", "arg1")

        assert action_state.session.resolve("{{ bdast.action_name }}") == "test"
        assert action_state.session.resolve("{{ bdast.action_arg }}") == "arg1"

        action_state.update_vars({"bdast": 54})

        assert action_state.session.resolve("{{ bdast.action_name }}") == "test"
        assert action_state.session.resolve("{{ bdast.action_arg }}") == "arg1"

    def test_var3(self):
        # Validate env var cannot be overwritten

        action_state = ActionState("test", "")

        # Make sure we're starting without TESTER4
        os.environ.pop("TESTER4", None)

        # Make sure we have env and no TESTER4
        with pytest.raises(jinja2.exceptions.UndefinedError):
            action_state.session.resolve("{{ env.TESTER4 }}")

        # Add TESTER4, which doesn't change action_state vars
        os.environ["TESTER4"] = "OTHER4"
        with pytest.raises(jinja2.exceptions.UndefinedError):
            action_state.session.resolve("{{ env.TESTER4 }}")

        # Update vars, which recreates env
        action_state.update_vars({})
        assert action_state.session.resolve("{{ env.TESTER4 }}") == "OTHER4"

        # Attempt to overwrite env
        action_state.update_vars({"env": 65})

        # Make sure env looks correct
        assert action_state.session.resolve("{{ env.TESTER4 }}") == "OTHER4"

# TODO testing
# obslib session
# obslib ignoring env vars
# obslib ignoring bdast vars
# session being recreated after vars refresh
# Unresolvable var references
# Circular var references
# Indirect var reference

