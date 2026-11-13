# Inventário de Casos de Borda e Regressões

## Concorrência e Conflitos
- Gravações simultâneas no SQLite WAL sob busy_timeout de 5000ms.
- Retentativas de webhooks bancários idempotentes por chave txid.
- Timeouts em conexões remotas tratadas com backoff exponencial.

## Sanitização e Validação de Entrada
- Bloqueio imediato de Path Traversal em manipulação de workspaces.
- Isolamento total de contêineres Docker efêmeros sem interface de rede.
