
import pytest
import bdast
from bdast import bdast_v2
from bdast.exception import BdastRunException
from bdast.exception import BdastLoadException
from bdast.exception import BdastArgumentException

class TestProcessStepNop:
    def test_1(self):
        action_state = bdast_v2.ActionState("test", "")

        bdast.bdast_v2.process_step_nop(action_state, {})

        # Doesn't raise anything or return anything - just nop

    def test_2(self):
        action_state = bdast_v2.ActionState("test", "")

        # Should fail on unknown keys
        with pytest.raises(BdastRunException):
            bdast.bdast_v2.process_step_nop(action_state, {
                "test": 1
            })

    def test_3(self):
        action_state = bdast_v2.ActionState("test", "")

        # Should fail on invalid configuration
        with pytest.raises(BdastArgumentException):
            bdast.bdast_v2.process_step_nop(action_state, "")

    def test_4(self):
        # Should fail on invalid action state
        with pytest.raises(BdastArgumentException):
            bdast.bdast_v2.process_step_nop(None, {})

    def test_5(self):
        action_state = bdast_v2.ActionState("test", None)

        # Should allow null/None for nop implementation config
        bdast.bdast_v2.process_step_nop(action_state, None)

