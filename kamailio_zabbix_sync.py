#!/usr/bin/env python3
"""
Kamailio to Zabbix Synchronization Script
Sincroniza ramais ativos do Kamailio com hosts no Zabbix
"""

import argparse
import json
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from time import perf_counter
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote_plus

import psycopg2
from dotenv import load_dotenv
from psycopg2.extras import RealDictCursor

from zabbix_utils import ZabbixAPI as ZabbixAPIClient
# ============================================================================
# CONFIGURAÇÃO
# ============================================================================

# Carrega variáveis de ambiente do arquivo .env
load_dotenv()


def build_db_config() -> Dict[str, object]:
    """Retorna configuração de conexão PostgreSQL.

    Se `KAMAILIO_DB_URL` ou `DATABASE_URL` estiver definido, usa essa URL.
    Caso contrário, constrói automaticamente a URL a partir dos campos individuais.
    """
    db_url = os.getenv('KAMAILIO_DB_URL') or os.getenv('DATABASE_URL')
    if db_url:
        return {'dsn': db_url}

    host = os.getenv('KAMAILIO_DB_HOST', 'localhost')
    port = int(os.getenv('KAMAILIO_DB_PORT', '5432'))
    database = os.getenv('KAMAILIO_DB_NAME', 'kamailio')
    user = quote_plus(os.getenv('KAMAILIO_DB_USER', 'kamailio'))
    password = os.getenv('KAMAILIO_DB_PASSWORD', '')

    if password:
        password = quote_plus(password)
        dsn = f"postgresql://{user}:{password}@{host}:{port}/{database}"
    else:
        dsn = f"postgresql://{user}@{host}:{port}/{database}"

    return {'dsn': dsn}


def build_zabbix_config() -> Dict[str, Optional[str]]:
    """Retorna configuração do Zabbix com defaults seguros."""
    return {
        'url': os.getenv('ZABBIX_URL', 'http://zabbix-web/zabbix/api_jsonrpc.php'),
        'api_token': os.getenv('ZABBIX_API_TOKEN') or None,
        'user': os.getenv('ZABBIX_USER') or None,
        'password': os.getenv('ZABBIX_PASSWORD') or None,
        'group_name': os.getenv('ZABBIX_GROUP_NAME', 'Ramais'),
        'template_name': os.getenv('ZABBIX_TEMPLATE_NAME', 'ICMP Ping'),
        # Nova configuração para o prefixo da organização
        'host_prefix': os.getenv('HOST_PREFIX', 'ORGANIZACAO')
    }


def parse_bool(value: Optional[str]) -> bool:
    """Converte valores de ambiente para booleanos."""
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {'1', 'true', 'yes', 'y', 'on'}


def get_development_limit() -> Optional[int]:
    """Retorna LIMIT para desenvolvimento; ausente significa processamento completo."""
    value = os.getenv('LIMIT', '').strip()
    if not value:
        return None
    try:
        limit = int(value)
    except ValueError:
        raise ValueError('LIMIT deve ser um inteiro positivo')
    if limit <= 0:
        raise ValueError('LIMIT deve ser um inteiro positivo')
    return limit


DB_CONFIG = build_db_config()
ZABBIX_CONFIG = build_zabbix_config()

LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO').upper()
LOG_FILE = os.getenv('LOG_FILE', 'kamailio_zabbix_sync.log')

# Configuração de Logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ============================================================================
# CLASSES E DATA MODELS
# ============================================================================

@dataclass
class RamalInfo:
    """Representa um ramal processado"""
    numero_ramal: str
    ip: str
    marca: str
    modelo: str
    user_agent: str
    expires: str
    contact: str

    def __str__(self):
        return (f"Ramal: {self.numero_ramal} | IP: {self.ip} | "
                f"Marca: {self.marca} | Modelo: {self.modelo}")


@dataclass
class SyncAction:
    """Uma ação já validada, pronta para ser executada ou exibida no dry-run."""
    action: str
    ramal: RamalInfo
    host: Optional[Dict[str, Any]] = None
    reason: str = ''


@dataclass
class SyncPlan:
    """Plano imutável em intenção: decisões separadas da execução na API."""
    actions: List[SyncAction]
    hosts_found: int = 0
    inconsistencies: List[str] = field(default_factory=list)

    def count(self, action: str) -> int:
        return sum(item.action == action for item in self.actions)

    @property
    def is_valid(self) -> bool:
        """Indica se o plano pode ser aplicado sem ambiguidade de identidade."""
        return not self.validate()

    def validate(self) -> List[str]:
        """Retorna todas as inconsistências que impedem uma execução atômica."""
        issues = list(self.inconsistencies)
        issues.extend(item.reason for item in self.actions
                      if item.action == 'invalid' and item.reason)
        return issues


@dataclass
class SyncReport:
    """Resultado único da sincronização, compartilhado por dry-run e execução real."""
    records_read: int = 0
    valid_records: int = 0
    ignored_records: int = 0
    hosts_found: int = 0
    created: int = 0
    updated: int = 0
    errors: int = 0
    dry_run: bool = False
    plan: Optional[SyncPlan] = None
    inconsistencies: List[str] = field(default_factory=list)
    duration_seconds: float = 0.0
    _started_at: float = field(default_factory=perf_counter, repr=False)

    def finalize(self) -> 'SyncReport':
        self.duration_seconds = perf_counter() - self._started_at
        return self

    def format(self) -> str:
        mode = ' (DRY-RUN)' if self.dry_run else ''
        lines = [
            f"RELATÓRIO FINAL{mode}: lidos={self.records_read} "
            f"válidos={self.valid_records} ignorados={self.ignored_records} "
            f"encontrados={self.hosts_found} criados={self.created} "
            f"atualizados={self.updated} erros={self.errors} "
            f"tempo={self.duration_seconds:.3f}s"
        ]
        if self.plan:
            lines.append('PLANO:')
            for action in self.plan.actions:
                numero = action.ramal.numero_ramal
                suffix = f" - {action.reason}" if action.reason else ''
                lines.append(f"{action.action.upper()} ramal {numero}{suffix}")
        if self.inconsistencies:
            lines.append('INCONSISTÊNCIAS:')
            lines.extend(f"- {issue}" for issue in self.inconsistencies)
        return '\n'.join(lines)


