# 🛡️ Especificação de Remediação & Hardening: FASE 0 — O Motor de Agentes

> **Documento:** `docs/fase-0-remediacao-hardening.md`  
> **Status:** Aprovado e Homologado pelo Chefe (João) após Sessão de Deliberação Arquitetural  
> **Escopo:** Endurecimento Defensivo, Resiliência Operacional e Infraestrutura do Motor (`services/engine`)

---

## 1. Visão Geral & Contexto

Após a conclusão da implementação inicial e aprovação dos 42 testes da Fase 0 (com 83% de cobertura), uma varredura estática e modelagem de ameaças (documentadas em `audits/REPORT.md` e `audits/FINDINGS-DETAIL.md`) identificou **24 pontos de vulnerabilidade e fragilidade arquitetural**.

Este documento consolida:
1. **As Decisões Estratégicas soberanas aprovadas por João** em sessão interativa de governança.
2. **A Matriz Completa de Remediação da Fase 0 (16 Vulnerabilidades do Motor + Broker RabbitMQ)**.
3. **Os Critérios de Aceitação TDD (Test-Driven Development)** com meta contínua de 80%+ de cobertura de código.

---

## 2. Decisões Estratégicas Aprovadas por João (Chefe)

| # | Área de Decisão | Decisão Soberana Homologada | Impacto Arquitetural na Fase 0 |
| :-: | :--- | :--- | :--- |
| **D1** | **Autenticação da API** (`SEC-003`) | **Header estático `X-Engine-Key`** configurado no `.env` e validado via FastAPI Dependency (`Security(get_api_key)`). | Bloqueia requisições não autorizadas aos endpoints `/api/v1/agent/run`, `/api/v1/agent/run/{id}` e `/api/v1/events/stream`. |
| **D2** | **Fila e Message Broker** (`SEC-008`) | **RabbitMQ (`rabbitmq:3-management`) gerenciado via `docker-compose.yml`** na raiz do projeto. | Substitui o acúmulo de corrotinas na memória por fila AMQP persistente (`agency.tasks`) com QoS prefetch=5 no worker pool. |
| **D3** | **CORS & Origens Confiáveis** (`SEC-010`) | **Origens de desenvolvimento pré-configuradas** (`localhost:3000`, `localhost:5173`, `127.0.0.1:3000`) parametrizáveis via `CORS_ORIGINS` no `.env`. | Permite integração futura com o Cockpit Web sem expor a API para origens não controladas. |
| **D4** | **Migrações de Banco** (`SEC-019`) | **Alembic configurado formalmente com migração inicial (`001_initial.py`)** e rotina de auto-upgrade no boot de desenvolvimento. | Garante versionamento do banco SQLite mantendo a conveniência de inicialização automática. |
| **D5** | **Retenção & Manutenção** (`SEC-024`) | **Retenção padrão de 30 dias** configurável via `.env` (`RETENTION_DAYS=30`) com rotina de limpeza e `PRAGMA auto_vacuum = INCREMENTAL`. | Previne inchaço do arquivo `pipeline.db` e fragmentação de páginas do SQLite. |

---

## 3. Infraestrutura RabbitMQ (`docker-compose.yml`)

Para suportar o enfileiramento e controle de concorrência com resiliência a reinicializações:

```yaml
version: "3.8"

services:
  rabbitmq:
    image: rabbitmq:3-management-alpine
    container_name: agency-rabbitmq
    restart: unless-stopped
    ports:
      - "5672:5672"   # Protocolo AMQP
      - "15672:15672" # Painel Web de Gerenciamento (Management UI)
    environment:
      RABBITMQ_DEFAULT_USER: ${RABBITMQ_USER:-agency}
      RABBITMQ_DEFAULT_PASS: ${RABBITMQ_PASS:-agency123}
    volumes:
      - rabbitmq_data:/var/lib/rabbitmq
    healthcheck:
      test: ["CMD", "rabbitmq-diagnostics", "check_running"]
      interval: 10s
      timeout: 5s
      retries: 5

volumes:
  rabbitmq_data:
```

---

## 4. Matriz Completa de Remediações Técnicas da Fase 0

### 4.1 Confinamento e Segurança do Sandbox

