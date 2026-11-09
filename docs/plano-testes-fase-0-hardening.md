# 🧪 Plano de Testes & Matriz QA: Hardening & Remediação da FASE 0

> **Documento:** `docs/plano-testes-fase-0-hardening.md`  
> **Referência Técnica:** [`docs/fase-0-remediacao-hardening.md`](file:///home/joao/projetos/the%20agency/docs/fase-0-remediacao-hardening.md)  
> **Status:** Aprovado e Pronto para Execução TDD  
> **Alinhamento:** Continuação direta dos cenários base da Fase 0 (TC-001 a TC-040) em [`docs/fase-0-motor-agentes.md`](file:///home/joao/projetos/the%20agency/docs/fase-0-motor-agentes.md)

---

## 1. Visão Geral & Escopo da Bateria de Testes

Este documento estabelece o plano formal de testes de controle de qualidade (QA) e engenharia de testes de segurança cobrindo todos os novos cenários introduzidos pelo endurecimento defensivo da **Fase 0 (Motor Standalone)**.

### Atores e Superfícies sob Teste:
1. **Cliente API / Gateway Local (`Client`):** Interage via REST (`POST /api/v1/agent/run`, `GET /api/v1/agent/run/{id}`) e SSE (`GET /api/v1/events/stream`).
2. **Autenticação & Middleware:** Filtra credenciais (`X-Engine-Key`), injeta `X-Request-ID` e aplica políticas de CORS.
3. **Fila RabbitMQ & Worker Pool:** Enfileira tarefas na fila `agency.tasks` e controla concorrência via `prefetch_count=5`.
4. **Sandbox Confinado (Docker & FS):** Executa comandos isolados com `--network=none` e gerencia operações atômicas no workspace.
5. **Loop Cognitivo do Agente (LLM Runner):** Executa raciocínio ReAct com circuit-breaker de loops, janela deslizante e telemetria de custos.
6. **Persistência SQLite WAL & Alembic:** Migrações versionadas, integridade transacional e rotina de retenção/vacuum.

---

## 2. Seção A: Matriz Completa de Cenários de Teste (TC-041 a TC-074)

| ID | Dimensão | Cenário / Objetivo do Teste | Pré-condição / Entrada | Resultado Esperado | Prioridade |
| :--- | :--- | :--- | :--- | :--- | :---: |
| **TC-041** | Happy Path | Autenticação com chave válida | Requisição com cabeçalho `X-Engine-Key: <CHAVE_VALIDA>` | Acesso autorizado com resposta normal (`200 OK` ou `202 Accepted`). | `P0` |
| **TC-042** | Security | Requisição desprovida de autenticação | Requisição aos endpoints `/api/v1/agent/run` ou `/events/stream` sem o cabeçalho `X-Engine-Key` | Bloqueio imediato com `HTTP 401 Unauthorized` e mensagem descritiva sem processamento interno. | `P0` |
| **TC-043** | Security | Requisição com chave inválida | Cabeçalho `X-Engine-Key: chave_falsa_123` | Bloqueio com `HTTP 401 Unauthorized`. | `P0` |
| **TC-044** | Security | Resistência a Timing Attacks na chave | Medição de tempo de resposta com chaves erradas de comprimentos variados | Uso de `secrets.compare_digest` garantindo validação em tempo constante. | `P1` |
| **TC-045** | Happy Path | Despacho com `workspace_slug` válido | `POST /api/v1/agent/run` com `workspace_slug: "alpha-client-01"` | Sucesso (`HTTP 202`), criando e amarrando canonicamente a pasta `<ROOT>/workspaces/clients/alpha-client-01`. | `P0` |
| **TC-046** | Security | Bloqueio de injeção de caminho absoluto | `POST /api/v1/agent/run` com `workspace_slug: "/"` ou `/etc` | `HTTP 422 Unprocessable Entity` rejeitando o formato de slug. | `P0` |
| **TC-047** | Security | Bloqueio de Path Traversal no Workspace | `POST /api/v1/agent/run` com `workspace_slug: "../../etc"` | `HTTP 422 Unprocessable Entity` pela regex `^[a-zA-Z0-9_\-]+$`. | `P0` |
| **TC-048** | Security | Bloqueio de Path Traversal em `agent_id` | `POST /api/v1/agent/run` com `agent_id: "../../../etc/passwd"` | `HTTP 422 Unprocessable Entity` pela validação de formato e existência em `config/agents/`. | `P0` |
| **TC-049** | Boundary | Valores limite no `workspace_slug` | Slugs de 1 caractere (`"a"`) e de 64 caracteres válidos | Ambos aceitos e normalizados com sucesso dentro de `<ROOT>/workspaces/clients/`. | `P1` |
| **TC-050** | Security | Isolamento de Rede no Docker Sandbox | Execução de comando bash `curl -I https://google.com` ou `ping` no container | Falha imediata de resolução ou conexão por ausência de interface de rede (`--network=none`). | `P0` |
| **TC-051** | Security | Supressão de Privilégios no Docker | Tentativa de escalação de privilégios via `su` ou escrita em `/root` | Falha imediata com permissão negada (`--cap-drop=ALL`, `--security-opt=no-new-privileges:true`). | `P0` |
| **TC-052** | Security | Sandbox Fail-Closed com Docker offline | Daemon Docker inacessível e flag `ALLOW_LOCAL_SUBPROCESS_DEV=false` | Operação aborta com `RuntimeError` de segurança; nenhum comando é disparado no host. | `P0` |
| **TC-053** | Edge Case | Fallback de desenvolvimento permitido | Docker offline, mas com `ALLOW_LOCAL_SUBPROCESS_DEV=true` no `.env` | Subprocesso local executa emitindo log explícito de advertência `WARNING: Local Subprocess Active`. | `P2` |
| **TC-054** | State / Lifecycle | Destruição de Containers Zumbis | Comando em timeout (`sleep 120` com teto de 5s) | Container nomeado `agency-{run_id}-{timestamp}` é sumariamente eliminado via `docker kill`/`rm`; zero containers órfãos no `docker ps`. | `P1` |
| **TC-055** | Happy Path | Enfileiramento de tarefa no RabbitMQ | `POST /api/v1/agent/run` com dados válidos | Tarefa persistida no RabbitMQ (exchange `agency.topic`, queue `agency.tasks`) com `status: queued`. | `P0` |
| **TC-056** | Concurrency | Consumo de tarefas com QoS 5 | 8 tarefas publicadas simultaneamente na fila do RabbitMQ | Exatamente 5 tarefas são consumidas simultaneamente (`prefetch_count=5`); as 3 restantes aguardam liberação de vaga. | `P0` |
| **TC-057** | Resilience | Queda e reconexão com RabbitMQ | Desconexão forçada do broker AMQP durante a execução | Motor ativa backoff exponencial de reconexão e retoma consumo sem perda de tarefas. | `P1` |
| **TC-058** | Boundary | Backpressure / Teto de Fila excedido | Fila atinge `MAX_QUEUE_CAPACITY=100` | Nova submissão recebe `HTTP 503 Service Unavailable (Capacity Exceeded)` sem consumir memória adicional. | `P1` |
| **TC-059** | State / Lifecycle | Proteção de Task contra Asyncio GC | Tarefa assíncrona longa executando em segundo plano | Múltiplas invocações manuais de `gc.collect()` não interrompem a execução da task retida em `_background_tasks`. | `P0` |
| **TC-060** | Boundary | Poda de Contexto / Janela Deslizante | Agente acumula histórico superior a 32k tokens | Histórico é compactado: System Prompt e Objetivo Inicial são mantidos; iterações intermediárias são resumidas. | `P1` |
| **TC-061** | Negative | Circuit Breaker de Repetição em Loops | LLM repete a mesma chamada de ferramenta com parâmetros idênticos recebendo o mesmo erro por 3 turnos | Execução é abortada com `status: failed` e mensagem amigável de interrupção por loop de falhas. | `P0` |
| **TC-062** | Security | Mascaramento de Chaves de API em Erros | Simulação de exceção contendo string de API Key (`AIza...`, `AQ....`, `sk-...`) | Chave é mascarada (`AQ...***...Nw`) em `AgentRun.error_message`, `AuditLog.content` e eventos SSE. | `P0` |
| **TC-063** | Happy Path | Precificação Dinâmica por Família de Modelos | Execução de agentes com `gemini-3.5-flash` e `gemini-2.5-pro` | Cálculo exato de custo em USD/BRL correspondente à tabela tarifária oficial de cada modelo. | `P1` |
| **TC-064** | Boundary | Teto de Timeout no Tool Registry | LLM solicita `timeout=99999` segundos | O valor é ajustado e executado com o teto de 180 segundos. | `P1` |
| **TC-065** | Boundary | Paginação e Teto em `list_directory` | Diretório contendo 1.000 arquivos | Retorno limitado aos primeiros 500 itens com indicador `has_more: true` e contagem total. | `P1` |
| **TC-066** | State / Concurrency | Escrita Atômica de Arquivos | Execução de `write_file` ou `patch_file` com simulação de crash antes do commit final | Gravação ocorre em arquivo `.tmp`; arquivo original permanece intacto até o `os.replace` bem-sucedido. | `P0` |
| **TC-067** | Boundary / Negative | Bloqueio de Arquivo Binário Gigante em `read_file` | Tentativa de leitura de arquivo com 3 MB (> 2 MB) ou contendo bytes nulos (`\x00`) | Leitura rejeitada com erro amigável sem estouro de memória RAM (OOM). | `P1` |
| **TC-068** | Concurrency | Isolamento de Transação em Mensageria | Execução da ferramenta `send_agent_message` | Operação insere registro sem invocar `session.commit()` prematuramente, mantendo a transação sob o runner. | `P1` |
| **TC-069** | State / Lifecycle | Migração Automática do Alembic no Boot | Inicialização da aplicação com banco SQLite vazio ou em versão desatualizada | Rotina executa `alembic upgrade head`, gerando tabela `alembic_version` sincronizada com o metadata. | `P0` |
| **TC-070** | State / Lifecycle | Rastreabilidade no Crash Recovery | Reinicialização com execuções deixadas em `RUNNING` | Tarefas são marcadas como `FAILED` e um registro formal é gravado na tabela `AuditLog`. | `P1` |
| **TC-071** | Security | Sanitização de Quebras de Linha no SSE | Emissão de evento SSE com `\r` ou `\n` no campo `event_type` | Quebras de linha são removidas, prevenindo injeção de framing no protocolo HTTP SSE. | `P1` |
| **TC-072** | Happy Path | Propagação de `X-Request-ID` | Requisição HTTP para a API | Resposta contém cabeçalho `X-Request-ID` (UUID v4) e o mesmo ID está indexado nos logs do Loguru. | `P1` |
| **TC-073** | Happy Path | Validação de Política de CORS | Requisição `OPTIONS` com `Origin: http://localhost:3000` | Resposta devolve cabeçalhos CORS correspondentes; origens não cadastradas são rejeitadas. | `P1` |
| **TC-074** | State / Lifecycle | Expulgo por Retenção e Incremental Vacuum | Banco SQLite com métricas e logs com mais de 30 dias | Rotina de manutenção deleta registros antigos e executa `PRAGMA incremental_vacuum`. | `P1` |

---

## 3. Seção B: Cenários Críticos em Formato BDD (Gherkin)

Abaixo estão as especificações BDD dos cenários de prioridade `P0` (Bloqueador) e `P1` (Crítico):

### BDD-01: Controle de Acesso e Autenticação (TC-041 & TC-042)
```gherkin
Funcionalidade: Autenticação Segura via Cabeçalho X-Engine-Key
  Como administrador da software house
  Quero que todas as chamadas aos endpoints de execução e streaming exijam uma chave de acesso
  Para impedir acessos não autorizados e abuso de inferência

  Cenário: [TC-041] Acesso bem-sucedido com chave autorizada
    Dado que a variável "ENGINE_API_KEY" está configurada como "chave-secreta-motor-2026"
    Quando uma requisição "POST /api/v1/agent/run" é enviada com o cabeçalho "X-Engine-Key: chave-secreta-motor-2026"
    Então a API deve autenticar a requisição com sucesso
    E deve retornar o status "202 Accepted" contendo o "run_id"

  Cenário: [TC-042] Bloqueio imediato de requisição sem cabeçalho de autenticação
    Dado que a variável "ENGINE_API_KEY" está configurada no servidor
    Quando uma requisição "POST /api/v1/agent/run" é enviada sem o cabeçalho "X-Engine-Key"
    Então o servidor deve interceptar a requisição antes do processamento
    E deve responder com o status "401 Unauthorized"
    E o corpo da resposta deve conter a mensagem "Missing or invalid API key"
```

---

### BDD-02: Confinamento Estrito de Workspace (TC-045, TC-046 & TC-047)
```gherkin
Funcionalidade: Confinamento Estrito e Imutável de Diretório de Workspace
  Como arquiteto de segurança da esteira
  Quero que os agentes operem estritamente dentro da raiz canônica de seus respectivos clientes
  Para que seja impossível ler ou alterar arquivos de sistema ou de outros workspaces

  Cenário: [TC-045] Despacho legítimo com slug de cliente
    Dado que o diretório base de workspaces é "<ROOT>/workspaces/clients"
    Quando o cliente solicita execução com "workspace_slug: projeto-cliente-a"
    Então a pasta "<ROOT>/workspaces/clients/projeto-cliente-a" deve ser resolvida canonicamente
    E o sandbox Docker deve montar exclusivamente essa pasta como diretório de trabalho

  Cenário: [TC-046] Bloqueio de injeção de barra ou caminho absoluto
    Dado que a API recebe uma solicitação de execução de agente
    Quando o payload contém "workspace_slug: /" ou "workspace_slug: /etc"
    Então o validador de schema Pydantic deve rejeitar a requisição
    E deve retornar o status "422 Unprocessable Entity"

  Cenário: [TC-047] Bloqueio de tentativa de Path Traversal
    Dado que a API recebe uma solicitação de execução de agente
    Quando o payload contém "workspace_slug: ../../home/joao"
    Então a validação por expressão regular "^[a-zA-Z0-9_\-]+$" deve falhar
    E a requisição deve ser bloqueada com status "422 Unprocessable Entity"
```

---

### BDD-03: Sandbox Docker Fail-Closed e Isolamento de Rede (TC-050 & TC-052)
```gherkin
Funcionalidade: Isolamento Rígido de Rede e Fail-Closed no Sandbox
  Como operador de infraestrutura
  Quero que comandos de terminal rodem sem interface de rede e recusem fallback inseguro no host
  Para prevenir vazamento de dados, ataques de SSRF e execução de código não confiavel na máquina física

  Cenário: [TC-050] Execução dentro do container sem acesso à rede externa
    Dado que um agente invoca a ferramenta "run_terminal_command" com "curl -I https://google.com"
    Quando o container Docker "node:20-slim" é inicializado
    Então a flag "--network=none" deve ser aplicada obrigatoriamente
    E a execução do comando deve falhar com erro de rede inalcançável
    E o status de saída (exit_code) retornado deve ser diferente de 0

  Cenário: [TC-052] Bloqueio de execução quando o Docker estiver offline (Fail-Closed)
    Dado que o serviço do Docker daemon está temporariamente inalcançável
    E a flag de ambiente "ALLOW_LOCAL_SUBPROCESS_DEV" está configurada como "false"
    Quando o motor tenta despachar um comando de terminal
    Então o sistema deve levantar uma exceção "RuntimeError" imediatamente
    E nenhum processo ou comando deve ser executado no shell da máquina host
```

---

### BDD-04: Fila Durável RabbitMQ e Backpressure de Workers (TC-055 & TC-056)
```gherkin
Funcionalidade: Enfileiramento Durável e Gestão de Concorrência via RabbitMQ
  Como gestor de operações
  Quero que tarefas excedentes aguardem em fila AMQP persistente com limite estrito de concorrência
  Para garantir resiliência contra picos de tráfego e evitar esgotamento de memória RAM

  Cenário: [TC-055] Enfileiramento e confirmação assíncrona
    Dado que o serviço RabbitMQ está ativo na porta 5672
    Quando uma requisição válida de execução chega em "POST /api/v1/agent/run"
    Então a tarefa deve ser serializada em JSON e publicada na fila "agency.tasks"
    E a resposta HTTP deve retornar imediatamente "202 Accepted" com "status: queued"

  Cenário: [TC-056] Consumo ordenado com limite de QoS prefetch 5
    Dado que 8 tarefas distintas foram enfileiradas na fila "agency.tasks"
    Quando o "WorkerPool" inicia o consumo com "prefetch_count=5"
    Então exatamente 5 tarefas devem iniciar o processamento simultâneo
    E as 3 tarefas restantes devem permanecer na fila aguardando liberação de slots
    Quando uma das 5 tarefas é finalizada com sucesso
    Então a 6ª tarefa da fila deve transicionar imediatamente para processamento ativo
```

---

### BDD-05: Janela Deslizante de Contexto e Circuit Breaker de Loops (TC-060 & TC-061)
```gherkin
Funcionalidade: Poda de Histórico e Interrupção Automática de Loops de Falha
  Como gestor financeiro da esteira
  Quero que o agente comprima históricos extensos e interrompa ciclos repetitivos de erro
  Para prevenir estouro de janela de contexto e consumo astronômico e inútil de tokens

  Cenário: [TC-060] Compressão inteligente de histórico longo
    Dado que uma execução longa acumulou mais de 32.000 tokens no histórico de mensagens
    Quando o turno ReAct se prepara para a próxima chamada da LLM
    Então o motor deve preservar intactos o System Prompt e o Objetivo Inicial da tarefa
    E deve compactar ou resumir as iterações intermediárias antigas
    E a contagem de tokens despachada deve ser reduzida para o teto seguro configurado

  Cenário: [TC-061] Interrupção por repetição de falha idêntica (Circuit Breaker)
    Dado que o agente invoca a ferramenta "patch_file" com argumentos específicos
    E a ferramenta devolve o erro "Target block not found"
    Quando o modelo insiste e repete exatamente a mesma chamada de ferramenta com os mesmos parâmetros por 3 iterações seguidas
    Então o circuito deve desarmar interrompendo o ciclo ReAct imediatamente
    E o status da execução no banco deve ser atualizado para "FAILED"
    E a mensagem de encerramento deve sinalizar detecção de loop repetitivo de falha
```

---

### BDD-06: Escritas Atômicas e Integridade do Filesystem (TC-066 & TC-067)
```gherkin
Funcionalidade: Escrita Atômica e Proteção contra Arquivos Danificados ou Gigantes
  Como engenheiro de software
  Quero que modificações em arquivos usem substituição atômica e bloqueiem binários gigantes
  Para impedir corrupção de código em crashes e evitar negação de serviço por falta de memória

  Cenário: [TC-066] Substituição atômica via arquivo temporário
    Dado que um arquivo de código "src/main.py" já existe no workspace do cliente
    Quando o agente aciona a ferramenta "write_file" com novo código
    Então o conteúdo deve ser gravado primeiro em um arquivo temporário com sufixo ".tmp"
    E a substituição do arquivo de destino deve ocorrer via "os.replace"
    E em nenhum momento o arquivo original deve permanecer zerado ou corrompido

  Cenário: [TC-067] Bloqueio de arquivos maiores que 2 MB na leitura
    Dado que um arquivo "dump.raw" possui 3 MB de tamanho no workspace
    Quando o agente tenta acionar a ferramenta "read_file" apontando para "dump.raw"
    Então o sistema deve verificar o tamanho do arquivo antes de carregar o conteúdo na memória
    E deve abortar a leitura retornando erro explicativo de superação do teto de 2 MB
    E o consumo de memória RAM do motor deve permanecer estável
```

---

### BDD-07: Versionamento de Banco e Retenção no SQLite WAL (TC-069 & TC-074)
```gherkin
Funcionalidade: Gestão Automatizada de Migrações e Retenção de Dados
  Como mantenedor do banco de dados
  Quero que o Alembic execute migrações no boot e que dados antigos sejam limpos periodicamente
  Para assegurar integridade estrutural e prevenir fragmentação de disco

  Cenário: [TC-069] Auto-upgrade do Alembic na inicialização do servidor
    Dado que um banco de dados novo está sendo inicializado
    Quando o lifespan do FastAPI inicia o ciclo de vida do motor
    Então o comando "alembic upgrade head" deve ser executado programaticamente
    E a tabela "alembic_version" deve ser registrada com a versão "001_initial_schema"
    E todas as tabelas ("agent_runs", "audit_logs", "token_metrics") devem ser criadas com sucesso

  Cenário: [TC-074] Purga de métricas antigas e execução de Incremental Vacuum
    Dado que a base SQLite contém registros de métricas de token com mais de 30 dias
    E o parâmetro "RETENTION_DAYS" está configurado como 30
    Quando o job de manutenção periódica é disparado
    Então as linhas anteriores à janela de 30 dias devem ser deletadas
    E o comando "PRAGMA incremental_vacuum" deve ser executado no banco
    E o arquivo "pipeline.db" deve recuperar espaço livre em disco
```

---

## 4. Seção C: Rastreabilidade de Cobertura das 24 Vulnerabilidades da Auditoria

| ID Auditoria | Vulnerabilidade Auditada | Cenários de Teste Cobrindo o Achado |
| :--- | :--- | :--- |
| **SEC-001** | Arbitrary Workspace Path Injection | `TC-045`, `TC-046`, `TC-047`, `TC-049`, `BDD-02` |
| **SEC-002** | Subprocess Sandbox Fallback RCE | `TC-052`, `TC-053`, `BDD-03` |
| **SEC-003** | Missing Authentication on Endpoints | `TC-041`, `TC-042`, `TC-043`, `TC-044`, `BDD-01` |
| **SEC-004** | Missing Docker Network Isolation & Caps | `TC-050`, `TC-051`, `BDD-03` |
| **SEC-005** | Traversal em `agent_id` | `TC-048` |
| **SEC-006** | Unbounded Command Timeout | `TC-064` |
| **SEC-007** | Potential API Key Leakage in Logs/SSE | `TC-062` |
| **SEC-008** | In-Memory Queue Exhaustion DoS | `TC-055`, `TC-056`, `TC-057`, `TC-058`, `BDD-04` |
| **SEC-010** | Missing CORS Policy & Trusted Hosts | `TC-073` |
| **SEC-011** | Asyncio GC Dropping Background Tasks | `TC-059` |
| **SEC-012** | Context Window Explosion & Loops | `TC-060`, `TC-061`, `BDD-05` |
| **SEC-013** | Unbounded `list_directory` Traversal | `TC-065` |
| **SEC-014** | Non-Atomic File Writes | `TC-066`, `BDD-06` |
| **SEC-015** | Large/Binary File Ingestion in `read_file` | `TC-067`, `BDD-06` |
| **SEC-016** | Hardcoded Pricing Discrepancy | `TC-063` |
| **SEC-017** | Premature `session.commit()` in Tools | `TC-068` |
| **SEC-018** | Zombie Docker Containers | `TC-054` |
| **SEC-019** | Missing Alembic Migrations | `TC-069`, `BDD-07` |
| **SEC-020** | Incomplete Crash Recovery Audit | `TC-070` |
| **SEC-022** | SSE Framing Newline Injection | `TC-071` |
| **SEC-023** | Missing Distributed Correlation ID | `TC-072` |
| **SEC-024** | Lack of SQLite Retention & Vacuum | `TC-074`, `BDD-07` |

---

## 5. Diretrizes de Execução dos Testes TDD

1. **Abordagem RED-GREEN-REFACTOR:**
   - Para cada cenário, criar o teste automatizado em `services/engine/tests/` (ex: `test_hardening_auth.py`, `test_hardening_sandbox.py`, `test_hardening_queue.py`).
   - Confirmar que o teste falha (RED).
   - Implementar a alteração mínima no código-fonte para passar (GREEN).
   - Refatorar mantendo a conformidade com as regras de immutabilidade e modularidade do `AGENTS.md`.
2. **Threshold de Cobertura:**
   - A execução de `uv run pytest --cov=src` deve manter cobertura total superior a **80%**.
3. **Isolamento de Testes:**
   - Testes do RabbitMQ devem utilizar mock de conexão ou container descartável de integração via fixture do pytest (`pytest-mock` / `testcontainers` / `respx`).
