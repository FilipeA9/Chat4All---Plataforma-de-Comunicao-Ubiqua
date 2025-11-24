# Database Migrations

Este diretório contém scripts SQL para migração do banco de dados.

## Ordem de Execução

Execute os scripts na seguinte ordem:

1. **001_initial_schema.sql** - Cria todas as tabelas, índices e tipos ENUM
2. **002_seed_users.sql** - Insere 5 usuários de teste

## Como Executar

### Usando psql

```bash
# Conectar ao banco de dados
psql -U postgres -d chat4all

# Executar migration
\i migrations/001_initial_schema.sql
\i migrations/002_seed_users.sql
```

### Usando Docker

```bash
# Copiar scripts para container
docker cp migrations/001_initial_schema.sql postgres_container:/tmp/
docker cp migrations/002_seed_users.sql postgres_container:/tmp/

# Executar dentro do container
docker exec -it postgres_container psql -U postgres -d chat4all -f /tmp/001_initial_schema.sql
docker exec -it postgres_container psql -U postgres -d chat4all -f /tmp/002_seed_users.sql
```

### Usando Python (método alternativo)

Os scripts `db/database.py` contêm as funções `init_db()` e `seed_db()` que executam as mesmas operações usando SQLAlchemy ORM.

## Credenciais dos Usuários de Teste

Todos os usuários de teste têm a senha: **password123**

| Username | Email | Full Name |
|----------|-------|-----------|
| user1 | user1@chat4all.com | User One |
| user2 | user2@chat4all.com | User Two |
| user3 | user3@chat4all.com | User Three |
| user4 | user4@chat4all.com | User Four |
| user5 | user5@chat4all.com | User Five |

## Notas

- **Produção**: Não use estes scripts diretamente em produção. Use ferramentas como Alembic para gerenciar migrações.
- **Senha**: O hash bcrypt foi gerado com 12 rounds para a senha "password123"
- **Desenvolvimento**: Estes scripts são ideais para setup rápido de ambiente de desenvolvimento/teste