#### SEC-001: Confinamento Estrito do Workspace
* **Componente:** `src/api/router.py`, `src/tools/implementations.py`
* **Vulnerabilidade:** O parâmetro `workspace_dir` aceitava caminhos arbitrários como `/etc` ou `/`.
* **Remediação:**
  1. Alterar o schema da requisição para aceitar `workspace_slug: str = Field(default="default", pattern=r"^[a-zA-Z0-9_\-]+$")`.
  2. Forçar a raiz canônica em `<PROJECT_ROOT>/workspaces/clients/<workspace_slug>`.
  3. Rejeitar qualquer tentativa de navegação relativa (`..`) ou caminhos absolutos.

#### SEC-002: Sandbox Fail-Closed (Sem Fallback Inseguro no Host)
* **Componente:** `src/runner/sandbox.py`
* **Vulnerabilidade:** Na ausência do daemon Docker, o sistema executava comandos diretamente no shell do host (RCE com privilégios do usuário).
* **Remediação:**
  1. Eliminar o fallback silencioso para `SubprocessSandboxDriver`.
  2. Se o Docker estiver inalcançável, levantar `RuntimeError("Docker daemon is unreachable. Terminal execution blocked (Fail-Closed).")`.
  3. Permitir subprocesso somente se `ALLOW_LOCAL_SUBPROCESS_DEV=true` estiver explicitamente declarado no `.env`.

#### SEC-004: Isolamento Rígido de Rede e Privilégios no Docker
* **Componente:** `src/runner/sandbox.py`
* **Vulnerabilidade:** O container executava sem `--network=none`, permitindo potencial SSRF e exfiltração de dados.
* **Remediação:**
  1. Adicionar obrigatoriamente `--network=none` ao comando do container.
  2. Adicionar `--cap-drop=ALL` e `--security-opt=no-new-privileges:true`.
  3. Adicionar `--read-only` montando `--tmpfs /tmp:rw,noexec,nosuid,size=64m`.

#### SEC-018: Destruição Determinística de Containers Zumbis
* **Componente:** `src/runner/sandbox.py`
* **Vulnerabilidade:** Containers abortados por timeout podiam permanecer rodando em segundo plano.
* **Remediação:**
  1. Atribuir nome determinístico único: `--name f"agency-{run_id[:8]}-{int(time.time())}"`.
  2. No bloco de `TimeoutExpired` e em blocos de exceção, executar `docker kill <container_name>` e `docker rm -f <container_name>`.

---

### 4.2 Controle de Acesso, Fila e Integridade do Loop Assíncrono

#### SEC-003: Autenticação via `X-Engine-Key`
* **Componente:** `src/api/router.py`, `src/config.py`
* **Vulnerabilidade:** Endpoints `/api/v1/agent/run` e `/api/v1/events/stream` expostos publicamente sem autenticação.
* **Remediação:**
  1. Criar dependência FastAPI `verify_api_key` que extrai o cabeçalho `X-Engine-Key`.
  2. Comparar com `settings.ENGINE_API_KEY` usando `secrets.compare_digest` para evitar timing attacks.
  3. Rejeitar requisições inválidas ou sem cabeçalho com `HTTP 401 Unauthorized`.

#### SEC-008: Fila de Tarefas Persistente via RabbitMQ
* **Componente:** `src/services/pool.py`, `src/services/queue.py`, `src/api/router.py`
* **Vulnerabilidade:** Sobrecarga de requisições acumulava corrotinas na memória RAM sem teto rígido (DoS).
* **Remediação:**
  1. Criar cliente assíncrono RabbitMQ (`aio-pika`).
  2. O endpoint `/api/v1/agent/run` publica a mensagem na exchange/fila `agency.tasks` e retorna `HTTP 202 Accepted` com `status: queued`.
  3. O `WorkerPool` atua como consumer com `prefetch_count=MAX_CONCURRENT_AGENTS` (padrão 5).
  4. Se a fila do RabbitMQ exceder a capacidade máxima (`MAX_QUEUE_CAPACITY=100`), retornar `HTTP 503 Service Unavailable`.

