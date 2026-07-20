#!/usr/bin/env python3
"""
Testes unitários para o módulo DataParser
"""

import json
import os
import tempfile
import unittest
from datetime import datetime
from kamailio_zabbix_sync import DataParser, RamalInfo, gerar_relatorio_inspecao, salvar_inspecao_json


class TestExtrairIPv4(unittest.TestCase):
    """Testes para extração de IPv4"""

    def test_ipv4_em_uri_sip_com_porta(self):
        """Extrai IPv4 de URI SIP com porta"""
        result = DataParser.extrair_ipv4("sip:3000@192.168.1.50:5060")
        self.assertEqual(result, "192.168.1.50")

    def test_ipv4_em_uri_sip_sem_porta(self):
        """Extrai IPv4 de URI SIP sem porta"""
        result = DataParser.extrair_ipv4("sip:3000@10.0.0.5")
        self.assertEqual(result, "10.0.0.5")

    def test_ipv4_em_received(self):
        """Extrai IPv4 do campo received"""
        result = DataParser.extrair_ipv4("sip:3000@172.16.254.1:5060")
        self.assertEqual(result, "172.16.254.1")

    def test_ipv4_invalido_retorna_none(self):
        """Retorna None para IPv4 inválido"""
        result = DataParser.extrair_ipv4("sip:3000@999.999.999.999")
        self.assertIsNone(result)

    def test_uri_vazia_retorna_none(self):
        """Retorna None para URI vazia"""
        result = DataParser.extrair_ipv4("")
        self.assertIsNone(result)

    def test_uri_none_retorna_none(self):
        """Retorna None para URI None"""
        result = DataParser.extrair_ipv4(None)
        self.assertIsNone(result)

    def test_ipv4_maximos_valores(self):
        """Extrai IPv4 com valores máximos (255.255.255.255)"""
        result = DataParser.extrair_ipv4("sip:3000@255.255.255.255:5060")
        self.assertEqual(result, "255.255.255.255")

    def test_ipv4_minimos_valores(self):
        """Extrai IPv4 com valores mínimos (0.0.0.0)"""
        result = DataParser.extrair_ipv4("sip:3000@0.0.0.0:5060")
        self.assertEqual(result, "0.0.0.0")

    def test_multiplos_ips_retorna_primeiro(self):
        """Extrai primeiro IPv4 quando há múltiplos"""
        result = DataParser.extrair_ipv4("sip:3000@192.168.1.50:5060 via 10.0.0.1")
        self.assertEqual(result, "192.168.1.50")


class TestEhSoftphone(unittest.TestCase):
    """Testes para detecção de softphones"""

    def test_microsip_detectado(self):
        """Detecta MicroSIP como softphone"""
        self.assertTrue(DataParser.eh_softphone("MicroSIP"))

    def test_mxipcall_detectado(self):
        """Detecta MxIpCall como softphone"""
        self.assertTrue(DataParser.eh_softphone("MxIpCall v2.0"))

    def test_linphone_detectado(self):
        """Detecta Linphone como softphone"""
        self.assertTrue(DataParser.eh_softphone("Linphone 4.2"))

    def test_zoiper_detectado(self):
        """Detecta Zoiper como softphone"""
        self.assertTrue(DataParser.eh_softphone("Zoiper 5.0"))

    def test_intelbras_nao_detectado_como_softphone(self):
        """Não detecta Intelbras como softphone"""
        self.assertFalse(DataParser.eh_softphone("Intelbras TIP125 v1.0"))

    def test_yealink_nao_detectado_como_softphone(self):
        """Não detecta Yealink como softphone"""
        self.assertFalse(DataParser.eh_softphone("Yealink SIP-T31G"))

    def test_user_agent_vazio(self):
        """Retorna False para User-Agent vazio"""
        self.assertFalse(DataParser.eh_softphone(""))

    def test_user_agent_none(self):
        """Retorna False para User-Agent None"""
        self.assertFalse(DataParser.eh_softphone(None))

    def test_case_insensitive(self):
        """Detecção case-insensitive"""
        self.assertTrue(DataParser.eh_softphone("MICROSIP v1.0"))
        self.assertTrue(DataParser.eh_softphone("microsip v1.0"))
        self.assertTrue(DataParser.eh_softphone("MiCrOsIp v1.0"))


