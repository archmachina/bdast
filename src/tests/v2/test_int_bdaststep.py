
import pytest
import bdast
from bdast import bdast_v2
from bdast.exception import BdastRunException
from bdast.exception import BdastLoadException
from bdast.exception import BdastArgumentException

class TestBdastStep:
    def test_depends_on1(self):
        step_def = {
            "name": "test",
            "depends_on": [
                "test",
                "test",
                "+build"
            ]
        }

        action_state = bdast.bdast_v2.ActionState("action_test", "")
        step = bdast.bdast_v2.BdastStep(step_def, action_state)

        assert len(step.depends_on) == 2
        assert len(step.required_by) == 0
        assert len(step.before) == 0
        assert len(step.after) == 0

        assert "test" in step.depends_on
        assert "build:end" in step.depends_on

    def test_required_by1(self):
        step_def = {
            "name": "test",
            "required_by": [
                "test",
                "test",
                "+build"
            ]
        }

        action_state = bdast.bdast_v2.ActionState("action_test", "")
        step = bdast.bdast_v2.BdastStep(step_def, action_state)

        assert len(step.depends_on) == 0
        assert len(step.required_by) == 2
        assert len(step.before) == 0
        assert len(step.after) == 0

        assert "test" in step.required_by
        assert "build:begin" in step.required_by

    def test_before1(self):
        step_def = {
            "name": "test",
            "before": [
                "test",
                "test",
                "+build"
            ]
        }

        action_state = bdast.bdast_v2.ActionState("action_test", "")
        step = bdast.bdast_v2.BdastStep(step_def, action_state)

        assert len(step.depends_on) == 0
        assert len(step.required_by) == 0
        assert len(step.before) == 2
        assert len(step.after) == 0

        assert "test" in step.before
        assert "build:begin" in step.before

    def test_after1(self):
        step_def = {
            "name": "test",
            "after": [
                "test",
                "test",
                "+build"
            ]
        }

        action_state = bdast.bdast_v2.ActionState("action_test", "")
        step = bdast.bdast_v2.BdastStep(step_def, action_state)

        assert len(step.depends_on) == 0
        assert len(step.required_by) == 0
        assert len(step.before) == 0
        assert len(step.after) == 2

        assert "test" in step.after
        assert "build:end" in step.after

    def test_during1(self):
        step_def = {
            "name": "test",
            "during": [
                "test",
            ]
        }

        action_state = bdast.bdast_v2.ActionState("action_test", "")
        with pytest.raises(BdastRunException):
            step = bdast.bdast_v2.BdastStep(step_def, action_state)

    def test_during2(self):
        step_def = {
            "name": "test",
            "during": [
                "+build"
            ]
        }

        action_state = bdast.bdast_v2.ActionState("action_test", "")
        step = bdast.bdast_v2.BdastStep(step_def, action_state)

        assert len(step.depends_on) == 1
        assert len(step.required_by) == 1
        assert len(step.before) == 0
        assert len(step.after) == 0

        assert "build:begin" in step.depends_on
        assert "build:end" in step.required_by