# ============================================================================
# REGEX E PARSING DE DADOS
# ============================================================================

class DataParser:
    """Classe responsável pelo tratamento e parsing dos dados"""

    # Regex para extrair IPv4 de URIs SIP
    IPV4_REGEX = r'\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b'

    # Dicionário de fabricantes conhecidos e suas variações de nome
    MANUFACTURERS = {
        'INTELBRAS': [
            'intelbras', 'intelbras tip', 'tip1', 'ip1'
        ],
        'YEALINK': [
            'yealink', 'sip-t', 'sip-cp', 'cp860'
        ],
        'GRANDSTREAM': [
            'grandstream', 'gxp', 'grp', 'gdp'
        ],
        'CISCO': [
            'cisco', 'cp-', 'ip phone'
        ],
        'POLYCOM': [
            'polycom', 'soundpoint', 'soundstation', 'vvx'
        ],
        'AVAYA': [
            'avaya', 'ip office', 'communication manager'
        ]
    }

    # Softphones a serem excluídos (não são aparelhos físicos)
    SOFTPHONES = [
        'microsip', 'zoiper', 'linphone', 'ekiga', 'jitsi',
        'mxipcall', 'groundwire', 'sipclient', 'bria',
        'twinkle', 'softphone', 'mobile', 'app', 'client'
    ]

    # Atributo estático para armazenar o cache da blacklist
    _BLACKLIST_IPS: Optional[List[str]] = None

    @classmethod
    def carregar_blacklist_ips(cls, caminho_arquivo: str = 'blacklist_ips.json') -> List[str]:
        """Carrega e armazena em cache a blacklist a partir de arquivo JSON(blacklist_ips.json)."""
        if cls._BLACKLIST_IPS is None:
            if os.path.exists(caminho_arquivo):
                try:
                    with open(caminho_arquivo, 'r', encoding='utf-8') as f:
                        dados = json.load(f)
                        if isinstance(dados, list):
                            cls._BLACKLIST_IPS = dados
                        elif isinstance(dados, dict) and 'ips' in dados:
                            cls._BLACKLIST_IPS = dados['ips']
                        else:
                            cls._BLACKLIST_IPS = []
                except Exception as e:
                    logger.error(f"Erro ao ler arquivo de blacklist {caminho_arquivo}: {e}")
                    cls._BLACKLIST_IPS = []
            else:
                logger.warning(f"Arquivo de blacklist {caminho_arquivo} não encontrado. Nenhuma filtragem por blacklist será aplicada.")
                cls._BLACKLIST_IPS = []
        return cls._BLACKLIST_IPS

    @staticmethod
    def extrair_ipv4(contact_uri: str) -> Optional[str]:
        """Extrai o IPv4 de uma URI SIP usando Regex."""
        if not contact_uri:
            return None
        
        try:
            match = re.search(DataParser.IPV4_REGEX, contact_uri)
            if match:
                ip = match.group(0)
                logger.debug(f"IPv4 extraído de '{contact_uri}': {ip}")
                return ip
            else:
                logger.warning(f"Nenhum IPv4 encontrado em: {contact_uri}")
                return None
        except Exception as e:
            logger.error(f"Erro ao extrair IPv4 de '{contact_uri}': {e}")
            return None

    @classmethod
    def filtrar_blacklist(cls, ramais: List['RamalInfo']) -> Tuple[List['RamalInfo'], List[Dict]]:
        """
        Filtra uma coleção completa de ramais parseados removendo aqueles que pertencem à blacklist.
        
        Returns:
            Tupla (ramais_validos, ramais_rejeitados)
        """
        blacklist = cls.carregar_blacklist_ips()
        if not blacklist:
            return ramais, []

        ramais_validos = []
        ramais_rejeitados = []

        for ramal in ramais:
            if ramal.ip in blacklist:
                logger.info(f"Ramal {ramal.numero_ramal} (IP: {ramal.ip}) rejeitado: IP está na blacklist")
                ramais_rejeitados.append({
                    'numero': ramal.numero_ramal,
                    'motivo': f"IP {ramal.ip} na blacklist"
                })
            else:
                ramais_validos.append(ramal)

        return ramais_validos, ramais_rejeitados
    @staticmethod

    def normalizar_numero_ramal(valor: Optional[str]) -> str:
        """Ponto único de normalização da identidade lógica de um ramal."""
        if not valor:
            return ''

        texto = str(valor).strip()
        texto = re.sub(r'(?i)\bramal\b', '', texto).strip()
        texto = re.sub(r'(?i)^c\s*\d+\s*[-:\[\]\s/]*', '', texto).strip()
        numeros = re.findall(r'\d+', texto)

        if not numeros:
            return ''

        numero = numeros[-1]
        if numero.startswith('0') and len(numero) > 1:
            return numero.lstrip('0') or '0'
        return numero

    @staticmethod
    def normalizar_modelo(user_agent: Optional[str], modelo_extraido: Optional[str] = None) -> str:
        """Remove versionamento de firmware/softwares do modelo, preservando o nome padrão do aparelho."""
        if not user_agent and not modelo_extraido:
            return 'GENERICO'

        base = (modelo_extraido or '').strip()
        if not base and user_agent:
            _, base = DataParser.extrair_marca_modelo(user_agent)

        if not base:
            return 'GENERICO'

        texto = base.upper()
        texto = re.sub(r'\s+V\d+(?:\.\d+)*', '', texto)
        texto = re.sub(r'\s+\d+(?:\.\d+){1,}', '', texto)
        texto = re.sub(r'\s*\([^)]*\)', '', texto)
        texto = re.sub(r'\s+', ' ', texto).strip()
        texto = re.sub(r'[^A-Z0-9\-\s]', '', texto)
        texto = re.sub(r'\s+', ' ', texto).strip()

        if not texto:
            return 'GENERICO'

        if 'SIP-T' in texto:
            return texto.replace('SIP-T', 'T').replace(' ', '')
        if 'SIP-' in texto:
            return texto.replace('SIP-', '').replace(' ', '')
        if 'CP-' in texto:
            return texto.replace('CP-', 'CP').replace(' ', '')
        if 'cp' in texto.lower() and re.search(r'\bcp\d+\b', texto.lower()):
            return re.sub(r'\bcp(\d+)\b', r'CP\1', texto, flags=re.IGNORECASE).replace(' ', '')
        return texto.replace(' ', '')

    @staticmethod
    def eh_ip_blacklist(ip: str) -> bool:
        """
        Verifica se o IP está na blacklist de IPs a serem ignorados.
        
        Args:
            ip: String do IP a ser verificado
            
        Returns:
            True se estiver na blacklist, False caso contrário
        """
        if not ip:
            return False
        
        if ip in DataParser.carregar_blacklist_ips():
            logger.info(f"IP {ip} está na blacklist e será ignorado")
            return True
        
        return False

    @staticmethod
    def eh_softphone(user_agent: str) -> bool:
        """
        Verifica se o User-Agent corresponde a um softphone.
        
        Args:
            user_agent: String do User-Agent do aparelho
            
        Returns:
            True se for softphone, False caso contrário
        """
        if not user_agent:
            return False
        
        user_agent_lower = user_agent.lower()
        
        for softphone in DataParser.SOFTPHONES:
            if softphone in user_agent_lower:
                logger.debug(f"Softphone detectado: {user_agent}")
                return True
        
        return False

    @staticmethod
    def extrair_marca_modelo(user_agent: str) -> Tuple[str, str]:
        """
        Faz parsing do User-Agent para extrair MARCA e MODELO do telefone.
        
        Args:
            user_agent: String do User-Agent (ex: "Intelbras TIP125 v1.0")
            
        Returns:
            Tupla (MARCA, MODELO) em MAIÚSCULAS (ex: ("INTELBRAS", "TIP125"))
            Se não conseguir identificar, retorna ("GENERICO", "GENERICO")
            
        Example:
            >>> DataParser.extrair_marca_modelo("Intelbras TIP125 v1.0")
            ('INTELBRAS', 'TIP125')
            
            >>> DataParser.extrair_marca_modelo("Unknown Device")
            ('GENERICO', 'GENERICO')
        """
        if not user_agent:
            logger.warning("User-Agent vazio fornecido")
            return ("GENERICO", "GENERICO")
        
        user_agent_lower = user_agent.lower()
        user_agent_upper = user_agent.upper()
        
        marca_encontrada = None
        
        # Buscar fabricante no User-Agent
        for marca_oficial, variacoes in DataParser.MANUFACTURERS.items():
            for variacao in variacoes:
                if variacao in user_agent_lower:
                    marca_encontrada = marca_oficial
                    break
            if marca_encontrada:
                break
        
        if not marca_encontrada:
            logger.warning(f"Marca não identificada para: {user_agent}")
            return ("GENERICO", "GENERICO")
        
        # Tentar extrair modelo baseado em padrões comuns
        modelo = DataParser._extrair_modelo(user_agent, marca_encontrada)
        
        logger.debug(f"Parsing bem-sucedido: {user_agent} → Marca: {marca_encontrada}, Modelo: {modelo}")
        return (marca_encontrada, modelo)

    @staticmethod
    def _extrair_modelo(user_agent: str, marca: str) -> str:
        """
        Extrai o modelo específico do User-Agent baseado na marca.
        
        Args:
            user_agent: String do User-Agent
            marca: Marca identificada (ex: "INTELBRAS")
            
        Returns:
            Modelo extraído em MAIÚSCULAS, ou "GENERICO" se não conseguir
        """
        user_agent_upper = user_agent.upper()
        
        # Padrões específicos por marca
        patterns = {
            'INTELBRAS': [
                r'TIP(\d+[A-Z]*)',
                r'IP(\d+[A-Z]*)'
            ],
            'YEALINK': [
                r'(?:SIP-)?T(\d+[A-Z]*)',
                r'CP(\d+[A-Z]*)'
            ],
            'GRANDSTREAM': [
                r'GXP(\d+[A-Z]*)',
                r'GRP(\d+[A-Z]*)',
                r'GDP(\d+[A-Z]*)'
            ],
            'CISCO': [
                r'CP-(\d+[A-Z]*)',
                r'([A-Z0-9]+(?:IP[A-Z0-9]*)?)'
            ],
            'POLYCOM': [
                r'(?:SOUNDPOINT|VVX)(?:\s)?(\d+[A-Z]*)',
                r'([A-Z0-9]+)'
            ],
            'AVAYA': [
                r'IP\s?(?:OFFICE|PHONE)?\s?(\d+[A-Z]*)'
            ]
        }
        
        if marca in patterns:
            for pattern in patterns[marca]:
                match = re.search(pattern, user_agent_upper)
                if match:
                    modelo = match.group(0).upper()
                    return modelo
        
        # Se não conseguir extrair, tenta pegar primeira sequência significativa
        match = re.search(r'(\b[A-Z]{2,}\d+[A-Z0-9]*\b)', user_agent_upper)
        if match:
            return match.group(1)
        
        return "GENERICO"


