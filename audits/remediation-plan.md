# 🛠️ Plano Completo de Remediação & Endurecimento (24 Achados)

Este documento estabelece o roadmap de engenharia de segurança, priorização de sprints e critérios de aceitação automatizados (TDD) para neutralizar as 24 vulnerabilidades identificadas.

---

## 🎯 Fase 1: Hotfixes Críticos (Sprint de Contenção Imediata)

> **Objetivo:** Eliminar vetores de RCE, quebra de raiz do workspace e perda silenciosa de tarefas ativas.

### 1.1 Confinamento Estrito do Workspace (SEC-001)
* **Arquivos:** `src/api/router.py`, `src/tools/implementations.py`
* **Implementação:**
  * Substituir `workspace_dir: str` no payload por `workspace_slug: str = Field(..., pattern=r"^[a-zA-Z0-9_\-]+$")`.
  * Forçar a raiz canônica em `<PROJECT_ROOT>/workspaces/clients/<workspace_slug>`.
  * Rejeitar qualquer tentativa de enviar barras (`/`), caminhos absolutos ou sequências `..`.
* **Critério de Teste:** Teste com `workspace_dir: "/"` retorna `HTTP 422`.

### 1.2 Fail-Closed no Sandbox de Terminal (SEC-002)
* **Arquivo:** `src/runner/sandbox.py`
* **Implementação:**
  * Eliminar o fallback silencioso para `SubprocessSandboxDriver` em `get_sandbox_driver()`.
  * Lançar `RuntimeError("Docker daemon is unreachable. Subprocess fallback prohibited.")`.
  * Permitir fallback apenas sob a flag explícita `ALLOW_LOCAL_SUBPROCESS_DEV=true` no `.env`.
* **Critério de Teste:** Com Docker parado, o comando de terminal aborta com erro de segurança sem tocar o host.

### 1.3 Prevenção de Coleta de Lixo em Tasks do Asyncio (SEC-011)
* **Arquivo:** `src/api/router.py`
* **Implementação:**
  * Criar um conjunto `_background_tasks: set[asyncio.Task] = set()`.
  * Retorquir forte referência na corrotina: `_background_tasks.add(task)` e descartar via callback `task.add_done_callback(_background_tasks.discard)`.
* **Critério de Teste:** Execução de tarefas longas não é cancelada mesmo sob chamadas forçadas de `gc.collect()`.

### 1.4 Regex Slug Mandatório em `agent_id` (SEC-005)
* **Arquivos:** `src/api/router.py`, `src/runner/agent_runner.py`
* **Implementação:**
  * Adicionar `pattern=r"^[a-z0-9_\-]+$"` ao campo `agent_id` no schema Pydantic.
* **Critério de Teste:** `agent_id: "../../../etc/passwd"` é bloqueado com `HTTP 422`.

---

## 🛡️ Fase 2: Blindagem de Gateway e Runtime Docker (Curto Prazo)

> **Objetivo:** Controle de acesso na API, isolamento de rede e higiene de processos.

### 2.1 Autenticação e Autorização nos Endpoints (SEC-003)
* **Arquivos:** `src/api/router.py`, `src/config.py`
* **Implementação:**
  * Criar dependência FastAPI verificando o cabeçalho `X-Engine-Key`.
  * Proteger `/api/v1/agent/run`, `/api/v1/agent/run/{run_id}` e `/api/v1/events/stream`.
* **Critério de Teste:** Requisições sem chave retornam `HTTP 401 Unauthorized`.

### 2.2 Isolamento de Rede e Capabilities no Docker (SEC-004)
* **Arquivo:** `src/runner/sandbox.py`
* **Implementação:**
  * Adicionar `--network=none`, `--cap-drop=ALL`, `--read-only` e `--tmpfs /tmp:rw,noexec,nosuid,size=64m`.
* **Critério de Teste:** Comandos `curl` ou `ping` dentro do container falham imediatamente por ausência de interface de rede.

### 2.3 Nomenclatura Determinística e Destruição de Containers Zumbis (SEC-018)
* **Arquivo:** `src/runner/sandbox.py`
* **Implementação:**
  * Nomear o container como `--name f"agency-{run_id}-{int(time.time())}"`.
  * No bloco `TimeoutExpired`, executar `subprocess.run(["docker", "kill", container_name])`.
* **Critério de Teste:** Comandos em timeout não deixam containers ativos no `docker ps`.