#### SEC-011: Prevenção de Descarte de Tarefas por GC no Asyncio
* **Componente:** `src/api/router.py`
* **Vulnerabilidade:** `asyncio.create_task` sem referência forte era vulnerável a cancelamento imprevisível pelo coletor de lixo do Python.
* **Remediação:**
  1. Criar conjunto `_background_tasks: set[asyncio.Task] = set()`.
  2. Adicionar task ao conjunto antes de executar: `_background_tasks.add(task)`.
  3. Remover task ao concluir via `task.add_done_callback(_background_tasks.discard)`.

#### SEC-023: Middleware de Request ID & Rastreamento Distribuído
* **Componente:** `src/main.py`, `src/api/router.py`
* **Vulnerabilidade:** Ausência de identificador único de requisição para correlacionar logs de API, fila e eventos SSE.
* **Remediação:**
  1. Adicionar middleware que captura ou gera `X-Request-ID` (UUID v4).
  2. Injetar o `request_id` no contexto do Loguru e nos cabeçalhos da resposta HTTP.

---

### 4.3 Inteligência do Agente (LLM) e Telemetria

#### SEC-005: Regex Slug Mandatório em `agent_id`
* **Componente:** `src/api/router.py`, `src/runner/agent_runner.py`
* **Vulnerabilidade:** Parâmetro `agent_id` aceitava sequências de traversal (`../../`) no carregador de perfis YAML.
* **Remediação:**
  1. Adicionar validação Pydantic com regex rígida `^[a-z0-9_\-]+$`.
  2. Validar que o caminho canônico do perfil reside estritamente sob `config/agents/`.

#### SEC-007: Sanitização de Segredos e API Keys em Erros
* **Componente:** `src/runner/agent_runner.py`, `src/api/sse.py`
* **Vulnerabilidade:** Exceções do LiteLLM podiam vazar a chave de API em mensagens persistidas no SQLite ou emitidas no SSE.
* **Remediação:**
  1. Criar função utilitária `mask_sensitive_data(text: str) -> str` aplicando regex sobre padrões de chaves (`AIza...`, `AQ....`, `sk-...`).
  2. Aplicar a máscara antes de salvar em `AgentRun.error_message`, `AuditLog.content` e eventos SSE.

#### SEC-012: Janela Deslizante de Contexto e Proteção contra Loops Infinitos
* **Componente:** `src/runner/agent_runner.py`
* **Vulnerabilidade:** O histórico acumulado de mensagens podia explodir o limite de tokens ou entrar em loop infinito de chamadas idênticas.
* **Remediação:**
  1. Poda de contexto: se o histórico exceder 32k tokens, preservar o System Prompt e o Objetivo Inicial, compactando as iterações intermediárias mais antigas.
  2. Circuit-breaker de repetição: se o modelo emitir exatamente a mesma chamada de ferramenta com os mesmos argumentos e receber o mesmo erro por 3 turnos consecutivos, abortar com `status: failed` e mensagem explicativa.

#### SEC-016: Tabela Dinâmica de Precificação de Modelos
* **Componente:** `src/runner/agent_runner.py`
* **Vulnerabilidade:** Os custos eram calculados com base estática no Gemini Flash, subdimensionando gastos ao usar Gemini Pro ou Claude.
* **Remediação:**
  1. Estruturar tabela de preços por milhão de tokens (input, cached, output) para:
     * `gemini-2.5-flash` / `gemini-3.5-flash`
     * `gemini-2.5-pro`
     * `claude-3-5-sonnet`
     * `groq/llama-3.3-70b`
  2. Recuperar a precificação exata baseada no `model_name` da execução.

---

### 4.4 Sistema de Arquivos e Ferramentas

#### SEC-006: Teto Rígido no Timeout de Comandos de Terminal
* **Componente:** `src/tools/registry.py`
* **Vulnerabilidade:** O modelo podia requisitar timeouts abusivos (ex: 99.999 segundos), travando slots de execução.
* **Remediação:**
  1. Forçar limite superior: `timeout = max(5, min(int(timeout), 180))`.

#### SEC-013: Paginação e Teto de Itens em `list_directory`
* **Componente:** `src/tools/implementations.py`
* **Vulnerabilidade:** Listar diretórios gigantes como `node_modules` gerava esgotamento de memória (OOM).
* **Remediação:**
  1. Limitar a listagem a no máximo 500 itens.
  2. Adicionar profundidade máxima de busca (default `max_depth=3`).

