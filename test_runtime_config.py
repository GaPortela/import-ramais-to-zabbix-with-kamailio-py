import os
import unittest
from unittest.mock import patch

from kamailio_zabbix_sync import build_db_config, build_zabbix_config


class TestRuntimeConfig(unittest.TestCase):
    """Testes para configuração com defaults seguros em ambientes novos."""

    def test_db_config_uses_sane_defaults_when_env_missing(self):
        with patch.dict(os.environ, {}, clear=True):
            config = build_db_config()

            self.assertEqual(config, {
                'dsn': 'postgresql://kamailio@localhost:5432/kamailio'
            })

    def test_db_config_builds_dsn_from_env_fields(self):
        with patch.dict(os.environ, {
            'KAMAILIO_DB_HOST': 'db.example.com',
            'KAMAILIO_DB_PORT': '5432',
            'KAMAILIO_DB_NAME': 'kamailio',
            'KAMAILIO_DB_USER': 'kamailio',
            'KAMAILIO_DB_PASSWORD': 'secret',
        }, clear=True):
            config = build_db_config()

            self.assertEqual(config, {
                'dsn': 'postgresql://kamailio:secret@db.example.com:5432/kamailio'
            })

    def test_db_config_uses_dsn_when_db_url_set(self):
        with patch.dict(os.environ, {
            'KAMAILIO_DB_URL': 'postgresql://kamailio:secret@db.example.com:5432/kamailio',
            'KAMAILIO_DB_HOST': 'ignored',
            'KAMAILIO_DB_USER': 'ignored',
        }, clear=True):
            config = build_db_config()

            self.assertEqual(config, {
                'dsn': 'postgresql://kamailio:secret@db.example.com:5432/kamailio'
            })

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