class TestExtrairMarcaModelo(unittest.TestCase):
    """Testes para parsing de marca e modelo"""

    def test_intelbras_tip125(self):
        """Parseia Intelbras TIP125"""
        marca, modelo = DataParser.extrair_marca_modelo("Intelbras TIP125 v1.0")
        self.assertEqual(marca, "INTELBRAS")
        self.assertEqual(modelo, "TIP125")

    def test_intelbras_tip125_minusculas(self):
        """Parseia Intelbras com user-agent em minúsculas"""
        marca, modelo = DataParser.extrair_marca_modelo("intelbras tip125 v1.0")
        self.assertEqual(marca, "INTELBRAS")
        self.assertEqual(modelo, "TIP125")

    def test_yealink_sip_t31g(self):
        """Parseia Yealink SIP-T31G"""
        marca, modelo = DataParser.extrair_marca_modelo("Yealink SIP-T31G")
        self.assertEqual(marca, "YEALINK")
        self.assertIn("31", modelo)

    def test_grandstream_gxp1625(self):
        """Parseia Grandstream GXP1625"""
        marca, modelo = DataParser.extrair_marca_modelo("Grandstream GXP1625")
        self.assertEqual(marca, "GRANDSTREAM")
        self.assertIn("1625", modelo)

    def test_cisco_cp7961g(self):
        """Parseia Cisco CP-7961G"""
        marca, modelo = DataParser.extrair_marca_modelo("Cisco IP Phone CP-7961G")
        self.assertEqual(marca, "CISCO")
        self.assertIn("7961", modelo)

    def test_polycom_vvx300(self):
        """Parseia Polycom VVX300"""
        marca, modelo = DataParser.extrair_marca_modelo("Polycom VVX 300")
        self.assertEqual(marca, "POLYCOM")
        self.assertIn("300", modelo)

    def test_marca_nao_identificada_retorna_generico(self):
        """Retorna GENERICO para marca desconhecida"""
        marca, modelo = DataParser.extrair_marca_modelo("Unknown Device v1.0")
        self.assertEqual(marca, "GENERICO")
        self.assertEqual(modelo, "GENERICO")

    def test_user_agent_vazio_retorna_generico(self):
        """Retorna GENERICO para User-Agent vazio"""
        marca, modelo = DataParser.extrair_marca_modelo("")
        self.assertEqual(marca, "GENERICO")
        self.assertEqual(modelo, "GENERICO")

    def test_user_agent_none_retorna_generico(self):
        """Retorna GENERICO para User-Agent None"""
        marca, modelo = DataParser.extrair_marca_modelo(None)
        self.assertEqual(marca, "GENERICO")
        self.assertEqual(modelo, "GENERICO")

    def test_retorno_sempre_maiusculas(self):
        """Retorno sempre em MAIÚSCULAS"""
        marca, modelo = DataParser.extrair_marca_modelo("intelbras tip125")
        self.assertTrue(marca.isupper() or marca == "GENERICO")
        self.assertTrue(modelo.isupper() or modelo == "GENERICO")

    def test_intelbras_ip_variacao(self):
        """Parseia variação Intelbras IP"""
        marca, modelo = DataParser.extrair_marca_modelo("Intelbras IP2000")
        self.assertEqual(marca, "INTELBRAS")
        self.assertIn("2000", modelo)

    def test_avaya_ip_office(self):
        """Parseia Avaya IP Office"""
        marca, modelo = DataParser.extrair_marca_modelo("Avaya IP Office")
        self.assertEqual(marca, "AVAYA")

    def test_user_agent_complexo(self):
        """Parseia User-Agent complexo com versão e informações extras"""
        marca, modelo = DataParser.extrair_marca_modelo(
            "YEALINK SIP-T31G 124.47.2.1.45 v1.0 (PCCW)"
        )
        self.assertEqual(marca, "YEALINK")
        self.assertIn("31", modelo)

    def test_compatibilidade_com_nomes_antigos(self):
        """Detecta marcas por nomes antigos/alternativos"""
        # Teste com variações de nome
        marca, _ = DataParser.extrair_marca_modelo("Intelbras IP 3000")
        self.assertEqual(marca, "INTELBRAS")


class TestInspecaoDados(unittest.TestCase):
    """Testes para o relatório de inspeção de dados brutos e parseados"""

    def test_relatorio_inspecao_mostra_brutos_e_parseados(self):
        """Gera um relatório com dados crus e parseados para inspeção manual"""
        dados_brutos = [{
            'username': '3000',
            'contact': 'sip:3000@192.168.1.50:5060',
            'received': 'sip:3000@192.168.1.50:5060',
            'user_agent': 'Intelbras TIP125 v1.0',
            'expires': '2026-07-20 12:00:00+00'
        }]
        dados_parseados = [RamalInfo(
            numero_ramal='3000',
            ip='192.168.1.50',
            marca='INTELBRAS',
            modelo='TIP125',
            user_agent='Intelbras TIP125 v1.0',
            expires='2026-07-20 12:00:00+00',
            contact='sip:3000@192.168.1.50:5060'
        )]

        relatorio = gerar_relatorio_inspecao(dados_brutos, dados_parseados, [])

        self.assertIn('Dados brutos retornados pelo banco', relatorio)
        self.assertIn('username=3000', relatorio)
        self.assertIn('Dados parseados', relatorio)
        self.assertIn('Ramal 3000', relatorio)
        self.assertIn('192.168.1.50', relatorio)