#### SEC-014: Escrita Atômica de Arquivos
* **Componente:** `src/tools/implementations.py`
* **Vulnerabilidade:** Falhas de processo no meio da escrita de `write_file` ou `patch_file` deixavam arquivos corrompidos ou zerados.
* **Remediação:**
  1. Gravar os dados em arquivo temporário com prefixo `.tmp` no mesmo diretório de destino.
  2. Concluir a escrita utilizando `os.replace(temp_path, final_path)`.

#### SEC-015: Proteção contra Leitura de Arquivos Binários Gigantes
* **Componente:** `src/tools/implementations.py`
* **Vulnerabilidade:** `read_file` tentava carregar arquivos gigantes ou binários na memória sem validação de tamanho.
* **Remediação:**
  1. Validar tamanho máximo de arquivo (teto de 2 MB via `os.path.getsize`).
  2. Inspecionar os primeiros 512 bytes procurando caracteres nulos (`\x00`) para rejeitar arquivos binários com mensagem amigável.

#### SEC-017: Isolamento de Transação em `send_agent_message`
* **Componente:** `src/tools/implementations.py`
* **Vulnerabilidade:** A ferramenta realizava `session.commit()` prematuro, interferindo na transação ativa gerenciada pelo runner.
* **Remediação:**
  1. Remover `await session.commit()` de dentro da ferramenta; o ciclo de commit pertence estritamente ao `AgentRunner`.

---

### 4.5 Persistência, Migrações e Manutenção

#### SEC-019: Ambiente de Migração Alembic
* **Componente:** `services/engine/alembic/`
* **Remediação:**
  1. Configurar `alembic.ini` e `alembic/env.py` conectados ao `SQLModel.metadata`.
  2. Gerar a primeira migração canônica `versions/001_initial_schema.py`.
  3. No lifespan do FastAPI, executar automaticamente `command.upgrade(alembic_cfg, "head")`.

#### SEC-020: Auditoria Completa de Recuperação no Boot
* **Componente:** `src/services/recovery.py`
* **Remediação:**
  1. Ao marcar execuções interrompidas como `FAILED`, registrar evento formal na tabela `AuditLog`.

#### SEC-022: Sanitização de Framing no SSE
* **Componente:** `src/api/sse.py`
* **Remediação:**
  1. Sanitizar quebras de linha (`\r`, `\n`) no nome do evento (`event_type`) antes de escrever no stream SSE.

#### SEC-024: Retenção e Manutenção de Espaço no SQLite
* **Componente:** `src/models/database.py`, `src/services/maintenance.py`
* **Remediação:**
  1. Ativar `PRAGMA auto_vacuum = INCREMENTAL` na criação da base de dados.
  2. Implementar rotina de purga que deleta métricas de token e logs com mais de `RETENTION_DAYS` (padrão 30 dias).
  3. Executar `PRAGMA incremental_vacuum` após a purga.

---

## 5. Matriz de Testes & Critérios de Aceitação TDD

Para cada remediação, um teste automatizado correspondente deve ser adicionado à suíte:

