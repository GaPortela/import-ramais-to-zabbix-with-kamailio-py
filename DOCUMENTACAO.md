# Documentação técnica

## Arquitetura

O módulo `kamailio_zabbix_sync.py` segue o pipeline abaixo:

```text
KamailioDB → DataParser → RamalInfo → SyncPlanner → SyncPlan → ZabbixPlanExecutor
```

- `KamailioDB` lê somente registros ativos de `location` e pode aplicar `LIMIT` de desenvolvimento.
- `DataParser.normalizar_numero_ramal()` é o único ponto de normalização do ramal.
- `SyncPlanner` recebe ramais válidos e o catálogo de hosts, produzindo ações sem escrever no Zabbix.
- `ZabbixPlanExecutor` executa somente ações já planejadas.
- `ZabbixAPI` encapsula exclusivamente a comunicação por `zabbix-utils`.

## Modelo de host no Zabbix

| Campo | Exemplo | Uso |
|---|---|---|
| `host` | `ramal-3000` | Identificador técnico estável |
| tag `ramal` | `3000` | Identificador persistente e pesquisável |
| `name` | `ORGANIZACAO-YEALINK-T31G-RAMAL 3000` | Apresentação |
| `description` | `User-Agent: Yealink SIP-T31G` | Metadado atualizável |
| interface | `10.0.0.5` | Metadado atualizável |

Marca, modelo, IP, User-Agent, descrição, tags auxiliares e nome visual não participam da decisão de identidade. O plano encontra hosts pela tag `ramal` ou pelo hostname técnico compatível com o padrão `ramal-<número>`.

Esta versão é destinada à primeira implantação: não há migração ou reconhecimento de hosts legados.

## Planejamento e execução

O planejador classifica cada ramal em:

- `create`: não existe host com a mesma identidade;
- `update`: existe exatamente um host com a mesma identidade;
- `invalid`: ramal vazio/duplicado na origem ou mais de um host associado à identidade.

Erros de validação impedem a ação para aquele ramal e são contabilizados no resultado. O executor atualiza hostname técnico, nome visual, descrição, tag, interface, grupo e template configurado quando aplicável.

## Dry-run e relatório

`--dry-run` autentica e consulta os sistemas necessários para montar um plano real, mas não envia `host.create` nem `host.update`. O log apresenta o plano completo e a contagem de criações, atualizações e inconsistências.

Após a sincronização (ou simulação), o relatório final inclui registros lidos, válidos, ignorados, hosts encontrados, criados, atualizados, erros e duração total. O modo dry-run é indicado explicitamente.

## Configuração

| Variável | Padrão | Descrição |
|---|---|---|
| `KAMAILIO_DB_URL` | — | DSN PostgreSQL prioritário |
| `KAMAILIO_DB_HOST` | `localhost` | Host usado quando não há DSN |
| `KAMAILIO_DB_PORT` | `5432` | Porta PostgreSQL |
| `KAMAILIO_DB_NAME` | `kamailio` | Banco PostgreSQL |
| `KAMAILIO_DB_USER` | `kamailio` | Usuário PostgreSQL |
| `KAMAILIO_DB_PASSWORD` | — | Senha PostgreSQL |
| `ZABBIX_URL` | `http://zabbix-web/zabbix/api_jsonrpc.php` | Endpoint da API |
| `ZABBIX_API_TOKEN` | — | Token preferencial |
| `ZABBIX_USER` / `ZABBIX_PASSWORD` | — | Alternativa de autenticação |
| `ZABBIX_GROUP_NAME` | `Ramais` | Grupo de hosts |
| `ZABBIX_TEMPLATE_NAME` | `ICMP Ping` | Template associado |
| `HOST_PREFIX` | `ORGANIZACAO` | Prefixo do nome visual |
| `LIMIT` | desabilitado | Máximo de registros, somente para desenvolvimento |

## Testes

```bash
python -m pytest -q
```

Além dos testes de parsing, `test_stable_identity.py` cobre alterações de IP, fabricante, modelo, User-Agent e nome visual, idempotência, dry-run, planejamento e `LIMIT`. Não é necessário um Zabbix real para esses testes.

## Operação segura

1. Execute primeiro com `--dry-run`.
2. Corrija qualquer ação `invalid` antes da execução efetiva.
3. Remova `LIMIT` antes da execução de produção.
4. Use token de API com permissões mínimas de leitura/criação/atualização de hosts.
