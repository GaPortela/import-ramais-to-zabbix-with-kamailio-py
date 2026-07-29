import os
import unittest
from unittest.mock import patch

from kamailio_zabbix_sync import (
    RamalInfo,
    SyncAction,
    SyncPlan,
    SyncPlanner,
    SyncReport,
    ZabbixAPI,
    ZabbixPlanExecutor,
    get_development_limit,
)


def ramal(numero='3000', ip='10.0.0.10', marca='INTELBRAS', modelo='TIP125', ua='Intelbras TIP125'):
    return RamalInfo(numero, ip, marca, modelo, ua, '', '')


class FakeHostAPI:
    def __init__(self, hosts):
        self.hosts = hosts
        self.get_calls = []
        self.creates = []
        self.updates = []

    def get(self, **kwargs):
        self.get_calls.append(kwargs)
        return self.hosts

    def create(self, **kwargs):
        self.creates.append(kwargs)
        return {'hostids': ['900']}

    def update(self, **kwargs):
        self.updates.append(kwargs)
        return {'hostids': [kwargs['hostid']]}


class FakeZabbix:
    def __init__(self, hosts):
        self.host = FakeHostAPI(hosts)


class TestStableIdentity(unittest.TestCase):
    def make_api(self, hosts):
        api = ZabbixAPI({
            'url': 'http://zabbix', 'group_name': 'Ramais',
            'host_prefix': 'ORGANIZACAO',
        })
        api.zapi = FakeZabbix(hosts)
        api.autenticar = lambda: True
        api.obter_id_grupo = lambda _: '1'
        api.obter_id_template = lambda _: None
        return api

    def tagged_host(self):
        return {
            'hostid': '42', 'host': 'ramal-3000',
            'name': 'ORGANIZACAO-INTELBRAS-TIP125-RAMAL 3000',
            'tags': [{'tag': 'ramal', 'value': '3000'}],
            'interfaces': [{'interfaceid': '5', 'ip': '10.0.0.10', 'main': '1'}],
        }

    def test_mutable_attributes_keep_same_tagged_host(self):
        api = self.make_api([self.tagged_host()])
        changed = ramal(ip='10.0.9.9', marca='YEALINK', modelo='T31G', ua='Yealink SIP-T31G')

        self.assertTrue(api.sincronizar_ramais([changed]))
        self.assertEqual(len(api.zapi.host.creates), 0)
        params = api.zapi.host.updates[0]
        self.assertEqual(params['hostid'], '42')
        self.assertEqual(params['host'], 'ramal-3000')
        self.assertEqual(params['interfaces'][0]['ip'], '10.0.9.9')
        self.assertEqual(params['tags'], [{'tag': 'ramal', 'value': '3000'}])
        self.assertEqual(params['name'], 'ORGANIZACAO-YEALINK-T31G-RAMAL 3000')
        self.assertEqual(params['description'], 'User-Agent: Yealink SIP-T31G')

    def test_dry_run_reports_plan_without_writing(self):
        api = self.make_api([])

        self.assertTrue(api.sincronizar_ramais([ramal()], dry_run=True))
        self.assertEqual(api.zapi.host.creates, [])
        self.assertEqual(api.zapi.host.updates, [])

    def test_duplicate_source_ramal_is_inconsistent(self):
        api = self.make_api([])

        self.assertFalse(api.sincronizar_ramais([ramal('03000'), ramal('3000')], dry_run=True))
        self.assertEqual(api.zapi.host.creates, [])

    def test_duplicate_hosts_are_inconsistent(self):
        api = self.make_api([self.tagged_host(), dict(self.tagged_host(), hostid='43')])

        self.assertFalse(api.sincronizar_ramais([ramal()], dry_run=True))

    def test_hostname_without_persistent_tag_is_not_identity(self):
        host = dict(self.tagged_host(), tags=[])
        plan = SyncPlanner.build([ramal()], [host], 'ramal')
        self.assertFalse(plan.is_valid)
        self.assertIn('exatamente uma tag', plan.validate()[0])

        # O catálogo real é filtrado pela API usando somente a tag persistente.
        api = self.make_api([])
        self.assertTrue(api.sincronizar_ramais([ramal()], dry_run=True))
        self.assertEqual(len(api.zapi.host.creates), 0)
        self.assertEqual(len(api.zapi.host.updates), 0)
        self.assertEqual(api.zapi.host.get_calls[0]['tags'], [{'tag': 'ramal'}])
        self.assertNotIn('groupids', api.zapi.host.get_calls[0])

    def test_invalid_plan_does_not_apply_partial_changes(self):
        api = self.make_api([])
        auth_called = []
        api.autenticar = lambda: auth_called.append(True) or True

        self.assertFalse(api.sincronizar_ramais([ramal('03000'), ramal('3000')]))
        self.assertEqual(auth_called, [])
        self.assertEqual(api.zapi.host.creates, [])
        self.assertEqual(api.zapi.host.updates, [])

    def test_repeated_synchronization_is_idempotent(self):
        api = self.make_api([self.tagged_host()])

        self.assertTrue(api.sincronizar_ramais([ramal()]))
        self.assertTrue(api.sincronizar_ramais([ramal()]))
        self.assertEqual(api.zapi.host.creates, [])
        self.assertEqual(len(api.zapi.host.updates), 2)

    def test_technical_hostname_ignores_organization_prefix(self):
        api = self.make_api([])
        api.host_prefix = 'NOVA-ORGANIZACAO'

        self.assertEqual(api.gerar_hostname_tecnico('c312-3000'), 'ramal-3000')

    def test_planner_builds_actions_without_zabbix_client(self):
        plan = SyncPlanner.build([ramal('1000'), ramal('1001')], [], 'ramal')

        self.assertEqual([action.action for action in plan.actions], ['create', 'create'])
        self.assertEqual(plan.hosts_found, 0)
        self.assertTrue(plan.is_valid)

    def test_executor_executes_only_planned_actions(self):
        api = self.make_api([])
        plan = SyncPlan([
            SyncAction('create', ramal('1000')),
            SyncAction('invalid', ramal('1001'), reason='duplicado'),
        ])

        errors = ZabbixPlanExecutor(api, '1', None).execute(plan)

        self.assertEqual(errors, 1)
        self.assertEqual(api.zapi.host.creates, [])

    def test_planner_rejects_host_with_invalid_identity_tag(self):
        plan = SyncPlanner.build(
            [ramal('1000')],
            [{'hostid': '42', 'host': 'ramal-1000', 'tags': [{'tag': 'ramal', 'value': ''}]}],
            'ramal',
        )

        self.assertFalse(plan.is_valid)
        self.assertIn('valor inválido', plan.validate()[0])

    def test_report_is_shared_by_dry_run_and_execution(self):
        api = self.make_api([])
        dry_report = SyncReport(dry_run=True)
        self.assertTrue(api.sincronizar_ramais([ramal()], dry_run=True, report=dry_report))
        self.assertIs(api.last_report, dry_report)
        self.assertEqual(dry_report.created, 1)
        self.assertIsNotNone(dry_report.plan)

    def test_development_limit_is_optional_and_validated(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(get_development_limit())
        with patch.dict(os.environ, {'LIMIT': '10'}, clear=True):
            self.assertEqual(get_development_limit(), 10)
        with patch.dict(os.environ, {'LIMIT': '0'}, clear=True):
            with self.assertRaises(ValueError):
                get_development_limit()


if __name__ == '__main__':
    unittest.main()