# ============================================================================
# CONEXÃO COM BANCO DE DADOS
# ============================================================================

class KamailioDB:
    """Classe para gerenciar conexão e queries ao banco PostgreSQL do Kamailio"""

    def __init__(self, db_config: Dict, limit: Optional[int] = None):
        """
        Inicializa a conexão com o banco de dados.
        
        Args:
            db_config: Dicionário com credenciais (host, port, database, user, password)
        """
        self.db_config = db_config
        self.limit = limit
        self.connection = None

    def conectar(self) -> bool:
        """
        Estabelece conexão com o banco PostgreSQL.
        
        Returns:
            True se conexão bem-sucedida, False caso contrário
        """
        try:
            self.connection = psycopg2.connect(**self.db_config)
            if 'dsn' in self.db_config:
                logger.info("Conectado ao PostgreSQL via URL configurada")
            else:
                logger.info(f"Conectado ao PostgreSQL em {self.db_config['host']}:{self.db_config['port']}")
            return True
        except psycopg2.Error as e:
            logger.error(f"Erro ao conectar ao PostgreSQL: {e}")
            return False

    def desconectar(self):
        """Fecha a conexão com o banco de dados."""
        if self.connection:
            self.connection.close()
            logger.info("Desconectado do PostgreSQL")

    def buscar_ramais_ativos(self) -> List[Dict]:
        """
        Busca todos os ramais ativos no banco do Kamailio.
        
        Filtros aplicados:
        - expires > NOW() (registro ainda válido)
        - user_agent NÃO contém softphone
        
        Returns:
            Lista de dicionários com os dados dos ramais
            
        Raises:
            Exception: Se houver erro na query
        """
        if not self.connection:
            logger.error("Não há conexão ativa com o banco de dados")
            raise Exception("Conexão não estabelecida")
        
        query = """
        SELECT 
            username,
            contact,
            received,
            user_agent,
            expires
        FROM location
        WHERE expires > NOW()
        ORDER BY username
        """
        
        try:
            cursor = self.connection.cursor(cursor_factory=RealDictCursor)
            if self.limit:
                query += ' LIMIT %s'
                cursor.execute(query, (self.limit,))
            else:
                cursor.execute(query)
            resultado = cursor.fetchall()
            cursor.close()
            
            logger.info(f"Encontrados {len(resultado)} ramais ativos no Kamailio")
            return resultado if resultado else []
            
        except psycopg2.Error as e:
            logger.error(f"Erro ao buscar ramais ativos: {e}")
            raise

    def processar_ramais(self, ramais_brutos: List[Dict]) -> List[RamalInfo]:
        """
        Processa os dados brutos dos ramais, aplicando tratamentos e filtrando por blacklist ao final.
        """
        ramais_processados = []
        ramais_rejeitados = []
        
        for ramal_bruto in ramais_brutos:
            try:
                # Extrai dados básicos
                numero_ramal = DataParser.normalizar_numero_ramal(ramal_bruto.get('username'))
                user_agent = ramal_bruto.get('user_agent', '')
                contact = ramal_bruto.get('contact', '')
                received = ramal_bruto.get('received', '')
                expires = ramal_bruto.get('expires', '')
                
                # Filtra softphones
                if DataParser.eh_softphone(user_agent):
                    logger.info(f"Ramal {numero_ramal} rejeitado: é um softphone ({user_agent})")
                    ramais_rejeitados.append({
                        'numero': numero_ramal,
                        'motivo': 'Softphone detectado',
                        'user_agent': user_agent
                    })
                    continue
                
                # Extrai IP (tenta received primeiro, depois contact)
                ip = DataParser.extrair_ipv4(received) or DataParser.extrair_ipv4(contact)
                
                if not ip:
                    logger.warning(f"Ramal {numero_ramal}: IP não encontrado")
                    ramais_rejeitados.append({
                        'numero': numero_ramal,
                        'motivo': 'IP não encontrado',
                        'contact': contact,
                        'received': received
                    })
                    continue
                
                # Faz parsing de marca/modelo
                marca, modelo = DataParser.extrair_marca_modelo(user_agent)
                modelo = DataParser.normalizar_modelo(user_agent, modelo)
                
                # Cria objeto RamalInfo
                ramal = RamalInfo(
                    numero_ramal=numero_ramal,
                    ip=ip,
                    marca=marca,
                    modelo=modelo,
                    user_agent=user_agent,
                    expires=str(expires),
                    contact=contact
                )
                
                ramais_processados.append(ramal)
                logger.debug(f"✓ {ramal}")
                
            except Exception as e:
                logger.error(f"Erro ao processar ramal {numero_ramal}: {e}")
                ramais_rejeitados.append({
                    'numero': numero_ramal,
                    'motivo': 'Erro no processamento',
                    'erro': str(e)
                })
                continue

        # Filtragem pós-processamento da coleção completa via Blacklist
        ramais_validos, rejeitados_blacklist = DataParser.filtrar_blacklist(ramais_processados)
        ramais_rejeitados.extend(rejeitados_blacklist)

        # Log resumido
        logger.info(f"\n{'='*60}")
        logger.info(f"RESUMO DO PROCESSAMENTO")
        logger.info(f"{'='*60}")
        logger.info(f"Ramais processados com sucesso: {len(ramais_validos)}")
        logger.info(f"Ramais rejeitados: {len(ramais_rejeitados)}")
        logger.info(f"{'='*60}\n")
        
        if ramais_rejeitados:
            logger.info("Detalhes dos ramais rejeitados:")
            for rejeitado in ramais_rejeitados:
                logger.info(f"  - {rejeitado}")
        
        return ramais_validos