class TestNormalizacaoDados(unittest.TestCase):
    """Testes para normalização de ramal e modelo"""

    def test_normaliza_numero_ramal_removendo_prefixos(self):
        """Remove prefixos como 'Ramal' e 'c312' para deixar apenas o número do ramal"""
        self.assertEqual(DataParser.normalizar_numero_ramal('Ramal 3000'), '3000')
        self.assertEqual(DataParser.normalizar_numero_ramal('c312-3000'), '3000')
        self.assertEqual(DataParser.normalizar_numero_ramal('c312-Ramal 3001'), '3001')
        self.assertEqual(DataParser.normalizar_numero_ramal('SIP3001'), '3001')

    def test_normaliza_modelo_removendo_versionamento(self):
        """Remove versões de firmware e sufixos de versão do modelo"""
        self.assertEqual(DataParser.normalizar_modelo('Intelbras TIP125 v1.0'), 'TIP125')
        self.assertEqual(DataParser.normalizar_modelo('Yealink SIP-T31G 124.47.2.1.45 v1.0 (PCCW)'), 'T31G')
        self.assertEqual(DataParser.normalizar_modelo('Grandstream GXP1625 1.0.11'), 'GXP1625')

    def test_salvar_inspecao_json_cria_arquivo_com_dados_normalizados(self):
        """Exporta inspeção para JSON com campos limpos para análise"""
        dados_brutos = [{
            'username': 'Ramal 3000',
            'contact': 'sip:3000@192.168.1.50:5060',
            'received': 'sip:3000@192.168.1.50:5060',
            'user_agent': 'Yealink SIP-T31G 124.47.2.1.45 v1.0 (PCCW)',
            'expires': '2026-07-20 12:00:00+00'
        }]
        dados_parseados = [RamalInfo(
            numero_ramal='3000',
            ip='192.168.1.50',
            marca='YEALINK',
            modelo='T31G',
            user_agent='Yealink SIP-T31G 124.47.2.1.45 v1.0 (PCCW)',
            expires='2026-07-20 12:00:00+00',
            contact='sip:3000@192.168.1.50:5060'
        )]

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, 'inspecao.json')
            salvar_inspecao_json(dados_brutos, dados_parseados, [], output_path=output_path)

            with open(output_path, encoding='utf-8') as handle:
                payload = json.load(handle)

        self.assertEqual(payload['dados_parseados'][0]['numero_ramal'], '3000')
        self.assertEqual(payload['dados_parseados'][0]['username'], '3000')
        self.assertEqual(payload['dados_parseados'][0]['modelo'], 'T31G')
        self.assertEqual(payload['dados_brutos'][0]['username'], 'Ramal 3000')
        self.assertEqual(payload['dados_brutos'][0]['username_normalizado'], '3000')

    def test_salvar_inspecao_json_converte_datetime_em_string(self):
        """Converte valores datetime para string antes de gravar o JSON"""
        dados_brutos = [{
            'username': 'c312-1000',
            'contact': 'sip:1000@192.168.1.10:5060',
            'received': 'sip:1000@192.168.1.10:5060',
            'user_agent': 'Yealink SIP-T20P 9.73.193.40',
            'expires': datetime(2026, 7, 20, 12, 0, 0)
        }]

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, 'inspecao.json')
            salvar_inspecao_json(dados_brutos, [], [], output_path=output_path)

            with open(output_path, encoding='utf-8') as handle:
                payload = json.load(handle)

        self.assertEqual(payload['dados_brutos'][0]['expires'], '2026-07-20T12:00:00')


class TestIntegracaoParsing(unittest.TestCase):
    """Testes de integração entre funções"""

    def test_fluxo_completo_ramal_valido(self):
        """Testa fluxo completo de validação e parsing de ramal válido"""
        # Simula dados de um ramal Intelbras
        user_agent = "Intelbras TIP125 v1.0"
        contact = "sip:3000@192.168.1.50:5060"
        
        # Valida
        self.assertFalse(DataParser.eh_softphone(user_agent))
        
        # Extrai IP
        ip = DataParser.extrair_ipv4(contact)
        self.assertEqual(ip, "192.168.1.50")
        
        # Parseia marca/modelo
        marca, modelo = DataParser.extrair_marca_modelo(user_agent)
        self.assertEqual(marca, "INTELBRAS")
        self.assertEqual(modelo, "TIP125")

    def test_fluxo_completo_softphone_rejeitado(self):
        """Testa fluxo completo de rejeição de softphone"""
        user_agent = "MicroSIP v2.0"
        contact = "sip:3000@192.168.1.50:5060"
        
        # Detecta como softphone (deve ser rejeitado)
        self.assertTrue(DataParser.eh_softphone(user_agent))
        
        # Mesmo tendo IP válido, não deveria ser processado

    def test_ramal_sem_ip_rejeitado(self):
        """Testa ramal sem IP válido é rejeitado"""
        user_agent = "Intelbras TIP125 v1.0"
        contact = "sip:3000@hostname.com"  # Hostname, não IP
        
        # Extrai IP
        ip = DataParser.extrair_ipv4(contact)
        self.assertIsNone(ip)  # Deve retornar None


if __name__ == '__main__':
    unittest.main(verbosity=2)
