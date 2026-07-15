# 🔄 Kamailio to Zabbix Synchronization Script

![Status](https://img.shields.io/badge/status-development-yellow) ![Python](https://img.shields.io/badge/python-3.8+-blue) ![License](https://img.shields.io/badge/license-MIT-green)

Automatiza a sincronização de ramais do **Kamailio** (servidor SIP) com **Zabbix** (monitoramento).

> 📌 **Este é um projeto modular em desenvolvimento. Etapa 1 (PostgreSQL + Data Parsing) está completa.**

---

## 🚀 Quick Start (5 minutos)

### 1️⃣ Pré-requisitos
- Python 3.8+
- PostgreSQL (Kamailio)
- pip (gerenciador de pacotes)

### 2️⃣ Instalação

```bash
# Clone o repositório
cd import-ramais-to-zabbix-with-kamailio-py

# Crie um ambiente virtual
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Instale dependências
pip install -r requirements.txt
```

### 3️⃣ Configuração

```bash
# Copie arquivo de exemplo
cp .env.example .env

# Edite com suas credenciais
nano .env
```

**Campos obrigatórios:**
```env
KAMAILIO_DB_HOST=seu-kamailio-host
KAMAILIO_DB_USER=kamailio
KAMAILIO_DB_PASSWORD=sua_senha

ZABBIX_URL=http://seu-zabbix.com/api_jsonrpc.php

# Opção 1: Token de API (recomendado - mais seguro)
ZABBIX_API_TOKEN=seu_token_aqui

# Opção 2: Usuário e Senha (legado - deixe vazio se usar token)
ZABBIX_USER=seu_usuario
ZABBIX_PASSWORD=sua_senha
```

### 4️⃣ Execute

```bash
# Executar script principal
python3 kamailio_zabbix_sync.py

# Rodar testes
pytest test_data_parser.py -v
```

---

## 📖 Documentação Completa

| Arquivo | Descrição |
|---------|-----------|
| **[DOCUMENTACAO.md](DOCUMENTACAO.md)** | 📚 Guia técnico completo (arquitetura, API, etc) |
| **[EXEMPLOS_PRATICOS.md](EXEMPLOS_PRATICOS.md)** | 💡 Exemplos SQL, dados de teste e cenários reais |
| **[ZABBIX_API_TOKEN.md](ZABBIX_API_TOKEN.md)** | 🔐 Guia: Geração e uso de tokens de API do Zabbix |
| **[kamailio_zabbix_sync.py](kamailio_zabbix_sync.py)** | ⚙️ Script principal (Etapa 1 + Etapa 2 em prog) |
| **[test_data_parser.py](test_data_parser.py)** | 🧪 36 testes unitários |
| **[requirements.txt](requirements.txt)** | 📦 Dependências Python |

---

## 🎯 Funcionalidades (Etapa 1)

### ✅ Implementado

- ✓ Conexão com PostgreSQL (Kamailio)
- ✓ Leitura de ramais ativos da tabela `location`
- ✓ **Extração de IPv4** com Regex validado
- ✓ **Parser de User-Agent** (marca + modelo)
- ✓ **Filtragem de softphones** (MicroSIP, Zoiper, etc)
- ✓ Logging estruturado
- ✓ 36 testes unitários com cobertura
- ✓ Tratamento de erros robusto
- ✓ Data model com `@dataclass`

**Exemplo de saída:**
```
Ramal: 3000 | IP: 192.168.1.50 | Marca: INTELBRAS | Modelo: TIP125
Ramal: 3001 | IP: 192.168.1.51 | Marca: YEALINK | Modelo: T31G
✗ Ramal: 3002 | Rejeitado: Softphone detectado (MicroSIP)
```

### ⏳ Etapa 2: Em Desenvolvimento

- ⚙️ **Classe `ZabbixAPI`** ✓ Implementada (suporte a token de API!)
- ⚙️ **Autenticação com Token** ✓ Implementada
- ⚙️ **Fallback Usuário/Senha** ✓ Implementada  
- ⚙️ Sincronização de hosts (criar, atualizar)
- ⚙️ **Etapa 3:** Validações avançadas e tratamento de edge cases
- ⚙️ **Etapa 4:** Scheduling automático e monitoramento

---

## 📊 Estrutura do Projeto

```
.
├── kamailio_zabbix_sync.py      # Script principal (com ZabbixAPI)
│   ├── DataParser               # Regex + parsing de dados
│   ├── KamailioDB               # Conexão PostgreSQL
│   ├── ZabbixAPI                # Integração com Zabbix (token/usuário)
│   └── RamalInfo                # Data model
├── test_data_parser.py           # 36 testes unitários
├── requirements.txt              # Dependências
├── .env.example                  # Config. de exemplo
├── DOCUMENTACAO.md               # Guia técnico completo
├── EXEMPLOS_PRATICOS.md          # Exemplos SQL e cenários
├── ZABBIX_API_TOKEN.md           # Guia: Tokens de API do Zabbix
└── README.md                     # Este arquivo
```

---

## 🧪 Testes

```bash
# Rodar todos os testes
pytest test_data_parser.py -v

# Teste específico
pytest test_data_parser.py::TestExtrairIPv4 -v

# Com cobertura
pytest test_data_parser.py --cov=kamailio_zabbix_sync --cov-report=html
```

**Resultado esperado:** 36 testes passando ✓

---

## 🔍 Exemplos de Uso

### Extrair IPv4 de URI SIP

```python
from kamailio_zabbix_sync import DataParser

ip = DataParser.extrair_ipv4("sip:3000@192.168.1.50:5060")
print(ip)  # → "192.168.1.50"
```

### Parser de Marca/Modelo

```python
marca, modelo = DataParser.extrair_marca_modelo("Intelbras TIP125 v1.0")
print(f"{marca}/{modelo}")  # → "INTELBRAS/TIP125"
```

### Conectar e Buscar Ramais

```python
from kamailio_zabbix_sync import KamailioDB, DB_CONFIG

db = KamailioDB(DB_CONFIG)
db.conectar()

ramais = db.buscar_ramais_ativos()
ramais_processados = db.processar_ramais(ramais)

for ramal in ramais_processados:
    print(ramal)  # Ramal: 3000 | IP: 192.168.1.50 | ...

db.desconectar()
```

---

## 📋 Checklist de Implementação

### Etapa 1: ✅ Concluída
- [x] Conexão PostgreSQL
- [x] Leitura de ramais ativos
- [x] Regex para IPv4
- [x] Parser de User-Agent
- [x] Filtro de softphones
- [x] Logging e tratamento de erros
- [x] Testes unitários (36 testes)

### Etapa 2: ⏳ Em Desenvolvimento
- [x] Classe `ZabbixAPI` (autenticação com token + fallback usuário/senha)
- [x] Autenticação com Token de API (recomendado)
- [x] Autenticação com Usuário/Senha (legado)
- [ ] Métodos `host.get`, `host.create`, `host.update`
- [ ] Buscar ID do grupo e template
- [ ] Criar hosts automaticamente
- [ ] Atualizar IPs de hosts existentes
- [ ] Testes de integração

### Etapa 3: 📋 Planejada
- [ ] Validação de IPs privados
- [ ] Tratamento de duplicatas
- [ ] Retry com backoff exponencial
- [ ] Testes e2e

### Etapa 4: 📋 Planejada
- [ ] APScheduler para scheduling
- [ ] Métricas Prometheus
- [ ] Dashboard de status
- [ ] Alertas

---

## 🔧 Troubleshooting

### Erro: "ModuleNotFoundError: No module named 'psycopg2'"

```bash
pip install -r requirements.txt
```

### Erro: "FATAL: Ident authentication failed"

Verifique credenciais no `.env`:
```bash
psql -h localhost -U kamailio -d kamailio
```

### Nenhum ramal encontrado?

```bash
# Conecte ao banco e verifique
psql -h localhost -U kamailio -d kamailio
SELECT COUNT(*) FROM location WHERE expires > NOW();
```

**Mais detalhes:** veja [DOCUMENTACAO.md](DOCUMENTACAO.md#troubleshooting)

---

## 📚 Referências

- **PostgreSQL:** https://www.postgresql.org/docs/
- **Kamailio:** https://www.kamailio.org/wiki/
- **Zabbix API:** https://www.zabbix.com/documentation/current/en/api/

---

## 🤝 Contribuição

Sugestões de melhorias:

1. **Performance:** Batching de inserts/updates
2. **Resiliência:** Retry com backoff exponencial
3. **Observabilidade:** Métricas Prometheus
4. **Segurança:** SSL/TLS, Secrets management

---

## 📝 Licença

MIT License - Veja LICENSE para detalhes

---

## ❓ FAQ

**P: Qual é o status do projeto?**  
R: Etapa 1 completa (PostgreSQL + Data Parsing). Próxima: integração Zabbix API.

**P: Como adicionar um novo softphone?**  
R: Edite a lista `SOFTPHONES` em `DataParser` e rodhe testes: `pytest test_data_parser.py`

**P: Como rodar em produção?**  
R: Use um scheduler (cron ou APScheduler). Etapa 4 está planejada.

**P: O script atualiza IPs automaticamente?**  
R: Sim, quando a Etapa 2 (Zabbix API) for implementada.

---

## 📞 Suporte

Consulte:
- Logs: `kamailio_zabbix_sync.log`
- Testes: `pytest test_data_parser.py -v`
- Documentação: [DOCUMENTACAO.md](DOCUMENTACAO.md)
- Exemplos: [EXEMPLOS_PRATICOS.md](EXEMPLOS_PRATICOS.md)

---

**Versão:** 0.0.1  
**Status:** Em Desenvolvimento (Etapa 1 ✅)  
**Última Atualização:** 14/07/2026
