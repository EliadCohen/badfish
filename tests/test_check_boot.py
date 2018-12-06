import pytest
import requests_mock
import unittest

from badfish import main
from tests import config


class TestCheckBoot(unittest.TestCase):

    @pytest.fixture(autouse=True)
    def inject_capsys(self, capsys):
        self._capsys = capsys

    @requests_mock.mock()
    def badfish_call(self, _mock):
        _mock.get("https://%s/redfish/v1/Systems/System.Embedded.1/Bios" % config.MOCK_HOST,
                  json={"Attributes": {"BootMode": u"Bios"}}
                  )
        _mock.get("https://%s/redfish/v1/Systems/System.Embedded.1/BootSources" % config.MOCK_HOST,
                  json={"Attributes": {"BootSeq": self.boot_seq}})
        argv = ["-H", config.MOCK_HOST, "-u", config.MOCK_USER, "-p", config.MOCK_PASS]
        argv.extend(self.args)
        assert not main(argv)
        out, err = self._capsys.readouterr()
        return err

    def test_check_boot_without_interfaces(self):
        self.boot_seq = config.BOOT_SEQ_RESPONSE_DIRECTOR
        self.args = ["--check-boot"]
        result = self.badfish_call()
        assert config.RESPONSE_WITHOUT == result

    def test_check_boot_with_interfaces_director(self):
        self.boot_seq = config.BOOT_SEQ_RESPONSE_DIRECTOR
        self.args = ["-i", config.INTERFACES_PATH, "--check-boot"]
        result = self.badfish_call()
        assert config.RESPONSE_DIRECTOR == result

    def test_check_boot_with_interfaces_foreman(self):
        self.boot_seq = config.BOOT_SEQ_RESPONSE_FOREMAN
        self.args = ["-i", config.INTERFACES_PATH, "--check-boot"]
        result = self.badfish_call()
        assert config.RESPONSE_FOREMAN == result

    def test_check_boot_no_match(self):
        self.boot_seq = config.BOOT_SEQ_RESPONSE_NO_MATCH
        self.args = ["-i", config.INTERFACES_PATH, "--check-boot"]
        result = self.badfish_call()
        assert config.WARN_NO_MATCH == result
