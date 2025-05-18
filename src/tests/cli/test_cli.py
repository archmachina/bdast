
import sys
import bdast
import pytest

class TestCli:
    def test_1(self):
        sys.argv = ["bdast", "--help"]

        with pytest.raises(SystemExit):
            res = bdast.cli.process_args()

    def test_2(self):
        sys.argv = ["bdast", "wrapper"]

        res = bdast.cli.process_args()

        assert res == 0

    def test_3(self):
        sys.argv = ["bdast", "template"]

        res = bdast.cli.process_args()

        assert res == 0