### 2.4 Teto Rígido no Timeout do Terminal (SEC-006)
* **Arquivo:** `src/tools/registry.py`
* **Implementação:**
  * Limitar o timeout recebido do modelo: `timeout = max(5, min(int(timeout), 180))`.
* **Critério de Teste:** Timeout de `99999` é reduzido e executado com 180s.

### 2.5 Configuração de CORS e Trusted Hosts (SEC-010)
* **Arquivo:** `src/main.py`
* **Implementação:**
  * Adicionar `CORSMiddleware` com origens configuráveis e `TrustedHostMiddleware`.

---

## 🗄️ Fase 3: Governança do Sistema de Arquivos e Banco (Médio Prazo)

> **Objetivo:** Prevenir corrupção de arquivos, exaustão de memória e garantir integridade transacional.

### 3.1 Escritas Atômicas no Workspace (SEC-014)
* **Arquivo:** `src/tools/implementations.py`
* **Implementação:**
  * Em `write_file` e `patch_file`, gravar em arquivo temporário com sufixo `.tmp` e renomear com `os.replace`.
* **Critério de Teste:** Se o processo falhar no meio, o arquivo anterior não é corrompido nem zerado.

### 3.2 Limites de Tamanho e Paginação em Ferramentas (SEC-013, SEC-015)
* **Arquivo:** `src/tools/implementations.py`
* **Implementação:**
  * `read_file`: Rejeitar leitura de arquivos maiores que 2 MB (`st_size > 2_000_000`).
  * `list_directory`: Limitar a saída em 500 itens com contagem total.
* **Critério de Teste:** Leitura de arquivos grandes retorna mensagem de erro explicativa sem estourar a memória.

### 3.3 Separação de Transações em `send_agent_message` (SEC-017)
* **Arquivo:** `src/tools/implementations.py`
* **Implementação:**
  * Remover `await session.commit()` de dentro da função `send_agent_message`. O commit fica sob responsabilidade do `AgentRunner`.

### 3.4 Rate Limiting e Teto de Fila do Pool (SEC-008)
* **Arquivos:** `src/services/pool.py`, `src/api/router.py`
* **Implementação:**
  * Definir `MAX_QUEUED_RUNS = 50`. Se excedido, responder `HTTP 503 Service Unavailable`.

### 3.5 Inicialização Completa do Alembic e Retenção no SQLite (SEC-019, SEC-024)
* **Arquivos:** `alembic/env.py`, `alembic.ini`, `src/models/database.py`
* **Implementação:**
  * Gerar ambiente Alembic com migrações versionadas.
  * Criar rotina periódica de `PRAGMA incremental_vacuum`.

---

## 🧠 Fase 4: Inteligência, Telemetria e Mensageria (Médio Prazo)

> **Objetivo:** Precisão contábil de tokens, blindagem de prompt e integridade de streams.

### 4.1 Tabela Dinâmica de Preços de Tokens (SEC-016)
* **Arquivo:** `src/runner/agent_runner.py`
* **Implementação:**
  * Mapear precificação real de múltiplos modelos (Gemini Flash, Pro, Claude, Groq) para prompt, cached e completion.
* **Critério de Teste:** Tarefa executada com `gemini-2.5-pro` calcula custos fiéis à tabela do modelo.

### 4.2 Sanitização de Exceções em SQLite e SSE (SEC-007)
* **Arquivo:** `src/runner/agent_runner.py`
* **Implementação:**
  * Aplicar filtro de segredos em `run_record.error_message`, `AuditLog.content` e eventos SSE `"error"`.

### 4.3 Poda de Contexto e Proteção contra Loops (SEC-012, SEC-009)
* **Arquivo:** `src/runner/agent_runner.py`
* **Implementação:**
  * Aplicar janela deslizante quando `messages` exceder 64k tokens.
  * Envelopar dados do workspace em `<untrusted_tool_result>`.
  * Interromper tarefas se a LLM repetir 3 vezes a mesma chamada com o mesmo erro.

### 4.4 Higiene na Mensageria Inter-Agentes e SSE (SEC-020, SEC-021, SEC-022, SEC-023)
* **Arquivos:** `src/tools/implementations.py`, `src/api/sse.py`, `src/services/recovery.py`, `src/api/router.py`
* **Implementação:**
  * Validar `to_agent` contra catálogo oficial e impor teto de 64 KB no payload.
  * Sanitizar quebras de linha em `event_type` no SSE.
  * Gravar `AuditLog` para tarefas recuperadas no boot.
  * Adicionar cabeçalho `X-Request-ID` para rastreamento distribuído.