# ============================================================================
# INTEGRAÇÃO COM ZABBIX API
# ============================================================================

class SyncPlanner:
    """Decide ações exclusivamente a partir da identidade estável e do catálogo lido.

    A tag ``ramal`` é o único identificador persistente: é pesquisável pela API
    e não mistura identidade com a descrição ou demais atributos do host.
    """

    @staticmethod
    def build(ramais: List[RamalInfo], hosts: List[Dict[str, Any]], tag_name: str) -> SyncPlan:
        index: Dict[str, List[Dict[str, Any]]] = {}
        inconsistencies: List[str] = []
        for host in hosts:
            tags = [tag for tag in host.get('tags', []) if tag.get('tag') == tag_name]
            host_label = host.get('hostid') or host.get('host') or '<desconhecido>'
            if len(tags) != 1:
                inconsistencies.append(
                    f"Host {host_label} deve possuir exatamente uma tag '{tag_name}'"
                )
                continue
            numero = DataParser.normalizar_numero_ramal(tags[0].get('value'))
            if not numero:
                inconsistencies.append(f"Host {host_label} possui valor inválido na tag '{tag_name}'")
                continue
            index.setdefault(numero, []).append(host)

        actions: List[SyncAction] = []
        seen = set()
        for ramal in ramais:
            numero = DataParser.normalizar_numero_ramal(ramal.numero_ramal)
            if not numero:
                actions.append(SyncAction('invalid', ramal, reason='ramal vazio na origem'))
                continue
            if numero in seen:
                actions.append(SyncAction('invalid', ramal,
                                          reason=f'ramal duplicado na origem: {numero}'))
                continue
            seen.add(numero)
            candidates = index.get(numero, [])
            if len(candidates) > 1:
                actions.append(SyncAction('invalid', ramal, reason='mais de um host possui a mesma identidade'))
            elif candidates:
                actions.append(SyncAction('update', ramal, host=candidates[0]))
            else:
                actions.append(SyncAction('create', ramal))
        return SyncPlan(actions=actions, hosts_found=len(hosts), inconsistencies=inconsistencies)


