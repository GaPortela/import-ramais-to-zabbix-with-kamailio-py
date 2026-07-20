#!/usr/bin/env python3
"""
Kamailio to Zabbix Synchronization Script
Sincroniza ramais ativos do Kamailio com hosts no Zabbix
"""

import argparse
import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote_plus

import psycopg2
from dotenv import load_dotenv
from psycopg2.extras import RealDictCursor

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
        'api_token': os.getenv('ZABBIX_API_TOKEN') or None,  # Preferência 1: Token de API
        'user': os.getenv('ZABBIX_USER') or None,  # Preferência 2: Usuário (fallback)
        'password': os.getenv('ZABBIX_PASSWORD') or None,  # Preferência 2: Senha (fallback)
        'group_name': os.getenv('ZABBIX_GROUP_NAME', 'Ramais'),
        'template_name': os.getenv('ZABBIX_TEMPLATE_NAME', 'ICMP Ping')
    }


def parse_bool(value: Optional[str]) -> bool:
    """Converte valores de ambiente para booleanos."""
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {'1', 'true', 'yes', 'y', 'on'}


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

    @staticmethod
    def extrair_ipv4(contact_uri: str) -> Optional[str]:
        """
        Extrai o IPv4 de uma URI SIP usando Regex.
        
        Args:
            contact_uri: String contendo a URI SIP (ex: "sip:3000@192.168.1.50:5060")
            
        Returns:
            IP extraído (ex: "192.168.1.50") ou None se não encontrado
            
        Example:
            >>> DataParser.extrair_ipv4("sip:3000@192.168.1.50:5060")
            '192.168.1.50'
        """
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

    def __init__(self, db_config: Dict):
        """
        Inicializa a conexão com o banco de dados.
        
        Args:
            db_config: Dicionário com credenciais (host, port, database, user, password)
        """
        self.db_config = db_config
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
        Processa os dados brutos dos ramais, aplicando tratamentos.
        
        Args:
            ramais_brutos: Lista de dicionários retornada do banco
            
        Returns:
            Lista de objetos RamalInfo processados e filtrados
        """
        ramais_processados = []
        ramais_rejeitados = []
        
        for ramal_bruto in ramais_brutos:
            try:
                # Extrai dados básicos
                numero_ramal = str(ramal_bruto['username'])
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
                    logger.warning(f"Ramal {numero_ramal}: Não foi possível extrair IP de '{contact}' ou '{received}'")
                    ramais_rejeitados.append({
                        'numero': numero_ramal,
                        'motivo': 'IP não encontrado',
                        'contact': contact,
                        'received': received
                    })
                    continue
                
                # Faz parsing de marca/modelo
                marca, modelo = DataParser.extrair_marca_modelo(user_agent)
                
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
        
        # Log resumido
        logger.info(f"\n{'='*60}")
        logger.info(f"RESUMO DO PROCESSAMENTO")
        logger.info(f"{'='*60}")
        logger.info(f"Ramais processados com sucesso: {len(ramais_processados)}")
        logger.info(f"Ramais rejeitados: {len(ramais_rejeitados)}")
        logger.info(f"{'='*60}\n")
        
        if ramais_rejeitados:
            logger.info("Detalhes dos ramais rejeitados:")
            for rejeitado in ramais_rejeitados:
                logger.info(f"  - {rejeitado}")
        
        return ramais_processados


# ============================================================================
# INTEGRAÇÃO COM ZABBIX API
# ============================================================================

class ZabbixAPI:
    """Classe para gerenciar integração com Zabbix via JSON-RPC API"""
    
    def __init__(self, config: Dict):
        """
        Inicializa conexão com Zabbix.
        
        Args:
            config: Dicionário com:
                - url: URL da API do Zabbix
                - api_token: Token de API (recomendado)
                - user: Usuário do Zabbix (alternativa se não houver token)
                - password: Senha do Zabbix (alternativa se não houver token)
                - group_name: Nome do grupo de hosts
                - template_name: Nome do template a aplicar
        """
        self.url = config.get('url')
        self.api_token = config.get('api_token')
        self.user = config.get('user')
        self.password = config.get('password')
        self.group_name = config.get('group_name')
        self.template_name = config.get('template_name')
        self.auth_token = None
        self.session = None
        
        self._init_session()
    
    def _init_session(self):
        """Inicializa a sessão HTTP."""
        import requests
        self.session = requests.Session()
        self.session.headers.update({'Content-Type': 'application/json'})
    
    def autenticar(self) -> bool:
        """
        Autentica com Zabbix usando token de API ou usuário/senha.
        
        Returns:
            True se autenticado com sucesso, False caso contrário
        """
        try:
            # Tenta usar token de API (recomendado)
            if self.api_token:
                logger.info("Autenticando no Zabbix com token de API")
                self.auth_token = self.api_token
                # Valida o token fazendo uma chamada simples
                return self._validar_token()
            
            # Fallback: usa usuário e senha
            elif self.user and self.password:
                logger.info("Autenticando no Zabbix com usuário/senha")
                return self._autenticar_usuario_senha()
            
            else:
                logger.error("Nenhum método de autenticação fornecido (token ou usuário/senha)")
                return False
                
        except Exception as e:
            logger.error(f"Erro durante autenticação Zabbix: {e}")
            return False
    
    def _validar_token(self) -> bool:
        """Valida o token de API fazendo uma chamada simples."""
        try:
            payload = {
                'jsonrpc': '2.0',
                'method': 'apiinfo.version',
                'auth': self.auth_token,
                'id': 1
            }
            
            response = self.session.post(self.url, json=payload)
            result = response.json()
            
            if 'result' in result:
                logger.info(f"Token de API validado com sucesso. Zabbix versão: {result['result']}")
                return True
            elif 'error' in result:
                logger.error(f"Erro de autenticação com token: {result['error']}")
                return False
            
            return False
            
        except Exception as e:
            logger.error(f"Erro ao validar token: {e}")
            return False
    
    def _autenticar_usuario_senha(self) -> bool:
        """Autentica com usuário e senha (método legado)."""
        try:
            payload = {
                'jsonrpc': '2.0',
                'method': 'user.login',
                'params': {
                    'username': self.user,
                    'password': self.password
                },
                'id': 1
            }
            
            response = self.session.post(self.url, json=payload)
            result = response.json()
            
            if 'result' in result:
                self.auth_token = result['result']
                logger.info("Autenticação com usuário/senha bem-sucedida")
                return True
            elif 'error' in result:
                logger.error(f"Erro de autenticação: {result['error']}")
                return False
            
            return False
            
        except Exception as e:
            logger.error(f"Erro ao autenticar com usuário/senha: {e}")
            return False
    
    def _fazer_chamada_api(self, method: str, params: Dict = None) -> Optional[Dict]:
        """
        Faz uma chamada à API do Zabbix.
        
        Args:
            method: Método da API (ex: 'host.create', 'host.update')
            params: Parâmetros do método
            
        Returns:
            Resultado da chamada ou None em caso de erro
        """
        try:
            payload = {
                'jsonrpc': '2.0',
                'method': method,
                'params': params or {},
                'auth': self.auth_token,
                'id': 1
            }
            
            response = self.session.post(self.url, json=payload)
            result = response.json()
            
            if 'result' in result:
                return result['result']
            elif 'error' in result:
                logger.error(f"Erro na chamada API {method}: {result['error']}")
                return None
            
            return None
            
        except Exception as e:
            logger.error(f"Erro ao fazer chamada à API: {e}")
            return None
    
    def obter_id_grupo(self, grupo_nome: str) -> Optional[str]:
        """Obtém o ID do grupo de hosts pelo nome."""
        try:
            result = self._fazer_chamada_api('hostgroup.get', {
                'filter': {'name': grupo_nome}
            })
            
            if result and len(result) > 0:
                return result[0]['groupid']
            
            logger.warning(f"Grupo '{grupo_nome}' não encontrado")
            return None
            
        except Exception as e:
            logger.error(f"Erro ao obter ID do grupo: {e}")
            return None
    
    def obter_id_template(self, template_nome: str) -> Optional[str]:
        """Obtém o ID do template pelo nome."""
        try:
            result = self._fazer_chamada_api('template.get', {
                'filter': {'name': template_nome}
            })
            
            if result and len(result) > 0:
                return result[0]['templateid']
            
            logger.warning(f"Template '{template_nome}' não encontrado")
            return None
            
        except Exception as e:
            logger.error(f"Erro ao obter ID do template: {e}")
            return None
    
    def host_existe(self, hostname: str) -> bool:
        """Verifica se um host já existe no Zabbix."""
        try:
            result = self._fazer_chamada_api('host.get', {
                'filter': {'name': hostname}
            })
            return bool(result and len(result) > 0)
        except Exception as e:
            logger.error(f"Erro ao verificar existência do host: {e}")
            return False
    
    def sincronizar_ramais(self, ramais: List[RamalInfo]) -> bool:
        """
        Sincroniza lista de ramais com Zabbix.
        
        Args:
            ramais: Lista de objetos RamalInfo
            
        Returns:
            True se sincronização bem-sucedida, False caso contrário
        """
        if not self.autenticar():
            logger.error("Falha na autenticação com Zabbix")
            return False
        
        # Obtém IDs necessários
        grupo_id = self.obter_id_grupo(self.group_name)
        template_id = self.obter_id_template(self.template_name)
        
        if not grupo_id:
            logger.error(f"Não foi possível obter ID do grupo '{self.group_name}'")
            return False
        
        if not template_id:
            logger.warning(f"Template '{self.template_name}' não encontrado. Criando hosts sem template.")
        
        hosts_criados = 0
        hosts_atualizados = 0
        hosts_erro = 0
        
        for ramal in ramais:
            try:
                hostname = f"RAMAL-{ramal.numero_ramal}"
                
                if self.host_existe(hostname):
                    # Atualiza host existente
                    logger.debug(f"Atualizando host {hostname}")
                    # Implementar atualização se necessário
                    hosts_atualizados += 1
                else:
                    # Cria novo host
                    params = {
                        'host': hostname,
                        'name': f"Ramal {ramal.numero_ramal} ({ramal.marca} {ramal.modelo})",
                        'groups': [{'groupid': grupo_id}],
                        'interfaces': [{
                            'type': 1,  # Zabbix agent
                            'main': 1,
                            'ip': ramal.ip,
                            'port': '10050'
                        }],
                    }
                    
                    if template_id:
                        params['templates'] = [{'templateid': template_id}]
                    
                    result = self._fazer_chamada_api('host.create', params)
                    
                    if result:
                        logger.info(f"✓ Host criado: {hostname} ({ramal.ip})")
                        hosts_criados += 1
                    else:
                        logger.error(f"✗ Erro ao criar host {hostname}")
                        hosts_erro += 1
                        
            except Exception as e:
                logger.error(f"Erro ao processar ramal {ramal.numero_ramal}: {e}")
                hosts_erro += 1
                continue
        
        # Log resumido
        logger.info(f"\n{'='*60}")
        logger.info(f"SINCRONIZAÇÃO COM ZABBIX CONCLUÍDA")
        logger.info(f"{'='*60}")
        logger.info(f"Hosts criados: {hosts_criados}")
        logger.info(f"Hosts atualizados: {hosts_atualizados}")
        logger.info(f"Erros: {hosts_erro}")
        logger.info(f"{'='*60}\n")
        
        return hosts_erro == 0


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

    logger.info("Iniciando sincronização Kamailio → Zabbix")
    logger.info(f"Timestamp: {datetime.now().isoformat()}\n")

    if dry_run:
        logger.info("Modo dry-run ativo: nenhuma conexão com o banco ou Zabbix será realizada.")
        return True

    if apenas_inspecao:
        logger.info("Modo inspeção ativo: apenas consultando os dados do banco e imprimindo relatório.")
        db = KamailioDB(DB_CONFIG)
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
    db = KamailioDB(DB_CONFIG)
    
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
        resultado_sync = zabbix.sincronizar_ramais(ramais_processados)
        
        return resultado_sync
        
    except Exception as e:
        logger.error(f"Erro durante a execução: {e}", exc_info=True)
        return False
    
    finally:
        db.desconectar()
        logger.info("Sincronização finalizada")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Sincroniza ramais Kamailio para Zabbix')
    parser.add_argument('--dry-run', action='store_true', help='Executa apenas o fluxo de validação sem acessar o banco/Zabbix')
    parser.add_argument('--inspecao', action='store_true', help='Consulta o banco e imprime relatório de dados brutos e parseados sem acessar o Zabbix')
    args = parser.parse_args()

    sucesso = main(dry_run=args.dry_run, apenas_inspecao=args.inspecao)
    exit(0 if sucesso else 1)
