# Chat4All - Cliente de Chat em Linha de Comando

Cliente de chat em tempo real que consome a API do Chat4All para simular comunicação entre usuários.

## Requisitos

- Python 3.8+
- API Chat4All rodando (via Docker)

## Instalação

```bash
# Navegue até a pasta do cliente
cd client

# Instale as dependências
pip install -r requirements.txt
```

## Uso

### Iniciando o Chat

Abra dois terminais para simular dois usuários diferentes:

**Terminal 1 - Usuário 1:**
```bash
python chat_client.py --user user1 --password password123
```

**Terminal 2 - Usuário 2:**
```bash
python chat_client.py --user user2 --password password123
```

### Comandos Disponíveis

| Comando | Descrição |
|---------|-----------|
| `/conversas` | Lista suas conversas |
| `/nova <user_id>` | Cria conversa privada com outro usuário |
| `/entrar <conv_id>` | Entra em uma conversa existente |
| `/historico` | Mostra histórico de mensagens |
| `/usuarios` | Lista usuários disponíveis |
| `/ajuda` | Mostra ajuda |
| `/sair` | Encerra o cliente |

Para enviar uma mensagem, basta digitar o texto e pressionar Enter (estando dentro de uma conversa).

### Usuários Disponíveis (Seed)

O sistema vem com 3 usuários pré-cadastrados:

| Username | Senha |
|----------|-------|
| user1 | password123 |
| user2 | password123 |
| user3 | password123 |

**Nota:** Os IDs dos usuários são atribuídos dinamicamente pelo sistema. Ao fazer login, o cliente mostrará seu ID atual.

## Exemplo de Uso

```
============================================================
      Chat4All - Cliente de Chat em Tempo Real
============================================================

ℹ Autenticando como 'user1'...
✓ Autenticado com sucesso como 'user1' (ID: 411)!
✓ Conectado ao WebSocket para mensagens em tempo real!

Comandos disponíveis:
  /conversas           - Lista suas conversas
  /nova <user_id>      - Cria conversa privada com outro usuário
  /entrar <conv_id>    - Entra em uma conversa existente
  /historico           - Mostra histórico de mensagens
  /usuarios            - Mostra seu ID e informações
  /ajuda               - Mostra esta ajuda
  /sair                - Encerra o cliente

>>> /nova 412
✓ Conversa criada com ID: 106
✓ Você entrou na conversa 106

>>> Olá, como vai?
[14:30:15] Você: Olá, como vai?

>>> 
[14:30:45] user2: Tudo bem! E você?
```

## Configuração Avançada

### URL da API

Por padrão, o cliente conecta em `http://localhost:8000`. Para usar outra URL:

```bash
python chat_client.py --user user1 --password password123 --url http://outra-url:8000
```

### Debug

Para ver logs detalhados, defina a variável de ambiente:

```bash
# Windows
set DEBUG=1
python chat_client.py --user user1 --password password123

# Linux/Mac
DEBUG=1 python chat_client.py --user user1 --password password123
```

## Arquitetura

O cliente utiliza:

- **requests**: Chamadas REST para autenticação, criação de conversas e envio de mensagens
- **websockets**: Conexão WebSocket para recebimento de mensagens em tempo real
- **colorama**: Cores no terminal para melhor visualização
- **asyncio**: Execução assíncrona para permitir envio e recebimento simultâneos

## Troubleshooting

### Erro de conexão

Se receber "Não foi possível conectar à API", verifique se:
1. O Docker está rodando: `docker ps`
2. A API está acessível: `curl http://localhost:8000/health`

### WebSocket não conecta

Verifique se:
1. O token de autenticação é válido
2. Não há firewall bloqueando a porta

### Mensagens não aparecem

Certifique-se de:
1. Estar inscrito na conversa (`/entrar <id>`)
2. O outro usuário está enviando para a mesma conversa
