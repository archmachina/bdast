
import sys
import bdast
import pytest

class TestCli:
    def test_valid1(self):
        sys.argv = ["--help"]

        res = bdast.cli.process_args()

        assert res == 1


