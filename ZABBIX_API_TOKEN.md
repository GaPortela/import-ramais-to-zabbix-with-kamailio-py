# Autenticação no Zabbix com API Token

## Visão Geral

O script agora suporta dois métodos de autenticação no Zabbix:

1. **Token de API** (Recomendado) - Mais seguro e moderno
2. **Usuário e Senha** (Legado) - Compatibilidade com versões antigas

## Como Gerar um Token de API no Zabbix

### Pré-requisitos
- Acesso administrativo ao Zabbix
- Zabbix 5.4+

### Passos

1. **Acessar o Zabbix**
   - Abra a interface web do Zabbix
   - Faça login com um usuário administrador

2. **Navegar para Tokens de API**
   - Menu: `Administration` → `API Tokens`

3. **Criar um Novo Token**
   - Clique em `Create API Token`
   - Preencha os campos:
     - **Name**: `Kamailio Sync Token` (ou um nome descritivo)
     - **User**: Selecione um usuário com permissões apropriadas
     - **Expires at**: (Opcional) Data de expiração

4. **Gerar o Token**
   - Clique em `Create`
   - **IMPORTANTE**: Copie o token gerado (aparece apenas uma vez!)

## Configuração do Arquivo `.env`

### Opção 1: Usando Token de API (Recomendado)

```env
ZABBIX_URL=http://seu-zabbix.com/api_jsonrpc.php
ZABBIX_API_TOKEN=seu_token_aqui
# Deixe ZABBIX_USER e ZABBIX_PASSWORD em branco
ZABBIX_USER=
ZABBIX_PASSWORD=
ZABBIX_GROUP_NAME=Ramais UNIMED
ZABBIX_TEMPLATE_NAME=ICMP Ping
```

### Opção 2: Usando Usuário e Senha (Legado)

```env
ZABBIX_URL=http://seu-zabbix.com/api_jsonrpc.php
# Deixe ZABBIX_API_TOKEN em branco
ZABBIX_API_TOKEN=
ZABBIX_USER=seu_usuario_zabbix
ZABBIX_PASSWORD=sua_senha_zabbix
ZABBIX_GROUP_NAME=Ramais UNIMED
ZABBIX_TEMPLATE_NAME=ICMP Ping
```

## Comportamento da Autenticação

O script tenta os métodos na seguinte ordem:

1. **Token de API** - Se `ZABBIX_API_TOKEN` estiver preenchido
2. **Usuário/Senha** - Se `ZABBIX_USER` e `ZABBIX_PASSWORD` estiverem preenchidos
3. **Erro** - Se nenhum método estiver disponível

## Permissões Necessárias

O usuário (ou token) deve ter permissões para:

- **Host**: Create, Update, Get
- **Template**: Get
- **Host Group**: Get
- **Interface**: Create, Update

### Exemplo de Role para Token

Se criar uma role personalizada:

```
Permissions:
├── API
│   └── Allow API calls
├── Host
│   ├── Create
│   ├── Update
│   └── Get
├── Template
│   └── Get
└── Host Group
    └── Get
```

## Segurança

### ✅ Boas Práticas

- Use **Token de API** em vez de usuário/senha
- Tokens com **data de expiração** curta (30-90 dias)
- Armazene o `.env` em `.gitignore`
- Use **roles com permissões mínimas** necessárias
- Regenere tokens periodicamente

### ❌ Evite

- Colocar credenciais em arquivos versionados
- Usar tokens com expiração nunca ou muito longa
- Compartilhar tokens ou credenciais
- Usar usuários admin para o script

## Testando a Autenticação

Execute o script para verificar a conexão:

```bash
python3 kamailio_zabbix_sync.py
```

Verifique os logs:

```bash
tail -f kamailio_zabbix_sync.log
```

Procure por mensagens de autenticação:

```
2024-XX-XX XX:XX:XX - INFO - Autenticando no Zabbix com token de API
2024-XX-XX XX:XX:XX - INFO - Token de API validado com sucesso. Zabbix versão: 6.0.0
```

## Regenerar Token

Se o token for comprometido:

1. Acesse `Administration` → `API Tokens`
2. Encontre o token na lista
3. Clique em `Delete`
4. Gere um novo token seguindo o passo 3 acima
5. Atualize o `.env` com o novo token

## Referências

- [Documentação oficial - Zabbix API Tokens](https://www.zabbix.com/documentation/current/en/manual/web_interface/administration/api_tokens)
- [Documentação oficial - Zabbix API Methods](https://www.zabbix.com/documentation/current/en/manual/api)

## Troubleshooting

### Erro: "Token de API inválido"
- Verifique se o token foi copiado corretamente
- Confirme se o token não expirou
- Verifique se o usuário associado tem permissões

### Erro: "Falha na autenticação"
- Se usando usuário/senha: verifique credenciais
- Verifique se a URL do Zabbix está correta
- Confirme conectividade com o servidor Zabbix

### Erro: "Grupo não encontrado"
- Verifique o nome exato do grupo em `Administration` → `Host groups`
- Confirme permissões do token para acessar grupos

### Erro: "Template não encontrado"
- Verifique o nome exato do template em `Monitoring` → `Templates`
- Confirme permissões do token para acessar templates
