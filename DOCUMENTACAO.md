# Kamailio to Zabbix Synchronization Script
## Documentação Técnica Completa

---

## 📋 Índice
1. [Visão Geral](#visão-geral)
2. [Arquitetura](#arquitetura)
3. [Instalação e Configuração](#instalação-e-configuração)
4. [Estrutura do Projeto](#estrutura-do-projeto)
5. [Testes Unitários](#testes-unitários)
6. [Guia de Uso](#guia-de-uso)
7. [Próximas Etapas](#próximas-etapas)
8. [Troubleshooting](#troubleshooting)

---

## Visão Geral

Este projeto automatiza a sincronização entre o **Kamailio** (servidor SIP) e o **Zabbix** (plataforma de monitoramento).

### Fluxo Principal
```
┌─────────────────────────────────────────────────────────────┐
│  KAMAILIO DATABASE (PostgreSQL)                             │
│  Tabela: location (ramais ativos)                           │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│  PROCESSAMENTO DE DADOS                                     │
│  ✓ Extração de IPv4 (Regex)                                 │
│  ✓ Parsing de User-Agent (marca/modelo)                     │
│  ✓ Filtragem de softphones                                  │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│  ZABBIX API                                                 │
│  ✓ Criar hosts (se não existem)                             │
│  ✓ Atualizar interfaces (IP)                                │
│  ✓ Vincular templates                                       │
└─────────────────────────────────────────────────────────────┘
```

---

## Arquitetura

### Camadas do Projeto

```
kamailio_zabbix_sync.py
├── Configuração (DB_CONFIG, ZABBIX_CONFIG)
├── Classes
│   ├── RamalInfo (Data Model)
│   ├── DataParser (Processamento de dados)
│   │   ├── extrair_ipv4()
│   │   ├── eh_softphone()
│   │   └── extrair_marca_modelo()
│   └── KamailioDB (Acesso ao banco)
│       ├── conectar()
│       ├── buscar_ramais_ativos()
│       └── processar_ramais()
└── main() (Orquestração)
```

### Componentes Principais

#### 1. **DataParser** - Tratamento de Dados
Responsável por normalizar e validar dados vindos do banco.

**Métodos:**

| Método | Entrada | Saída | Descrição |
|--------|---------|-------|-----------|
| `extrair_ipv4()` | URI SIP | IP ou None | Extrai IPv4 usando Regex |
| `eh_softphone()` | User-Agent | Bool | Detecta se é softphone |
| `extrair_marca_modelo()` | User-Agent | (str, str) | Parseia marca e modelo |

**Exemplos:**

```python
# Extração de IP
DataParser.extrair_ipv4("sip:3000@192.168.1.50:5060")
# → "192.168.1.50"

# Detecção de softphone
DataParser.eh_softphone("MicroSIP v2.0")
# → True (será rejeitado)

# Parsing de marca/modelo
DataParser.extrair_marca_modelo("Intelbras TIP125 v1.0")
# → ("INTELBRAS", "TIP125")
```

#### 2. **KamailioDB** - Acesso ao Banco

Gerencia conexão e queries ao PostgreSQL do Kamailio.

```python
db = KamailioDB(DB_CONFIG)
db.conectar()
ramais_brutos = db.buscar_ramais_ativos()
ramais_processados = db.processar_ramais(ramais_brutos)
db.desconectar()
```

#### 3. **RamalInfo** - Modelo de Dados

Representa um ramal processado e validado.

```python
@dataclass
class RamalInfo:
    numero_ramal: str    # "3000"
    ip: str              # "192.168.1.50"
    marca: str           # "INTELBRAS"
    modelo: str          # "TIP125"
    user_agent: str      # User-Agent original
    expires: str         # Timestamp de expiração
    contact: str         # URI SIP completo
```

---

## Instalação e Configuração

### 1. Pré-requisitos

- Python 3.8+
- PostgreSQL (instalado no servidor Kamailio)
- Acesso à API do Zabbix
- pip (gerenciador de pacotes Python)

### 2. Instalação

```bash
# Clone ou copie os arquivos para seu servidor
cd /caminho/do/projeto

# Crie um ambiente virtual (recomendado)
python3 -m venv venv
source venv/bin/activate  # No Windows: venv\Scripts\activate

# Instale as dependências
pip install -r requirements.txt
```

### 3. Configuração

```bash
# Copie o arquivo de exemplo
cp .env.example .env

# Edite com suas credenciais
nano .env  # ou seu editor preferido
```

**Campos obrigatórios:**
- `KAMAILIO_DB_URL` ou (`KAMAILIO_DB_HOST`, `KAMAILIO_DB_USER`, `KAMAILIO_DB_PASSWORD`)
- `ZABBIX_URL`, `ZABBIX_USER`, `ZABBIX_PASSWORD`

`KAMAILIO_DB_URL` tem prioridade quando definido. Caso não seja informado, a URL será criada automaticamente a partir das variáveis:
- `KAMAILIO_DB_HOST`
- `KAMAILIO_DB_PORT`
- `KAMAILIO_DB_NAME`
- `KAMAILIO_DB_USER`
- `KAMAILIO_DB_PASSWORD`

Exemplo de URL gerada automaticamente:
```env
postgresql://kamailio:senha@localhost:5432/kamailio
```

### 4. Teste de Conectividade

```bash
# Teste conexão com PostgreSQL
python3 -c "import psycopg2; psycopg2.connect(host='localhost', database='kamailio', user='kamailio', password='senha')"

# Se sucesso, não retorna erro
```

### 5. Uso com Docker

```bash
docker build -t kamailio-zabbix-sync .
docker run --rm --env-file .env kamailio-zabbix-sync
```

Para rodar em modo dry-run:

```bash
docker run --rm --env-file .env kamailio-zabbix-sync python kamailio_zabbix_sync.py --dry-run
```

---

## Estrutura do Projeto

```
projeto/
├── kamailio_zabbix_sync.py          # Script principal
├── test_data_parser.py               # Testes unitários
├── requirements.txt                  # Dependências Python
├── .env.example                      # Configuração de exemplo
├── DOCUMENTACAO.md                   # Esta documentação
├── kamailio_zabbix_sync.log          # Log gerado na execução
└── venv/                             # Ambiente virtual (criado)
```

---

## Testes Unitários

### Executar Testes

```bash
# Rode todos os testes
python3 -m pytest test_data_parser.py -v

# Rode com cobertura
python3 -m pytest test_data_parser.py --cov=kamailio_zabbix_sync

# Rode um teste específico
python3 -m pytest test_data_parser.py::TestExtrairIPv4::test_ipv4_em_uri_sip_com_porta -v
```

### Cobertura de Testes

**Classes de teste:**

1. **TestExtrairIPv4** (10 testes)
   - Validação de URIs SIP
   - Casos extremos (0.0.0.0, 255.255.255.255)
   - IPs inválidos

2. **TestEhSoftphone** (10 testes)
   - Detecção de softphones (MicroSIP, Zoiper, etc)
   - Case-insensitive
   - Telefones físicos não devem ser detectados

3. **TestExtrairMarcaModelo** (13 testes)
   - Parsing de marcas: Intelbras, Yealink, Grandstream, Cisco, Polycom, Avaya
   - Modelos específicos
   - Fallback para "GENERICO"

4. **TestIntegracaoParsing** (3 testes)
   - Fluxo completo de validação
   - Cenários reais de ramal válido/inválido

**Total: 36 testes unitários**

### Exemplo de Saída

```
$ python3 -m pytest test_data_parser.py -v

test_data_parser.py::TestExtrairIPv4::test_ipv4_em_uri_sip_com_porta PASSED
test_data_parser.py::TestExtrairIPv4::test_ipv4_em_uri_sip_sem_porta PASSED
test_data_parser.py::TestEhSoftphone::test_microsip_detectado PASSED
test_data_parser.py::TestExtrairMarcaModelo::test_intelbras_tip125 PASSED
...

====== 36 passed in 0.45s ======
```

---

## Guia de Uso

### Execução Básica

```bash
# Ativar ambiente virtual
source venv/bin/activate

# Executar script
python3 kamailio_zabbix_sync.py
```

### Saída Esperada

```
2024-01-15 14:32:10,123 - INFO - Iniciando sincronização Kamailio → Zabbix
2024-01-15 14:32:10,124 - INFO - Timestamp: 2024-01-15T14:32:10.123456
2024-01-15 14:32:10,234 - INFO - Conectado ao PostgreSQL em localhost:5432
2024-01-15 14:32:10,235 - INFO - Buscando ramais ativos no banco de dados...
2024-01-15 14:32:10,345 - INFO - Encontrados 25 ramais ativos no Kamailio
2024-01-15 14:32:10,346 - INFO - Processando dados dos ramais...

============================================================
RESUMO DO PROCESSAMENTO
============================================================
Ramais processados com sucesso: 23
Ramais rejeitados: 2
============================================================

2024-01-15 14:32:10,450 - INFO - Próxima etapa: Sincronizar 23 ramais com Zabbix
2024-01-15 14:32:10,451 - INFO - Desconectado do PostgreSQL
2024-01-15 14:32:10,452 - INFO - Sincronização finalizada
```

### Verificar Logs

```bash
# Ver últimas linhas do log
tail -f kamailio_zabbix_sync.log

# Filtrar por erros
grep ERROR kamailio_zabbix_sync.log

# Filtrar por ramal específico
grep "ramal 3000" kamailio_zabbix_sync.log
```

---

## Próximas Etapas

### ✅ ETAPA 1 - CONCLUÍDA
- [x] Conexão com PostgreSQL
- [x] Extração de IPv4 (Regex)
- [x] Parsing de User-Agent (marca/modelo)
- [x] Filtragem de softphones
- [x] Testes unitários
- [x] Logging estruturado

### ⏳ ETAPA 2 - INTEGRAÇÃO ZABBIX API

**Arquivo a criar:** `zabbix_api.py`

**Funcionalidades:**
```python
class ZabbixAPI:
    def __init__(self, config)
    def autenticar()              # Gerar token de sessão
    def obter_group_id()          # ID do grupo "Ramais UNIMED"
    def obter_template_id()       # ID do template "ICMP Ping"
    def host_existe()             # Verificar se host já existe
    def criar_host()              # Criar novo host
    def atualizar_interface()     # Atualizar IP do host
    def sincronizar_ramais()      # Orquestração
```

**Métodos Zabbix API a utilizar:**
- `user.login` - Autenticação
- `hostgroup.get` - Buscar grupos
- `template.get` - Buscar templates
- `host.get` - Listar hosts
- `host.create` - Criar host
- `host.update` - Atualizar host
- `hostinterface.get` - Obter interfaces de host

### ⏳ ETAPA 3 - VALIDAÇÕES E TRATAMENTOS

**Validações a adicionar:**
- [ ] Validação de IP privado vs público
- [ ] Validação de reachability (ping)
- [ ] Duplicação de ramal com IPs diferentes
- [ ] Ramal não registrado vs expirado

**Tratamento de erros:**
- [ ] Retry automático em caso de falha de conexão
- [ ] Rate limiting da API do Zabbix
- [ ] Backup de estado anterior

### ⏳ ETAPA 4 - SCHEDULING E MONITORING

**Recursos a implementar:**
- [ ] Scheduler (cron ou APScheduler)
- [ ] Métricas de sincronização
- [ ] Alertas em caso de falha
- [ ] Dashboard de status

---

## Troubleshooting

### Erro: "ModuleNotFoundError: No module named 'psycopg2'"

```bash
# Instale a dependência
pip install psycopg2-binary

# Ou reinstale todas
pip install -r requirements.txt
```

### Erro: "FATAL: Ident authentication failed for user 'kamailio'"

**Causa:** PostgreSQL rejeita autenticação.

**Solução:**
1. Verifique credenciais em `.env`
2. Verifique se user existe: `sudo -u postgres psql -c "\du"`
3. Teste conexão: `psql -h localhost -U kamailio -d kamailio`

### Erro: "Empty reply from server" (PostgreSQL)

**Causa:** PostgreSQL não está escutando em rede.

**Solução:**
1. Edite `/etc/postgresql/postgresql.conf`:
   ```
   listen_addresses = 'localhost'  # ou '*' para aceitar de qualquer lugar
   ```
2. Reinicie PostgreSQL: `sudo systemctl restart postgresql`

### Aviso: "Nenhum ramal encontrado"

**Possíveis causas:**
1. Tabela "location" está vazia (nenhum ramal registrado)
2. Todos os ramais expiraram (`expires < NOW()`)
3. Query está apontando para banco errado

**Verificação:**
```bash
# Conecte diretamente ao banco
psql -h localhost -U kamailio -d kamailio

# Execute a query
SELECT username, contact, expires FROM location WHERE expires > NOW();
```

### Softphone não está sendo detectado

**Verificação:**
1. Liste o User-Agent exato do aparelho:
   ```bash
   psql -h localhost -U kamailio -d kamailio
   SELECT DISTINCT user_agent FROM location;
   ```

2. Adicione o softphone à lista `SOFTPHONES` em `DataParser`:
   ```python
   SOFTPHONES = [
       'seu_novo_softphone',  # ← adicione aqui
       ...
   ]
   ```

3. Execute testes: `pytest test_data_parser.py -v`

---

## Exemplo de Dados Reais

### Saída do PostgreSQL

```
 username |           contact            | user_agent
----------+------------------------------+-------------------
 3000     | sip:3000@192.168.1.50:5060   | Intelbras TIP125 v1.0
 3001     | sip:3001@192.168.1.51:5060   | MicroSIP v2.0
 3002     | sip:3002@192.168.1.52:5060   | Yealink SIP-T31G
 3003     | sip:3003@192.168.1.53:5060   | Grandstream GXP1625
```

### Após Processamento

```
Ramal: 3000 | IP: 192.168.1.50 | Marca: INTELBRAS | Modelo: TIP125
✗ Ramal: 3001 | Rejeitado: Softphone detectado (MicroSIP v2.0)
Ramal: 3002 | IP: 192.168.1.52 | Marca: YEALINK | Modelo: T31G
Ramal: 3003 | IP: 192.168.1.53 | Marca: GRANDSTREAM | Modelo: GXP1625
```

### Hosts a Criar no Zabbix

```
Host Name (ID único)      | Visible Name (GUI)
--------------------------+---------------------------------------
ramal_3000                | UNIMED-INTELBRAS-TIP125-RAMAL 3000
ramal_3002                | UNIMED-YEALINK-T31G-RAMAL 3002
ramal_3003                | UNIMED-GRANDSTREAM-GXP1625-RAMAL 3003
```

---

## Contribuição e Melhorias

### Melhorias Futuras Sugeridas

1. **Performance:**
   - Batching de inserts/updates no Zabbix
   - Cache de IDs de grupos/templates

2. **Resiliência:**
   - Retry exponencial com backoff
   - Deadletter queue para falhas

3. **Observabilidade:**
   - Métricas Prometheus
   - Distributed tracing (OpenTelemetry)

4. **Segurança:**
   - Suporte a SSL/TLS para PostgreSQL e Zabbix
   - Secrets management (Vault)

---

## Contato e Suporte

Para dúvidas ou problemas, consulte:
- Logs: `kamailio_zabbix_sync.log`
- Testes: `pytest test_data_parser.py -v`
- Documentação PostgreSQL: https://www.postgresql.org/docs/
- Documentação Zabbix API: https://www.zabbix.com/documentation/current/en/api/

---

**Versão:** 1.0.0  
**Data:** 2024-01-15  
**Status:** Em Desenvolvimento (Etapa 1 Concluída)
