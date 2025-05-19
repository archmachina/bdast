
import pytest
import os
import bdast

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
        assert "env" in action_state._vars
        assert "TESTER" in action_state._vars["env"]
        assert action_state._vars["env"]["TESTER"] == "67"

    def test_env2(self):
        # Check environment variables

        os.environ.pop("TESTER", None)

        action_state = ActionState("test", "")

        assert action_state is not None
        assert "env" in action_state._vars
        assert "TESTER" not in action_state._vars["env"]

    def test_bdast_var1(self):
        # Check for bdast variable and content

        action_state = ActionState("test", "")

        assert "bdast" in action_state._vars

        assert "action_name" in action_state._vars["bdast"]
        assert action_state._vars["bdast"]["action_name"] == "test"

        assert "action_arg" in action_state._vars["bdast"]
        assert action_state._vars["bdast"]["action_arg"] == ""

    def test_bdast_var2(self):
        # Check for bdast variable and content

        action_state = ActionState("other", "arg1")

        assert "bdast" in action_state._vars

        assert "action_name" in action_state._vars["bdast"]
        assert action_state._vars["bdast"]["action_name"] == "other"

        assert "action_arg" in action_state._vars["bdast"]
        assert action_state._vars["bdast"]["action_arg"] == "arg1"

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

        action_state = ActionState("test", "")

        assert "bdast" in action_state._vars

        action_state.update_vars({"bdast": 54})

        assert "bdast" in action_state._vars
        assert isinstance(action_state._vars["bdast"], dict)
        assert "action_name" in action_state._vars["bdast"]
        assert "action_arg" in action_state._vars["bdast"]

    def test_var3(self):
        # Validate env var cannot be overwritten

        action_state = ActionState("test", "")

        # Make sure we're starting without TESTER4
        os.environ.pop("TESTER4", None)

        # Make sure we have env and no TESTER4
        assert "env" in action_state._vars
        assert "TESTER4" not in action_state._vars["env"]

        # Add TESTER4, which doesn't change action_state vars
        os.environ["TESTER4"] = "OTHER4"
        assert "TESTER4" not in action_state._vars["env"]

        # Update vars, which recreates env
        action_state.update_vars({})
        assert "TESTER4" in action_state._vars["env"]
        assert action_state._vars["env"]["TESTER4"] == "OTHER4"

        # Attempt to overwrite env
        action_state.update_vars({"env": 65})

        # Make sure env looks correct
        assert "env" in action_state._vars
        assert isinstance(action_state._vars["env"], dict)
        assert "TESTER4" in action_state._vars["env"]
        assert action_state._vars["env"]["TESTER4"] == "OTHER4"

# TODO testing
# obslib session
# obslib ignoring env vars
# obslib ignoring bdast vars
# session being recreated after vars refresh
# Unresolvable var references
# Circular var references
# Indirect var reference

