# Kamailio → Zabbix: sincronização de ramais

Sincroniza ramais SIP ativos do PostgreSQL/Kamailio com hosts do Zabbix usando `zabbix-utils`.

## Identidade estável

O número normalizado do ramal é a única identidade lógica. Para o ramal `3000`, o host criado contém:

- Hostname técnico: `ramal-3000`
- Tag persistente: `ramal=3000`
- Nome visual: `<HOST_PREFIX>-<MARCA>-<MODELO>-RAMAL 3000`

IP, marca, modelo, User-Agent e nome visual são atributos atualizáveis. Eles não criam outro host. A tag foi escolhida por ser metadado estruturado, pesquisável pela API e suportado nativamente pelo Zabbix; descrição e macros não são usadas como chave de identidade.

## Instalação

```bash
python -m venv venv
# Linux/macOS
source venv/bin/activate
# Windows PowerShell
# .\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Configure o ambiente em `.env`:

```env
KAMAILIO_DB_URL=postgresql://kamailio:senha@localhost:5432/kamailio

ZABBIX_URL=http://zabbix.example/zabbix/api_jsonrpc.php
ZABBIX_API_TOKEN=seu_token
ZABBIX_GROUP_NAME=Ramais
ZABBIX_TEMPLATE_NAME=ICMP Ping
HOST_PREFIX=ORGANIZACAO
```

Também são aceitos `ZABBIX_USER` e `ZABBIX_PASSWORD` quando não for utilizado token. Veja [ZABBIX_API_TOKEN.md](ZABBIX_API_TOKEN.md).

## Execução

```bash
# Simulação: consulta PostgreSQL e Zabbix, mas não grava no Zabbix
python kamailio_zabbix_sync.py --dry-run

# Sincronização efetiva
python kamailio_zabbix_sync.py

# Somente inspeção dos dados vindos do Kamailio
python kamailio_zabbix_sync.py --inspecao
```

Para limitar a consulta durante desenvolvimento, use `LIMIT`; ele é desabilitado por padrão:

```bash
LIMIT=10 python kamailio_zabbix_sync.py --dry-run
```

No Windows PowerShell:

```powershell
$env:LIMIT = '10'
python kamailio_zabbix_sync.py --dry-run
```

## Fluxo de sincronização

```text
PostgreSQL → parsing/normalização → validação → plano → dry-run ou executor Zabbix → relatório
```

`SyncPlanner` decide `create`, `update` ou `invalid` antes de alterações. `ZabbixPlanExecutor` apenas executa esse plano. O dry-run imprime todas as ações e as contagens; a execução final informa lidos, válidos, ignorados, hosts encontrados, criados, atualizados, erros e duração.

## Testes

```bash
python -m pytest -q
```

Os testes abrangem parsing, configurações, normalização, plano, executor, dry-run, `LIMIT` e atualização idempotente de atributos.

## Documentação

- [Documentação técnica](DOCUMENTACAO.md)
- [Exemplos práticos](EXEMPLOS_PRATICOS.md)
- [Token de API do Zabbix](ZABBIX_API_TOKEN.md)
