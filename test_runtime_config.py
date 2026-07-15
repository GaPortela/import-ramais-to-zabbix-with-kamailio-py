import os
import unittest
from unittest.mock import patch

from kamailio_zabbix_sync import build_db_config, build_zabbix_config


class TestRuntimeConfig(unittest.TestCase):
    """Testes para configuração com defaults seguros em ambientes novos."""

    def test_db_config_uses_sane_defaults_when_env_missing(self):
        with patch.dict(os.environ, {}, clear=True):
            config = build_db_config()

            self.assertEqual(config["host"], "localhost")
            self.assertEqual(config["port"], 5432)
            self.assertEqual(config["database"], "kamailio")
            self.assertEqual(config["user"], "kamailio")
            self.assertEqual(config["password"], "")

    def test_zabbix_config_uses_sane_defaults_when_env_missing(self):
        with patch.dict(os.environ, {}, clear=True):
            config = build_zabbix_config()

            self.assertEqual(config["url"], "http://zabbix-web/zabbix/api_jsonrpc.php")
            self.assertIsNone(config["api_token"])
            self.assertIsNone(config["user"])
            self.assertIsNone(config["password"])
            self.assertEqual(config["group_name"], "Ramais")
            self.assertEqual(config["template_name"], "ICMP Ping")


if __name__ == "__main__":
    unittest.main(verbosity=2)
