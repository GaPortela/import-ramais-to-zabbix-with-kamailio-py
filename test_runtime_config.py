import os
import unittest
from unittest.mock import MagicMock, patch

from kamailio_zabbix_sync import (
    DataParser,
    KamailioDB,
    RamalInfo,
    ZabbixAPI,
    build_db_config,
    build_zabbix_config,
    get_development_limit,
)


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

    def test_limit_de_desenvolvimento_e_opcional(self):
        with patch.dict(os.environ, {'LIMIT': '3'}, clear=True):
            self.assertEqual(get_development_limit(), 3)

    def test_query_usa_limit_quando_configurado(self):
        db = KamailioDB({}, limit=3)
        db.connection = MagicMock()
        cursor = db.connection.cursor.return_value
        cursor.fetchall.return_value = []

        db.buscar_ramais_ativos()

        query, params = cursor.execute.call_args.args
        self.assertIn('LIMIT %s', query)
        self.assertEqual(params, (3,))


class TestStabilizedContracts(unittest.TestCase):
    def setUp(self):
        DataParser._BLACKLIST_IPS = []

    def test_processar_ramais_permanece_metodo_do_repositorio(self):
        db = KamailioDB({})
        result = db.processar_ramais([{
            "username": "3000",
            "contact": "sip:3000@192.168.1.50:5060",
            "received": "",
            "user_agent": "Intelbras TIP125 v1.0",
            "expires": "2026-07-20T12:00:00",
        }])

        self.assertEqual(len(result), 1)
        self.assertIsInstance(result[0], RamalInfo)
        self.assertEqual(result[0].ip, "192.168.1.50")

    def test_autenticacao_token_usa_cliente_zabbix_utils(self):
        with patch("kamailio_zabbix_sync.ZabbixAPIClient") as client_factory:
            client = client_factory.return_value
            client.api_version.return_value = "7.0.0"
            api = ZabbixAPI({"url": "http://zabbix/api_jsonrpc.php", "api_token": "token"})

            self.assertTrue(api.autenticar())
            client_factory.assert_called_once_with(url="http://zabbix/api_jsonrpc.php")
            client.login.assert_called_once_with(token="token")


if __name__ == "__main__":
    unittest.main(verbosity=2)
