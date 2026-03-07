
import pytest
import bdast
from bdast import bdast_v2
from bdast.exception import BdastRunException
from bdast.exception import BdastLoadException
from bdast.exception import BdastArgumentException

import requests

class TestSpecStepUrl:
    def test_verify_1(self):
        action_state = bdast_v2.ActionState("test", "")

        with pytest.raises(requests.exceptions.SSLError):
            bdast.bdast_v2.process_step_url(action_state, {
                "url": "https://expired.badssl.com/",
                "method": "get"
            })

    def test_verify_2(self):
        action_state = bdast_v2.ActionState("test", "")

        with pytest.raises(requests.exceptions.SSLError):
            bdast.bdast_v2.process_step_url(action_state, {
                "url": "https://expired.badssl.com/",
                "method": "get",
                "verify": "true"
            })

    def test_verify_3(self):
        action_state = bdast_v2.ActionState("test", "")

        with pytest.raises(requests.exceptions.SSLError):
            bdast.bdast_v2.process_step_url(action_state, {
                "url": "https://expired.badssl.com/",
                "method": "get",
                "verify": True
            })

    def test_verify_4(self):
        action_state = bdast_v2.ActionState("test", "")

        bdast.bdast_v2.process_step_url(action_state, {
            "url": "https://www.google.com/",
            "method": "get",
            "verify": True
        })

    def test_verify_5(self):
        action_state = bdast_v2.ActionState("test", "")

        bdast.bdast_v2.process_step_url(action_state, {
            "url": "https://www.google.com/",
            "method": "get"
        })

    @pytest.mark.filterwarnings("ignore:.*Unverified HTTPS request.*")
    def test_noverify_1(self):
        action_state = bdast_v2.ActionState("test", "")

        bdast.bdast_v2.process_step_url(action_state, {
            "url": "https://www.google.com/",
            "method": "get",
            "verify": False
        })

    @pytest.mark.filterwarnings("ignore:.*Unverified HTTPS request.*")
    def test_noverify_2(self):
        action_state = bdast_v2.ActionState("test", "")

        bdast.bdast_v2.process_step_url(action_state, {
            "url": "https://expired.badssl.com/",
            "method": "get",
            "verify": False
        })

    def test_check_1(self):
        action_state = bdast_v2.ActionState("test", "")

        bdast.bdast_v2.process_step_url(action_state, {
            "url": "https://www.google.com.au",
            "method": "get"
        })

    def test_check_2(self):
        action_state = bdast_v2.ActionState("test", "")

        with pytest.raises(BdastRunException):
            bdast.bdast_v2.process_step_url(action_state, {
                "url": "https://www.google.com.au",
                "method": "get",
                "status_check": []
            })

    def test_check_3(self):
        action_state = bdast_v2.ActionState("test", "")

        bdast.bdast_v2.process_step_url(action_state, {
            "url": "https://www.google.com.au",
            "method": "get",
            "status_check": 200
        })

    def test_check_4(self):
        action_state = bdast_v2.ActionState("test", "")

        bdast.bdast_v2.process_step_url(action_state, {
            "url": "https://www.google.com.au",
            "method": "get",
            "status_check": [200]
        })

    def test_check_5(self):
        action_state = bdast_v2.ActionState("test", "")

        with pytest.raises(BdastRunException):
            bdast.bdast_v2.process_step_url(action_state, {
                "url": "https://www.google.com.au",
                "method": "get",
                "status_check": [350]
            })

    def test_check_5(self):
        action_state = bdast_v2.ActionState("test", "")

        bdast.bdast_v2.process_step_url(action_state, {
            "url": "https://www.google.com.au/nonexistantlocation",
            "method": "get",
            "status_check": [404]
        })