| ID | Teste Automatizado | Critério de Aceitação |
| :--- | :--- | :--- |
| **TC-SEC-001** | `test_workspace_confinement_blocks_arbitrary_paths` | `POST /api/v1/agent/run` com `workspace_dir: "/"` retorna `HTTP 422`. |
| **TC-SEC-002** | `test_sandbox_fail_closed_when_docker_down` | Com Docker inalcançável e `ALLOW_LOCAL_SUBPROCESS_DEV=false`, o comando levanta erro e não toca o host. |
| **TC-SEC-003** | `test_auth_header_protection` | Requisições sem `X-Engine-Key` correto retornam `HTTP 401 Unauthorized`. |
| **TC-SEC-004** | `test_docker_network_none_isolation` | Tentativa de `curl` dentro do sandbox Docker falha por ausência de interface de rede. |
| **TC-SEC-005** | `test_agent_id_path_traversal_blocked` | `agent_id: "../../../etc/passwd"` retorna `HTTP 422`. |
| **TC-SEC-006** | `test_timeout_clamped_to_180s` | Timeout solicitado de `99999` é reduzido e executado com 180s. |
| **TC-SEC-007** | `test_api_key_masked_in_errors_and_logs` | Exceção contendo chave de API tem o segredo mascarado no banco e SSE. |
| **TC-SEC-008** | `test_rabbitmq_task_enqueue_and_worker_consumption` | Tarefas enviadas entram na fila do RabbitMQ e são consumidas pelos 5 workers com resiliência. |
| **TC-SEC-010** | `test_cors_headers_applied` | Requisição `OPTIONS` com origem permitida retorna cabeçalhos CORS corretos. |
| **TC-SEC-011** | `test_asyncio_task_not_garbage_collected` | Tarefa em execução não é cancelada mesmo sob chamadas forçadas de `gc.collect()`. |
| **TC-SEC-012** | `test_sliding_window_and_loop_circuit_breaker` | Loop com 3 falhas idênticas é interrompido com erro de repetição detectado. |
| **TC-SEC-013** | `test_list_directory_pagination_limit` | Diretório com 1.000 arquivos retorna no máximo 500 itens com aviso de truncamento. |
| **TC-SEC-014** | `test_atomic_file_write_replaces_cleanly` | Escrita de arquivo grava via temporário sem deixar arquivos em estado intermediário. |
| **TC-SEC-015** | `test_read_file_blocks_large_binary_files` | Arquivo maior que 2 MB ou com bytes nulos é rejeitado com erro amigável. |
| **TC-SEC-016** | `test_model_pricing_lookup_accuracy` | Execução simulando modelo Pro calcula custos condizentes com a tabela Pro. |
| **TC-SEC-017** | `test_send_agent_message_does_not_prematurely_commit` | Chamada da ferramenta não efetua commit isolado na sessão compartilhada. |
| **TC-SEC-018** | `test_deterministic_container_naming_and_cleanup` | Container é nomeado deterministicamente e destruído após timeout. |
| **TC-SEC-019** | `test_alembic_upgrade_head_on_boot` | Migração do Alembic roda com sucesso criando a tabela `alembic_version`. |
| **TC-SEC-020** | `test_recovery_writes_audit_log` | Tarefa recuperada no boot gera registro de `AuditLog`. |
| **TC-SEC-022** | `test_sse_newline_injection_sanitized` | Evento SSE com quebras de linha no tipo é sanitizado sem quebrar o framing HTTP. |
| **TC-SEC-023** | `test_request_id_middleware_propagation` | Requisições HTTP geram e devolvem o cabeçalho `X-Request-ID`. |
| **TC-SEC-024** | `test_retention_purge_and_vacuum` | Registros antigos são expurgados respeitando a janela configurada no `.env`. |

---

## 6. Definições de Fronteira: O Que Foi Transferido para as Próximas Fases

Para garantir que o escopo da Fase 0 permaneça estritamente focado no motor estável e seguro, os seguintes itens foram oficialmente documentados e transferidos para as fases subsequentes:

1. **Fase 1 (Gateways de Borda & Mensageria Externa):**
   * **Inspeção de Injeção de Prompt via Llama Guard 3 (`SEC-009`)**: Delegada ao microsserviço `guardrail-gateway (:3007)`.
   * **Roteamento Avançado de Mensageria Inter-Agentes e Externa (`SEC-021`)**: O RabbitMQ evolui para uma Topic Exchange `agency.bus` integrando os microsserviços `whatsapp-gateway (:3005)` e `telegram-gateway (:3008)`.
   * **Proteção de Borda & Reverse Proxy Rate Limiting (`SEC-NV-001`)**: Cloudflare WAF / Nginx com limitação por IP na frente dos gateways.
   * **Desacoplamento de Ferramentas via MCP**: Migração de `read_file`, `write_file` e sandbox para o microsserviço independente `workspace-sandbox-service (:3010)`.

2. **Fase 2 (O Conselho Executivo - C-Suite Board & Governança):**
   * **Orquestração Multi-Agentes com LangGraph**: Deliberação assíncrona entre CEO, CTO, CRO e COO consumindo tópicos do RabbitMQ.
   * **Isolamento de Estado Distribuído & Bloqueio Otimista**: Gestão de concorrência em decisões estratégicas complexas.
   * **Governança de Logs de Decisão**: Retenção estendida de auditoria para os 3 Níveis de Autonomia supervisionados por João.