class ZabbixPlanExecutor:
    """Executa ações já decididas; não contém regras de identificação ou planejamento."""

    def __init__(self, client: 'ZabbixAPI', group_id: str, template_id: Optional[str]):
        self.client = client
        self.group_id = group_id
        self.template_id = template_id

    def execute(self, plan: SyncPlan) -> int:
        issues = plan.validate()
        if issues:
            logger.error('Plano inválido; nenhuma ação será enviada ao Zabbix.')
            for issue in issues:
                logger.error('Inconsistência: %s', issue)
            return len(issues)

        errors = 0
        for item in plan.actions:
            try:
                if item.action == 'create':
                    success = self.client.criar_host(item.ramal, self.group_id, self.template_id)
                else:
                    success = self.client.atualizar_host(item.host, item.ramal, self.group_id, self.template_id)
                if not success:
                    errors += 1
            except Exception as exc:
                logger.error('Erro ao executar %s para ramal %s: %s', item.action, item.ramal.numero_ramal, exc)
                errors += 1
        return errors

class ZabbixAPI:
    """Classe para gerenciar integração com Zabbix via zabbix-utils"""

    def __init__(
        self,
        url: str = None,
        api_token: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
        group_name: str = 'Ramais',
        template_name: str = 'ICMP Ping',
        host_prefix: Optional[str] = None
    ):
        """
        Inicializa a conexão com o Zabbix.
        """
        # Permite receber o dicionário ZABBIX_CONFIG no construtor
        if isinstance(url, dict):
            config = url
            self.url = config.get('url')
            self.api_token = config.get('api_token')
            self.user = config.get('user')
            self.password = config.get('password')
            self.group_name = config.get('group_name', 'Ramais')
            self.template_name = config.get('template_name', 'ICMP Ping')
            self.host_prefix = config.get('host_prefix') or os.getenv('HOST_PREFIX', 'ORGANIZACAO')
        else:
            self.url = url or os.getenv('ZABBIX_URL', 'http://zabbix-web/zabbix/api_jsonrpc.php')
            self.api_token = api_token or os.getenv('ZABBIX_API_TOKEN')
            self.user = user or os.getenv('ZABBIX_USER')
            self.password = password or os.getenv('ZABBIX_PASSWORD')
            self.group_name = group_name
            self.template_name = template_name
            self.host_prefix = host_prefix or os.getenv('HOST_PREFIX', 'ORGANIZACAO')

        self.zapi = None
        self.last_report = SyncReport()

    RAMAL_TAG = 'ramal'

    def gerar_nome_visual(self, ramal: RamalInfo) -> str:
        """Gera o nome visual legado para hosts novos, sem usá-lo como identidade."""
        prefixo = (self.host_prefix or 'ORGANIZACAO').upper().strip()
        marca = (ramal.marca or 'GENERICO').upper().strip()
        modelo = (ramal.modelo or 'GENERICO').upper().strip()
        numero = (ramal.numero_ramal or '').strip()

        return f"{prefixo}-{marca}-{modelo}-RAMAL {numero}"

    # Compatibilidade para consumidores antigos da classe. O resultado é visual,
    # nunca deve ser usado para localizar um host durante a sincronização.
    gerar_hostname = gerar_nome_visual

    def gerar_hostname_tecnico(self, numero_ramal: str) -> str:
        """Retorna o identificador técnico estável de um ramal normalizado."""
        numero = DataParser.normalizar_numero_ramal(numero_ramal)
        if not numero:
            raise ValueError('Número de ramal inválido')
        return f'ramal-{numero}'

    def _tags_ramal(self, numero_ramal: str) -> List[Dict[str, str]]:
        return [{'tag': self.RAMAL_TAG, 'value': DataParser.normalizar_numero_ramal(numero_ramal)}]

    def _description(self, ramal: RamalInfo) -> str:
        return f"User-Agent: {ramal.user_agent or 'não informado'}"

    # Refatorado para usar nativamente a inicialização e autenticação da biblioteca zabbix-utils
    def autenticar(
        self,
        url: str = None,
        api_token: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None
    ) -> bool:
        """Autentica no Zabbix utilizando a biblioteca zabbix-utils."""
        self.url = url or self.url
        self.api_token = api_token or self.api_token
        self.user = user or self.user
        self.password = password or self.password

        try:
            self.zapi = ZabbixAPIClient(url=self.url)

            if self.api_token:
                logger.info("Autenticando no Zabbix via Token de API (zabbix-utils)...")
                self.zapi.login(token=self.api_token)
            elif self.user and self.password:
                logger.info("Autenticando no Zabbix via Usuário/Senha (zabbix-utils)...")
                self.zapi.login(user=self.user, password=self.password)
            else:
                logger.error("Nenhum método de autenticação fornecido (Token ou Usuário/Senha)")
                self.zapi = None
                return False

            # Teste de conexão/versão utilizando método nativo da biblioteca
            version_info = self.zapi.api_version()
            if version_info:
                logger.info(f"Conexão com Zabbix bem-sucedida. Versão API: {version_info}")
                return True

            logger.error("Falha ao obter versão do Zabbix. Verifique credenciais.")
            return False

        except Exception as e:
            logger.error(f"Erro inesperado na autenticação com Zabbix: {e}")
            return False

    def criar_host(self, ramal: RamalInfo, group_id: str, template_id: Optional[str] = None) -> bool:
        """Cria um host no Zabbix utilizando zabbix-utils."""
        if not self.zapi:
            logger.error("ZabbixAPI não inicializado. Chame autenticar() primeiro.")
            return False

        try:
            numero = DataParser.normalizar_numero_ramal(ramal.numero_ramal)
            hostname_tecnico = self.gerar_hostname_tecnico(numero)
            params = {
                'host': hostname_tecnico,
                'name': self.gerar_nome_visual(ramal),
                'tags': self._tags_ramal(numero),
                'description': self._description(ramal),
                'interfaces': [{
                    'type': 1,  # Agent
                    'main': 1,
                    'useip': 1,
                    'ip': ramal.ip,
                    'dns': '',
                    'port': '10050'
                }],
                'groups': [{'groupid': group_id}]
            }

            if template_id:
                params['templates'] = [{'templateid': template_id}]

            result = self.zapi.host.create(**params)
            if result and 'hostids' in result:
                logger.info(f"Host '{hostname_tecnico}' criado com sucesso no Zabbix (ID: {result['hostids'][0]})")
                return True

            logger.error(f"Falha ao criar host '{hostname_tecnico}' no Zabbix")
            return False

        except Exception as e:
            logger.error(f"Erro inesperado ao criar host do ramal '{ramal.numero_ramal}': {e}")
            return False

    def atualizar_host(self, host: Dict[str, Any], ramal: RamalInfo, group_id: str,
                        template_id: Optional[str] = None) -> bool:
        """Atualiza atributos mutáveis e grava a tag de identidade persistente."""
        if not self.zapi:
            logger.error("ZabbixAPI não inicializado. Chame autenticar() primeiro.")
            return False

        try:
            host_id = host['hostid']
            interfaces = host.get('interfaces', [])

            # Atualização das interfaces de rede utilizando o id existente quando disponível
            if interfaces:
                interface_id = interfaces[0]['interfaceid']
                interface_params = [{
                    'interfaceid': interface_id,
                    'type': 1,
                    'main': 1,
                    'useip': 1,
                    'ip': ramal.ip,
                    'dns': '',
                    'port': '10050'
                }]
            else:
                interface_params = [{
                    'type': 1,
                    'main': 1,
                    'useip': 1,
                    'ip': ramal.ip,
                    'dns': '',
                    'port': '10050'
                }]

            params = {
                'hostid': host_id,
                'host': self.gerar_hostname_tecnico(ramal.numero_ramal),
                'name': self.gerar_nome_visual(ramal),
                'description': self._description(ramal),
                'interfaces': interface_params,
                'groups': [{'groupid': group_id}],
                'tags': self._tags_ramal(ramal.numero_ramal)
            }

            if template_id:
                params['templates'] = [{'templateid': template_id}]

            # Atualização do host via zabbix-utils
            update_result = self.zapi.host.update(**params)
            if update_result and 'hostids' in update_result:
                logger.info(f"Host '{host.get('host', host_id)}' atualizado com sucesso no Zabbix")
                return True

            logger.error(f"Falha ao atualizar host '{host_id}'")
            return False

        except Exception as e:
            logger.error(f"Erro inesperado ao atualizar host '{host_id}': {e}")
            return False

    # Refatorado para consulta nativa do id do grupo via zabbix-utils
    def obter_id_grupo(self, grupo_nome: str) -> Optional[str]:
        """Obtém o ID do grupo de hosts pelo nome utilizando zabbix-utils."""
        if not self.zapi:
            return None

        try:
            result = self.zapi.hostgroup.get(filter={'name': grupo_nome})
            if result and len(result) > 0:
                return result[0]['groupid']

            logger.warning(f"Grupo '{grupo_nome}' não encontrado no Zabbix")
            return None

        except Exception as e:
            logger.error(f"Erro ao obter ID do grupo '{grupo_nome}' via zabbix-utils: {e}")
            return None

    # Refatorado para consulta nativa do id do template via zabbix-utils
    def obter_id_template(self, template_nome: str) -> Optional[str]:
        """Obtém o ID do template pelo nome utilizando zabbix-utils."""
        if not self.zapi:
            return None

        try:
            result = self.zapi.template.get(filter={'name': template_nome})
            if result and len(result) > 0:
                return result[0]['templateid']

            # Fallback buscando pelo campo 'host' do template
            result = self.zapi.template.get(filter={'host': template_nome})
            if result and len(result) > 0:
                return result[0]['templateid']

            logger.warning(f"Template '{template_nome}' não encontrado no Zabbix")
            return None

        except Exception as e:
            logger.error(f"Erro ao obter ID do template '{template_nome}' via zabbix-utils: {e}")
            return None

    def _catalogar_hosts(self) -> List[Dict[str, Any]]:
        """Busca hosts gerenciados exclusivamente pela tag persistente do ramal."""
        return self.zapi.host.get(
            tags=[{'tag': self.RAMAL_TAG}], output=['hostid', 'host', 'name'],
            selectInterfaces=['interfaceid', 'ip', 'main'], selectTags='extend'
        ) or []

    def planejar_sincronizacao(self, ramais: List[RamalInfo]) -> SyncPlan:
        """Consulta o catálogo por tag e delega a decisão ao planejador puro."""
        return SyncPlanner.build(ramais, self._catalogar_hosts(), self.RAMAL_TAG)

    def sincronizar_ramais(self, ramais: List[RamalInfo], dry_run: bool = False,
                           report: Optional[SyncReport] = None) -> bool:
        """Sincroniza por identidade persistente; no dry-run apenas produz o plano."""
        report = report or SyncReport(dry_run=dry_run)
        report.dry_run = dry_run
        self.last_report = report

        # Validação independente da API: duplicidades e ramais inválidos são
        # rejeitados antes mesmo da primeira chamada ao Zabbix.
        source_plan = SyncPlanner.build(ramais, [], self.RAMAL_TAG)
        if not source_plan.is_valid:
            report.plan = source_plan
            report.created = source_plan.count('create')
            report.updated = source_plan.count('update')
            report.inconsistencies = source_plan.validate()
            report.errors = len(report.inconsistencies)
            logger.error('Plano de origem inválido; nenhuma chamada ao Zabbix será realizada.')
            return False

        if not self.autenticar():
            report.errors = 1
            return False

        grupo_id = self.obter_id_grupo(self.group_name)
        template_id = self.obter_id_template(self.template_name)

        if not grupo_id:
            logger.error(f"Não foi possível obter ID do grupo '{self.group_name}'")
            report.errors = 1
            return False

        if not template_id:
            logger.warning(f"Template '{self.template_name}' não encontrado. Criando hosts sem template.")

        plano = self.planejar_sincronizacao(ramais)
        report.plan = plano
        report.hosts_found = plano.hosts_found
        report.created = plano.count('create')
        report.updated = plano.count('update')
        report.inconsistencies = plano.validate()
        for item in plano.actions:
            if item.action == 'invalid':
                logger.error("Ramal %s: %s", item.ramal.numero_ramal, item.reason)
            else:
                logger.info("%s: ramal %s", item.action.upper(), item.ramal.numero_ramal)

        if dry_run:
            logger.info("DRY-RUN: criaria=%s atualizaria=%s inconsistentes=%s",
                        report.created, report.updated, len(report.inconsistencies))
            report.errors = len(report.inconsistencies)
            return plano.is_valid

        # O executor só pode receber um plano inteiramente validado. Assim,
        # nenhuma alteração parcial é enviada quando há identidade ambígua.
        if not plano.is_valid:
            logger.error('Plano de sincronização inválido; nenhuma alteração será enviada ao Zabbix.')
            report.errors = len(report.inconsistencies)
            return False

        report.errors = ZabbixPlanExecutor(self, grupo_id, template_id).execute(plano)

        logger.info(f"\n{'='*60}")
        logger.info(f"SINCRONIZAÇÃO COM ZABBIX CONCLUÍDA")
        logger.info(f"{'='*60}")
        logger.info(f"Hosts criados: {report.created}")
        logger.info(f"Hosts atualizados: {report.updated}")
        logger.info(f"Erros: {report.errors}")
        logger.info(f"{'='*60}\n")

        return report.errors == 0


