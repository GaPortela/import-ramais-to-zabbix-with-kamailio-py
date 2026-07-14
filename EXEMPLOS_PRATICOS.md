# Exemplos Práticos - Kamailio to Zabbix Sync
## Guia com SQL, Dados de Teste e Cenários Reais

---

## 📌 Índice
1. [Queries PostgreSQL](#queries-postgresql)
2. [Dados de Teste](#dados-de-teste)
3. [Exemplos de Parsing](#exemplos-de-parsing)
4. [Cenários Reais](#cenários-reais)
5. [Debug e Troubleshooting](#debug-e-troubleshooting)

---

## Queries PostgreSQL

### 1. Conectar ao Banco do Kamailio

```bash
# Conexão remota
psql -h seu-kamailio.com -p 5432 -U kamailio -d kamailio

# Conexão local
sudo -u kamailio psql kamailio
```

### 2. Explorar Tabela de Location

```sql
-- Listar todas as colunas da tabela location
SELECT * FROM location LIMIT 5;

-- Ver estrutura da tabela
\d location
```

**Saída esperada:**
```
 id  | username |           contact            |  user_agent  | expires | ...
-----+----------+------------------------------+--------------+----------
 1   | 3000     | sip:3000@192.168.1.50:5060   | Intelbras... | 2024-01-16 10:30:00
 2   | 3001     | sip:3001@192.168.1.51:5060   | MicroSIP v2  | 2024-01-16 10:45:00
```

### 3. Query Principal - Ramais Ativos

```sql
-- Ramais válidos (não expirados)
SELECT 
    username,
    contact,
    received,
    user_agent,
    expires,
    ruid
FROM location
WHERE expires > NOW()
ORDER BY username;
```

### 4. Queries de Diagnóstico

```sql
-- Contar ramais ativos
SELECT COUNT(*) as total_ramais FROM location WHERE expires > NOW();

-- Listar softphones (para validar filtro)
SELECT DISTINCT user_agent FROM location 
WHERE expires > NOW() 
AND (
    user_agent ILIKE '%microsip%'
    OR user_agent ILIKE '%zoiper%'
    OR user_agent ILIKE '%linphone%'
    OR user_agent ILIKE '%softphone%'
)
ORDER BY user_agent;

-- Ramais por marca
SELECT 
    CASE 
        WHEN user_agent ILIKE '%intelbras%' THEN 'INTELBRAS'
        WHEN user_agent ILIKE '%yealink%' THEN 'YEALINK'
        WHEN user_agent ILIKE '%grandstream%' THEN 'GRANDSTREAM'
        ELSE 'OUTROS'
    END as marca,
    COUNT(*) as quantidade
FROM location
WHERE expires > NOW()
GROUP BY marca
ORDER BY quantidade DESC;

-- Listar ramais sem IP válido
SELECT username, contact, received FROM location
WHERE expires > NOW()
AND contact !~ '\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}'
AND received !~ '\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}';

-- Ramais prestes a expirar (próximos 5 minutos)
SELECT username, user_agent, expires FROM location
WHERE expires > NOW()
AND expires < NOW() + INTERVAL '5 minutes'
ORDER BY expires;

-- Histórico de um ramal específico
SELECT * FROM location WHERE username = '3000' ORDER BY expires DESC;
```

### 5. Inserir Dados de Teste

```sql
-- Limpar dados de teste
DELETE FROM location WHERE username IN ('9900', '9901', '9902', '9903', '9904');

-- Inserir ramais de teste
INSERT INTO location (username, contact, received, user_agent, expires)
VALUES
    ('9900', 'sip:9900@192.168.1.100:5060', 'sip:9900@192.168.1.100:5060', 'Intelbras TIP125 v1.0', NOW() + INTERVAL '1 hour'),
    ('9901', 'sip:9901@192.168.1.101:5060', 'sip:9901@192.168.1.101:5060', 'MicroSIP v2.0', NOW() + INTERVAL '1 hour'),
    ('9902', 'sip:9902@192.168.1.102:5060', 'sip:9902@192.168.1.102:5060', 'Yealink SIP-T31G', NOW() + INTERVAL '1 hour'),
    ('9903', 'sip:9903@192.168.1.103:5060', 'sip:9903@192.168.1.103:5060', 'Grandstream GXP1625', NOW() + INTERVAL '1 hour'),
    ('9904', 'sip:9904@hostname.local:5060', 'sip:9904@hostname.local:5060', 'Unknown Device', NOW() + INTERVAL '1 hour');

-- Verificar inserção
SELECT * FROM location WHERE username LIKE '99%' ORDER BY username;
```

---

## Dados de Teste

### Dataset Completo para Validação

```json
{
  "ramais_teste": [
    {
      "descricao": "Intelbras TIP125 - Válido",
      "username": "3000",
      "contact": "sip:3000@192.168.1.50:5060",
      "user_agent": "Intelbras TIP125 v1.0",
      "esperado": {
        "aceito": true,
        "ip": "192.168.1.50",
        "marca": "INTELBRAS",
        "modelo": "TIP125"
      }
    },
    {
      "descricao": "Yealink T31G - Válido",
      "username": "3001",
      "contact": "sip:3001@10.0.0.5:5060",
      "user_agent": "Yealink SIP-T31G",
      "esperado": {
        "aceito": true,
        "ip": "10.0.0.5",
        "marca": "YEALINK",
        "modelo": "T31G"
      }
    },
    {
      "descricao": "MicroSIP - Softphone (Rejeitado)",
      "username": "3002",
      "contact": "sip:3002@192.168.1.60:5060",
      "user_agent": "MicroSIP v2.0 (Windows)",
      "esperado": {
        "aceito": false,
        "motivo": "Softphone detectado"
      }
    },
    {
      "descricao": "Grandstream GXP1625 - Válido",
      "username": "3003",
      "contact": "sip:3003@172.16.0.100:5060",
      "user_agent": "Grandstream GXP1625",
      "esperado": {
        "aceito": true,
        "ip": "172.16.0.100",
        "marca": "GRANDSTREAM",
        "modelo": "GXP1625"
      }
    },
    {
      "descricao": "Sem IP válido - Rejeitado",
      "username": "3004",
      "contact": "sip:3004@telefone.local",
      "received": "sip:3004@invalid",
      "user_agent": "Intelbras TIP125",
      "esperado": {
        "aceito": false,
        "motivo": "IP não encontrado"
      }
    },
    {
      "descricao": "Cisco CP-7961G - Válido",
      "username": "3005",
      "contact": "sip:3005@192.168.50.75:5060",
      "user_agent": "Cisco IP Phone CP-7961G",
      "esperado": {
        "aceito": true,
        "ip": "192.168.50.75",
        "marca": "CISCO",
        "modelo": "7961G"
      }
    },
    {
      "descricao": "Polycom VVX 300 - Válido",
      "username": "3006",
      "contact": "sip:3006@192.168.100.20:5060",
      "user_agent": "Polycom VVX 300",
      "esperado": {
        "aceito": true,
        "ip": "192.168.100.20",
        "marca": "POLYCOM",
        "modelo": "VVX300"
      }
    },
    {
      "descricao": "Linphone (Softphone - Rejeitado)",
      "username": "3007",
      "contact": "sip:3007@192.168.1.70:5060",
      "user_agent": "Linphone 4.2",
      "esperado": {
        "aceito": false,
        "motivo": "Softphone detectado"
      }
    },
    {
      "descricao": "Marca Genérica - IP válido",
      "username": "3008",
      "contact": "sip:3008@192.168.1.80:5060",
      "user_agent": "Unknown Device v1.0",
      "esperado": {
        "aceito": true,
        "ip": "192.168.1.80",
        "marca": "GENERICO",
        "modelo": "GENERICO"
      }
    },
    {
      "descricao": "Avaya IP Office - Válido",
      "username": "3009",
      "contact": "sip:3009@192.168.200.50:5060",
      "user_agent": "Avaya IP Office",
      "esperado": {
        "aceito": true,
        "ip": "192.168.200.50",
        "marca": "AVAYA",
        "modelo": "GENERICO"
      }
    }
  ]
}
```

---

## Exemplos de Parsing

### Python - Testando Manualmente

```python
from kamailio_zabbix_sync import DataParser

# ====== EXEMPLO 1: Extração de IP ======
print("=== EXTRAÇÃO DE IP ===")
uris = [
    "sip:3000@192.168.1.50:5060",
    "sip:3001@10.0.0.5",
    "sip:3002@hostname.local",
    "sip:3003@172.16.254.1:5060"
]

for uri in uris:
    ip = DataParser.extrair_ipv4(uri)
    print(f"{uri:35} → {ip}")

# Saída esperada:
# sip:3000@192.168.1.50:5060         → 192.168.1.50
# sip:3001@10.0.0.5                  → 10.0.0.5
# sip:3002@hostname.local            → None
# sip:3003@172.16.254.1:5060         → 172.16.254.1

# ====== EXEMPLO 2: Detecção de Softphone ======
print("\n=== DETECÇÃO DE SOFTPHONE ===")
user_agents = [
    "Intelbras TIP125 v1.0",
    "MicroSIP v2.0",
    "Yealink SIP-T31G",
    "Linphone 4.2",
    "Zoiper 5.0 (Android)",
    "Unknown Softphone v1.0"
]

for ua in user_agents:
    eh_soft = DataParser.eh_softphone(ua)
    status = "❌ SOFTPHONE (REJEITADO)" if eh_soft else "✓ TELEFONE (ACEITO)"
    print(f"{ua:30} → {status}")

# Saída esperada:
# Intelbras TIP125 v1.0            → ✓ TELEFONE (ACEITO)
# MicroSIP v2.0                    → ❌ SOFTPHONE (REJEITADO)
# ...

# ====== EXEMPLO 3: Parsing de Marca/Modelo ======
print("\n=== PARSING DE MARCA/MODELO ===")
user_agents_parsing = [
    "Intelbras TIP125 v1.0",
    "intelbras tip125 v1.0",  # minúsculas
    "Yealink SIP-T31G",
    "GRANDSTREAM GXP1625",
    "Cisco IP Phone CP-7961G",
    "Polycom VVX 300",
    "Unknown Device",
    ""
]

for ua in user_agents_parsing:
    marca, modelo = DataParser.extrair_marca_modelo(ua)
    print(f"{ua:35} → {marca:15} | {modelo}")

# Saída esperada:
# Intelbras TIP125 v1.0            → INTELBRAS     | TIP125
# intelbras tip125 v1.0            → INTELBRAS     | TIP125
# Yealink SIP-T31G                 → YEALINK       | T31G
# ...
```

### Teste com Dados do Banco

```python
# Script para testar com dados reais do banco
from kamailio_zabbix_sync import KamailioDB, DataParser

db = KamailioDB({
    'host': 'localhost',
    'port': 5432,
    'database': 'kamailio',
    'user': 'kamailio',
    'password': 'senha'
})

if db.conectar():
    ramais = db.buscar_ramais_ativos()
    
    print(f"Total de ramais encontrados: {len(ramais)}\n")
    
    for ramal in ramais[:5]:  # Primeiros 5
        username = ramal['username']
        contact = ramal['contact']
        user_agent = ramal['user_agent']
        
        ip = DataParser.extrair_ipv4(contact)
        is_softphone = DataParser.eh_softphone(user_agent)
        marca, modelo = DataParser.extrair_marca_modelo(user_agent)
        
        print(f"Ramal: {username}")
        print(f"  Contact: {contact}")
        print(f"  IP: {ip}")
        print(f"  User-Agent: {user_agent}")
        print(f"  Marca/Modelo: {marca}/{modelo}")
        print(f"  Softphone: {'SIM ❌' if is_softphone else 'NÃO ✓'}")
        print()
    
    db.desconectar()
```

---

## Cenários Reais

### Cenário 1: Ambiente com 50 Ramais Intelbras TIP125

```sql
-- Simular inserção
DO $$
DECLARE
    i INTEGER := 3100;
BEGIN
    FOR i IN 3100..3150 LOOP
        INSERT INTO location (username, contact, user_agent, expires)
        VALUES (
            i::text,
            'sip:' || i::text || '@192.168.' || (i/256)::text || '.' || (i%256)::text || ':5060',
            'Intelbras TIP125 v1.0',
            NOW() + INTERVAL '8 hours'
        );
    END LOOP;
END $$;

-- Verificar
SELECT COUNT(*) FROM location WHERE username::integer >= 3100;
-- Resultado: 51 ramais
```

**Processamento esperado:**
- ✓ 50 ramais aceitos
- ✗ 0 ramais rejeitados
- Nomes no Zabbix: `UNIMED-INTELBRAS-TIP125-RAMAL 3100`, etc

---

### Cenário 2: Ambiente Heterogêneo (Mix de Marcas)

```sql
-- Ambiente com múltiplos fabricantes
DELETE FROM location WHERE username::integer >= 4000 AND username::integer < 5000;

INSERT INTO location (username, contact, user_agent, expires) VALUES
('4001', 'sip:4001@192.168.1.1:5060', 'Intelbras TIP125 v1.0', NOW() + INTERVAL '8 hours'),
('4002', 'sip:4002@192.168.1.2:5060', 'Yealink SIP-T31G', NOW() + INTERVAL '8 hours'),
('4003', 'sip:4003@192.168.1.3:5060', 'Grandstream GXP1625', NOW() + INTERVAL '8 hours'),
('4004', 'sip:4004@192.168.1.4:5060', 'Cisco IP Phone CP-7961G', NOW() + INTERVAL '8 hours'),
('4005', 'sip:4005@192.168.1.5:5060', 'Polycom VVX 300', NOW() + INTERVAL '8 hours'),
('4006', 'sip:4006@192.168.1.6:5060', 'MicroSIP v2.0', NOW() + INTERVAL '8 hours'),
('4007', 'sip:4007@192.168.1.7:5060', 'Linphone 4.2', NOW() + INTERVAL '8 hours');
```

**Processamento esperado:**
- ✓ 5 ramais aceitos (4001-4005)
- ✗ 2 ramais rejeitados (4006, 4007)

**Output no Zabbix:**
```
UNIMED-INTELBRAS-TIP125-RAMAL 4001
UNIMED-YEALINK-T31G-RAMAL 4002
UNIMED-GRANDSTREAM-GXP1625-RAMAL 4003
UNIMED-CISCO-7961G-RAMAL 4004
UNIMED-POLYCOM-VVX300-RAMAL 4005
```

---

### Cenário 3: Problemas de Conectividade

```sql
-- Ramais com problemas de IP
INSERT INTO location (username, contact, received, user_agent, expires) VALUES
('5001', 'sip:5001@hostname.local', 'sip:5001@hostname.local', 'Intelbras TIP125', NOW() + INTERVAL '8 hours'),
('5002', 'sip:5002@999.999.999.999:5060', 'sip:5002@999.999.999.999:5060', 'Yealink SIP-T31G', NOW() + INTERVAL '8 hours'),
('5003', '', 'sip:5003@192.168.1.100:5060', 'Grandstream GXP1625', NOW() + INTERVAL '8 hours');
```

**Processamento esperado:**
- ✗ 5001: IP não encontrado (hostname inválido)
- ✗ 5002: IP não encontrado (inválido)
- ✓ 5003: OK (usa campo `received`)

---

## Debug e Troubleshooting

### Aumentar Verbosidade do Log

```python
# Em kamailio_zabbix_sync.py, altere:
logging.basicConfig(
    level=logging.DEBUG,  # ← Mudou de INFO para DEBUG
    ...
)
```

### Executar com Debug

```bash
python3 -c "
from kamailio_zabbix_sync import DataParser

# Teste específico
ua = 'Intelbras TIP125 v1.0'
marca, modelo = DataParser.extrair_marca_modelo(ua)
print(f'User-Agent: {ua}')
print(f'Marca: {marca}')
print(f'Modelo: {modelo}')
"
```

### Profiling de Performance

```python
import cProfile
from kamailio_zabbix_sync import main

cProfile.run('main()')
```

### Verificar Padrão Regex

```python
import re
from kamailio_zabbix_sync import DataParser

# Teste o regex diretamente
test_uris = [
    "sip:3000@192.168.1.50:5060",
    "sip:3000@invalid.com",
    "sip:3000@256.256.256.256"  # IP inválido
]

for uri in test_uris:
    matches = re.findall(DataParser.IPV4_REGEX, uri)
    print(f"{uri:40} → {matches}")
```

---

## Validação Manual do Script

### Passo a Passo para Testar

```bash
# 1. Ativar ambiente
source venv/bin/activate

# 2. Inserir dados de teste (opcional)
psql -h localhost -U kamailio kamailio < setup_test_data.sql

# 3. Executar script
python3 kamailio_zabbix_sync.py

# 4. Verificar logs
tail -50 kamailio_zabbix_sync.log

# 5. Rodar testes unitários
pytest test_data_parser.py -v

# 6. Verificar cobertura
pytest test_data_parser.py --cov=kamailio_zabbix_sync --cov-report=html

# 7. Abrir relatório (no navegador)
# coverage report
```

### Checklist de Validação

- [ ] PostgreSQL está rodando
- [ ] Credenciais estão corretas no `.env`
- [ ] Tabela `location` tem dados
- [ ] `python3 -m pytest test_data_parser.py` passa
- [ ] `python3 kamailio_zabbix_sync.py` executa sem erros
- [ ] Log mostra ramais aceitos e rejeitados
- [ ] Nomes dos hosts seguem padrão `ramal_XXXX`
- [ ] Nomes visíveis seguem padrão `UNIMED-MARCA-MODELO-RAMAL XXXX`

---

## Recursos Adicionais

### Documentação Oficial
- PostgreSQL: https://www.postgresql.org/docs/
- Kamailio: https://www.kamailio.org/wiki/
- Zabbix API: https://www.zabbix.com/documentation/current/en/api/

### Ferramentas Úteis
```bash
# Inspecionar banco PostgreSQL
pgAdmin: https://www.pgadmin.org/

# Cliente PostgreSQL GUI
DBeaver: https://dbeaver.io/

# Teste de regex online
RegexTester: https://regex101.com/
```

