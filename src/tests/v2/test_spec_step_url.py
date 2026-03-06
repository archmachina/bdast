
import pytest
import bdast
from bdast import bdast_v2
from bdast.exception import BdastRunException
from bdast.exception import BdastLoadException
from bdast.exception import BdastArgumentException

import requests

class TestProcessStepUrl:
    def verify_1(self):
        action_state = bdast_v2.ActionState("test", "")

        with pytest.raises(requests.exceptions.SSLError):
            bdast.bdast_v2.process_step_url(action_state, {
                "url": "https://expired.badssl.com/",
                "method": "get"
            })

    def verify_2(self):
        action_state = bdast_v2.ActionState("test", "")

        with pytest.raises(requests.exceptions.SSLError):
            bdast.bdast_v2.process_step_url(action_state, {
                "url": "https://expired.badssl.com/",
                "method": "get",
                "verify": "true"
            })

    def verify_3(self):
        action_state = bdast_v2.ActionState("test", "")

        with pytest.raises(requests.exceptions.SSLError):
            bdast.bdast_v2.process_step_url(action_state, {
                "url": "https://expired.badssl.com/",
                "method": "get",
                "verify": True
            })

    def verify_4(self):
        action_state = bdast_v2.ActionState("test", "")

        bdast.bdast_v2.process_step_url(action_state, {
            "url": "https://www.google.com/",
            "method": "get",
            "verify": True
        })

    def verify_5(self):
        action_state = bdast_v2.ActionState("test", "")

        bdast.bdast_v2.process_step_url(action_state, {
            "url": "https://www.google.com/",
            "method": "get"
        })

    @pytest.mark.filterwarnings("ignore:.*Unverified HTTPS request.*")
    def noverify_1(self):
        action_state = bdast_v2.ActionState("test", "")

        bdast.bdast_v2.process_step_url(action_state, {
            "url": "https://www.google.com/",
            "method": "get",
            "verify": False
        })

    @pytest.mark.filterwarnings("ignore:.*Unverified HTTPS request.*")
    def noverify_2(self):
        action_state = bdast_v2.ActionState("test", "")

        bdast.bdast_v2.process_step_url(action_state, {
            "url": "https://expired.badssl.com/",
            "method": "get",
            "verify": False
        })