# ============================================================================
# FUNÇÃO PRINCIPAL
# ============================================================================

def gerar_relatorio_inspecao(ramais_brutos: List[Dict], ramais_processados: List[RamalInfo], ramais_rejeitados: List[Dict]) -> str:
    """Gera um relatório legível para inspeção dos dados crus e parseados."""
    linhas = []
    linhas.append('=' * 80)
    linhas.append('RELATÓRIO DE INSPEÇÃO DE DADOS')
    linhas.append('=' * 80)
    linhas.append('')
    linhas.append('Dados brutos retornados pelo banco:')
    if ramais_brutos:
        for item in ramais_brutos:
            linhas.append(f"- username={item.get('username')} | contact={item.get('contact')} | received={item.get('received')} | user_agent={item.get('user_agent')} | expires={item.get('expires')}")
    else:
        linhas.append('- Nenhum dado bruto encontrado')

    linhas.append('')
    linhas.append('Dados parseados:')
    if ramais_processados:
        for ramal in ramais_processados:
            linhas.append(
                f"- Ramal {ramal.numero_ramal} | IP={ramal.ip} | Marca={ramal.marca} | Modelo={ramal.modelo} | "
                f"UserAgent={ramal.user_agent} | Expires={ramal.expires} | Contact={ramal.contact}"
            )
    else:
        linhas.append('- Nenhum dado parseado')

    linhas.append('')
    linhas.append('Ramais rejeitados:')
    if ramais_rejeitados:
        for rejeitado in ramais_rejeitados:
            linhas.append(f"- numero={rejeitado.get('numero')} | motivo={rejeitado.get('motivo')} | detalhes={rejeitado}")
    else:
        linhas.append('- Nenhum ramal rejeitado')

    linhas.append('')
    linhas.append('=' * 80)
    return '\n'.join(linhas)


