# Exemplos práticos

## Inspeção e simulação antes da implantação

```bash
# Examina dados brutos/normalizados sem acessar o Zabbix
python kamailio_zabbix_sync.py --inspecao

# Monta e mostra o plano real; não cria nem altera hosts
python kamailio_zabbix_sync.py --dry-run
```

Para testar somente uma pequena amostra:

```bash
LIMIT=10 python kamailio_zabbix_sync.py --dry-run
```

Remova `LIMIT` na execução de produção.

## Resultado do planejamento

Para ramais `3000` e `3001` sem hosts existentes, o plano é:

```text
CREATE: ramal 3000
CREATE: ramal 3001
DRY-RUN: criaria=2 atualizaria=0 inconsistentes=0
```

Um host novo para `3000` terá:

```text
host técnico: ramal-3000
tag:          ramal=3000
nome visual:  ORGANIZACAO-INTELBRAS-TIP125-RAMAL 3000
descrição:    User-Agent: Intelbras TIP125 v1.0
```

## Atualização sem troca de identidade

Se o ramal `3000` mudar de Intelbras/TIP125 no IP `10.0.0.10` para Yealink/T31G no IP `10.0.9.9`, a próxima execução produz `UPDATE: ramal 3000`. O mesmo host técnico `ramal-3000` recebe o novo IP, nome visual e descrição; nenhum host adicional é criado.

## Duplicidade na origem

Entradas como `c312-3000` e `3000` são ambas normalizadas para `3000`. O plano marca a segunda ocorrência como inválida e não a envia ao executor. Isso impede a criação de dois hosts para a mesma identidade lógica.

## Consulta PostgreSQL usada pela aplicação

```sql
SELECT username, contact, received, user_agent, expires
FROM location
WHERE expires > NOW()
ORDER BY username;
```

Com `LIMIT=10`, a aplicação acrescenta `LIMIT 10` à consulta parametrizada.

## Testes locais

```bash
python -m pytest -q
```

Os testes não exigem servidor PostgreSQL ou Zabbix para validar a regra de identidade, o plano e o executor.