def _normalizar_para_json(valor: Any) -> Any:
    """Converte valores não serializáveis em tipos JSON-safe."""
    if isinstance(valor, (datetime, date)):
        return valor.isoformat()
    if isinstance(valor, dict):
        return {str(key): _normalizar_para_json(value) for key, value in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [_normalizar_para_json(item) for item in valor]
    return valor


def salvar_inspecao_json(ramais_brutos: List[Dict], ramais_processados: List[RamalInfo], ramais_rejeitados: List[Dict], output_path: Optional[str] = None) -> str:
    """Salva a inspeção em um arquivo JSON para análise externa."""
    if not output_path:
        output_path = os.path.join(os.getcwd(), 'inspecao_ramal.json')

    payload = {
        'dados_brutos': [
            {
                'username': item.get('username'),
                'username_normalizado': DataParser.normalizar_numero_ramal(item.get('username')),
                'contact': item.get('contact'),
                'received': item.get('received'),
                'user_agent': item.get('user_agent'),
                'expires': _normalizar_para_json(item.get('expires'))
            }
            for item in ramais_brutos
        ],
        'dados_parseados': [
            {
                'username': ramal.numero_ramal,
                'numero_ramal': ramal.numero_ramal,
                'ip': ramal.ip,
                'marca': ramal.marca,
                'modelo': ramal.modelo,
                'user_agent': ramal.user_agent,
                'expires': _normalizar_para_json(ramal.expires),
                'contact': ramal.contact
            }
            for ramal in ramais_processados
        ],
        'ramais_rejeitados': _normalizar_para_json(ramais_rejeitados),
        'gerado_em': datetime.now().isoformat()
    }

    with open(output_path, 'w', encoding='utf-8') as handle:
        json.dump(_normalizar_para_json(payload), handle, indent=2, ensure_ascii=False)

    logger.info(f"Inspeção salva em {output_path}")
    return output_path


def main(dry_run: Optional[bool] = None, apenas_inspecao: bool = False):
    """Função principal de orquestração."""
    if dry_run is None:
        dry_run = parse_bool(os.getenv('DRY_RUN', 'False'))
    report = SyncReport(dry_run=dry_run)

    logger.info("Iniciando sincronização Kamailio → Zabbix")
    logger.info(f"Timestamp: {datetime.now().isoformat()}\n")

    if dry_run:
        logger.info("Modo dry-run ativo: consultas ao banco/Zabbix são permitidas; nenhuma alteração será enviada.")

    if apenas_inspecao:
        logger.info("Modo inspeção ativo: apenas consultando os dados do banco e imprimindo relatório.")
        db = KamailioDB(DB_CONFIG, limit=get_development_limit())
        if not db.conectar():
            logger.error("Falha na conexão com o banco de dados. Abortando.")
            return False
        try:
            ramais_brutos = db.buscar_ramais_ativos()
            ramais_processados = db.processar_ramais(ramais_brutos)
            relatorio = gerar_relatorio_inspecao(ramais_brutos, ramais_processados, [])
            output_path = salvar_inspecao_json(ramais_brutos, ramais_processados, [], output_path=os.path.join(os.getcwd(), 'inspecao_ramal.json'))
            print(relatorio)
            print(f'\nArquivo JSON salvo em: {output_path}')
            return True
        finally:
            db.desconectar()
            logger.info("Inspeção finalizada")
    
    # Conecta ao banco do Kamailio
    development_limit = get_development_limit()
    if development_limit:
        logger.info("LIMIT de desenvolvimento ativo: %s ramais", development_limit)
    db = KamailioDB(DB_CONFIG, limit=development_limit)
    
    if not db.conectar():
        logger.error("Falha na conexão com o banco de dados. Abortando.")
        return False
    
    try:
        # Busca ramais ativos
        logger.info("Buscando ramais ativos no banco de dados...")
        ramais_brutos = db.buscar_ramais_ativos()
        
        if not ramais_brutos:
            logger.warning("Nenhum ramal encontrado no banco de dados")
            return False
        
        # Processa os dados
        logger.info("Processando dados dos ramais...")
        ramais_processados = db.processar_ramais(ramais_brutos)
        
        if not ramais_processados:
            logger.warning("Nenhum ramal válido após processamento")
            return False
        
        # Sincroniza ramais com Zabbix
        logger.info(f"\nSincronizando {len(ramais_processados)} ramais com Zabbix...")
        zabbix = ZabbixAPI(ZABBIX_CONFIG)
        report.records_read = len(ramais_brutos)
        report.valid_records = len(ramais_processados)
        report.ignored_records = len(ramais_brutos) - len(ramais_processados)
        resultado_sync = zabbix.sincronizar_ramais(
            ramais_processados, dry_run=dry_run, report=report
        )
        report.finalize()
        logger.info(report.format())

        return resultado_sync
        
    except Exception as e:
        logger.error(f"Erro durante a execução: {e}", exc_info=True)
        return False
    
    finally:
        db.desconectar()
        logger.info("Sincronização finalizada")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Sincroniza ramais Kamailio para Zabbix')
    parser.add_argument('--dry-run', action='store_true', help='Exibe o plano de criação/atualização sem alterar o Zabbix')
    parser.add_argument('--inspecao', action='store_true', help='Consulta o banco e imprime relatório de dados brutos e parseados sem acessar o Zabbix')
    args = parser.parse_args()

    sucesso = main(dry_run=args.dry_run, apenas_inspecao=args.inspecao)
    exit(0 if sucesso else 1)
