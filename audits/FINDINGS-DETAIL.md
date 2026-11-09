# 🔍 Detalhamento Técnico das 24 Vulnerabilidades (Full Scope)

Este documento contém o dossiê técnico exaustivo das **24 vulnerabilidades e defeitos de engenharia** mapeados durante a auditoria completa do **The Agency Engine (Fase 0)**.

---

## SEC-001: Injeção de Caminho de Workspace Arbitrário via Parâmetro da API

* **Identificador:** SEC-001  
* **Severidade:** **CRÍTICA**  
* **CVSS v3.1:** `9.8` (`CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H`)  
* **CWEs:** [CWE-22](https://cwe.mitre.org/data/definitions/22.html), [CWE-73](https://cwe.mitre.org/data/definitions/73.html)  
* **Arquivo Afetado:** [`services/engine/src/api/router.py:30`](file:///home/joao/projetos/the%20agency/services/engine/src/api/router.py#L30) e [`services/engine/src/runner/agent_runner.py:108`](file:///home/joao/projetos/the%20agency/services/engine/src/runner/agent_runner.py#L108)  

### Análise de Causa-Raiz
No endpoint `POST /api/v1/agent/run`, `AgentRunRequest` aceita `workspace_dir: str = "workspaces/clients/default"`. Não há validação impedindo valores como `"/"`, `"/etc"` ou `"/home/joao"`.
Na ferramenta `resolve_safe_path`:
```python
resolved_ws = workspace_dir.resolve()
target.relative_to(resolved_ws)
```
Se `workspace_dir` for `/`, todo e qualquer arquivo do disco hospedeiro é considerado dentro do workspace. O Docker montará `/:/workspace`, concedendo ao container acesso de leitura e escrita à raiz do sistema.

### Remediação
Restringir `workspace_dir` para slugs alfanuméricos relativos à pasta canônica:
```python
# Em src/api/router.py
def get_safe_workspace(slug: str) -> Path:
    if not re.match(r"^[a-zA-Z0-9_\-]+$", slug):
        raise HTTPException(status_code=422, detail="Invalid workspace slug.")
    base = Path("workspaces/clients").resolve()
    target = (base / slug).resolve()
    target.mkdir(parents=True, exist_ok=True)
    return target
```

---

## SEC-002: Execução de Comandos no Host sem Isolamento no Fallback

* **Identificador:** SEC-002  
* **Severidade:** **CRÍTICA**  
* **CVSS v3.1:** `9.8` (`CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H`)  
* **CWEs:** [CWE-250](https://cwe.mitre.org/data/definitions/250.html), [CWE-78](https://cwe.mitre.org/data/definitions/78.html), [CWE-200](https://cwe.mitre.org/data/definitions/200.html)  
* **Arquivo Afetado:** [`services/engine/src/runner/sandbox.py:50`](file:///home/joao/projetos/the%20agency/services/engine/src/runner/sandbox.py#L50) e [`services/engine/src/runner/sandbox.py:205`](file:///home/joao/projetos/the%20agency/services/engine/src/runner/sandbox.py#L205)  

### Análise de Causa-Raiz
Quando o Docker daemon não está rodando, `get_sandbox_driver()` faz downgrade para `SubprocessSandboxDriver`. Ele executa `subprocess.Popen(command, shell=True, ...)` no host, removendo apenas 3 chaves de API do ambiente e deixando chaves SSH, tokens de nuvem e ferramentas de sistema expostos.

### Remediação
Adotar política de **Fail-Closed**: se o Docker estiver inacessível, abortar com erro de infraestrutura segura:
```python
def get_sandbox_driver() -> BaseSandboxDriver:
    docker = DockerSandboxDriver()
    if docker.is_available():
        return docker
    raise RuntimeError("Docker daemon is unreachable. Execution halted for security.")
```

---

## SEC-003: Ausência Total de Autenticação/Autorização na API

* **Identificador:** SEC-003  
* **Severidade:** **ALTA**  
* **CVSS v3.1:** `8.6` (`CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:L`)  
* **CWEs:** [CWE-306](https://cwe.mitre.org/data/definitions/306.html), [CWE-862](https://cwe.mitre.org/data/definitions/862.html)  
* **Arquivo Afetado:** [`services/engine/src/api/router.py:24`](file:///home/joao/projetos/the%20agency/services/engine/src/api/router.py#L24)  

### Análise de Causa-Raiz
Nenhum endpoint possui dependências de autenticação (`HTTPBearer` ou `APIKeyHeader`). Qualquer cliente na rede pode submeter tarefas caras ao Gemini, visualizar o stream SSE de outros clientes ou consultar dados do SQLite.

### Remediação
Exigir `X-Engine-Key` ou `Authorization: Bearer <token>` em todas as rotas da API:
```python
async def require_auth(key: str = Security(APIKeyHeader(name="X-Engine-Key"))):
    if key != get_settings().ENGINE_API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")
```

---

## SEC-004: Falta de Isolamento de Rede e Capabilities no Container Docker

* **Identificador:** SEC-004  
* **Severidade:** **ALTA**  
* **CVSS v3.1:** `7.5` (`CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:C/C:H/I:N/A:N`)  
* **CWEs:** [CWE-276](https://cwe.mitre.org/data/definitions/276.html), [CWE-918](https://cwe.mitre.org/data/definitions/918.html)  
* **Arquivo Afetado:** [`services/engine/src/runner/sandbox.py:142`](file:///home/joao/projetos/the%20agency/services/engine/src/runner/sandbox.py#L142)  

### Análise de Causa-Raiz
O comando `docker run` não passa `--network=none`, `--cap-drop=ALL` nem `--read-only`. O container tem acesso de rede irrestrito à internet, portas do host e endpoints de metadados (`169.254.169.254`).

### Remediação
Configurar bandeiras de contenção estrita no Docker:
```python
docker_cmd = [
    "docker", "run", "--rm",
    "--network=none",
    "--cap-drop=ALL",
    "--security-opt=no-new-privileges:true",
    "--read-only",
    "--tmpfs=/tmp:rw,noexec,nosuid,size=64m",
    f"--memory={self.memory_limit}",
    f"--cpus={self.cpus_limit}",
    f"--pids-limit={self.pids_limit}",
    "-v", f"{cwd.resolve()}:/workspace:rw",
    "-w", "/workspace",
    self.image, "bash", "-c", command,
]
```

---

## SEC-005: Directory Traversal no Carregamento de Perfis YAML

* **Identificador:** SEC-005  
* **Severidade:** **ALTA**  
* **CVSS v3.1:** `7.5` (`CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:N/A:N`)  
* **CWEs:** [CWE-22](https://cwe.mitre.org/data/definitions/22.html), [CWE-23](https://cwe.mitre.org/data/definitions/23.html)  
* **Arquivo Afetado:** [`services/engine/src/runner/agent_runner.py:50`](file:///home/joao/projetos/the%20agency/services/engine/src/runner/agent_runner.py#L50)  

### Análise de Causa-Raiz
`load_agent_profile(agent_id)` concatena caminhos diretamente com `f"{agent_id}.yaml"`. Se `agent_id` contiver sequências `../`, o motor carrega arquivos YAML fora das pastas autorizadas.

### Remediação
Adicionar validação regex no schema do Pydantic:
```python
agent_id: str = Field(..., pattern=r"^[a-z0-9_\-]+$")
```

---

## SEC-006: Timeout Ilimitado no Terminal permitindo DoS

* **Identificador:** SEC-006  
* **Severidade:** **MÉDIA**  
* **CVSS v3.1:** `5.3` (`CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:L`)  
* **CWEs:** [CWE-400](https://cwe.mitre.org/data/definitions/400.html)  
* **Arquivo Afetado:** [`services/engine/src/tools/registry.py:223`](file:///home/joao/projetos/the%20agency/services/engine/src/tools/registry.py#L223)  

### Análise de Causa-Raiz
`timeout = int(arguments.get("timeout", 60))` aceita qualquer valor sem teto. Um valor como `999999` prende o processo e a vaga no semáforo do pool.

### Remediação
```python
timeout = max(5, min(int(arguments.get("timeout", 60)), 180))
```

---

## SEC-007: Vazamento Potencial de API Keys em Exceções Gravadas no SQLite e SSE

* **Identificador:** SEC-007  
* **Severidade:** **MÉDIA**  
* **CVSS v3.1:** `5.5` (`CVSS:3.1/AV:N/AC:L/PR:L/UI:N/S:U/C:H/I:N/A:N`)  
* **CWEs:** [CWE-532](https://cwe.mitre.org/data/definitions/532.html), [CWE-209](https://cwe.mitre.org/data/definitions/209.html)  
* **Arquivo Afetado:** [`services/engine/src/runner/agent_runner.py:198`](file:///home/joao/projetos/the%20agency/services/engine/src/runner/agent_runner.py#L198)  

### Análise de Causa-Raiz
Ao capturar falhas da API do Gemini/LiteLLM, `str(exc)` é salvo sem filtro em `AgentRun.error_message`, `AuditLog.content` e transmitido no evento SSE `"error"`. URLs de requisição com chaves expostas acabam salvas no banco.

### Remediação
Sanitizar o texto de exceções antes de gravar ou transmitir:
```python
def sanitize_secret(text: str) -> str:
    key = get_settings().GEMINI_API_KEY
    return text.replace(key, "[REDACTED_KEY]") if key else text
```

---

## SEC-008: Ausência de Rate Limiting e In-Memory Queue DoS

* **Identificador:** SEC-008  
* **Severidade:** **MÉDIA**  
* **CVSS v3.1:** `5.3` (`CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:L`)  
* **CWEs:** [CWE-770](https://cwe.mitre.org/data/definitions/770.html)  
* **Arquivo Afetado:** [`services/engine/src/services/pool.py:30`](file:///home/joao/projetos/the%20agency/services/engine/src/services/pool.py#L30)  

### Análise de Causa-Raiz
O semáforo assíncrono limita a execução ativa a 5, mas requisições excedentes são enfileiradas em memória sem limite máximo. Um ataque com 100.000 requisições esgota a memória do processo.

### Remediação
Estabelecer um teto máximo de fila (ex: 50 tarefas) no `AgentPool`.

---

## SEC-009: Injeção Indireta de Prompt em Dados do Workspace

* **Identificador:** SEC-009  
* **Severidade:** **BAIXA**  
* **CVSS v3.1:** `3.7` (`CVSS:3.1/AV:L/AC:H/PR:N/UI:N/S:U/C:L/I:L/A:N`)  
* **CWEs:** [CWE-1426](https://cwe.mitre.org/data/definitions/1426.html)  
* **Arquivo Afetado:** [`services/engine/src/runner/agent_runner.py:350`](file:///home/joao/projetos/the%20agency/services/engine/src/runner/agent_runner.py#L350)  

### Análise de Causa-Raiz
Retornos de ferramentas (`read_file`, `run_terminal_command`) são injetados sem delimitação semântica. Textos contendo comandos adversos podem influenciar o raciocínio da LLM.

### Remediação
Envelopar dados externos em `<untrusted_tool_result>...</untrusted_tool_result>`.

---

## SEC-010: Ausência de CORS e Host Header Validation

* **Identificador:** SEC-010  
* **Severidade:** **BAIXA**  
* **CVSS v3.1:** `3.1` (`CVSS:3.1/AV:N/AC:H/PR:N/UI:R/S:U/C:L/I:N/A:N`)  
* **CWEs:** [CWE-942](https://cwe.mitre.org/data/definitions/942.html)  
* **Arquivo Afetado:** [`services/engine/src/main.py:50`](file:///home/joao/projetos/the%20agency/services/engine/src/main.py#L50)  

### Análise de Causa-Raiz
O FastAPI não possui `CORSMiddleware` nem `TrustedHostMiddleware`, abrindo margem para configurações erradas de CORS ou DNS rebinding quando exposto a dashboards web.

---

## SEC-011: Perda de Tarefas por Garbage Collection de Tasks do Asyncio

* **Identificador:** SEC-011  
* **Severidade:** **ALTA**  
* **CVSS v3.1:** `7.5` (`CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:H`)  
* **CWEs:** [CWE-400](https://cwe.mitre.org/data/definitions/400.html), [CWE-665](https://cwe.mitre.org/data/definitions/665.html)  
* **Arquivo Afetado:** [`services/engine/src/api/router.py:128`](file:///home/joao/projetos/the%20agency/services/engine/src/api/router.py#L128)  

### Análise de Causa-Raiz
Em `router.py:128`:
`asyncio.create_task(pool.submit(run_id=run_id, coro=runner.run()))`
O Python mantém apenas referências fracas para tasks em segundo plano no event loop. Se uma task não for retida em um conjunto (`set`) no processo, o Garbage Collector do Python pode coletá-la e cancelá-la silenciosamente no meio da execução.

### Remediação
Manter um conjunto global de tarefas ativas:
```python
_active_background_tasks = set()

task = asyncio.create_task(pool.submit(run_id=run_id, coro=runner.run()))
_active_background_tasks.add(task)
task.add_done_callback(_active_background_tasks.discard)
```

---

## SEC-012: Explosão Descontrolada do Context Window e Loops Infinitos de Falha

* **Identificador:** SEC-012  
* **Severidade:** **ALTA**  
* **CVSS v3.1:** `7.1` (`CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:L/A:H`)  
* **CWEs:** [CWE-400](https://cwe.mitre.org/data/definitions/400.html), [CWE-835](https://cwe.mitre.org/data/definitions/835.html)  
* **Arquivo Afetado:** [`services/engine/src/runner/agent_runner.py:296`](file:///home/joao/projetos/the%20agency/services/engine/src/runner/agent_runner.py#L296)  

### Análise de Causa-Raiz
A lista `messages` acumula todas as chamadas de ferramentas e resultados sem truncamento. Ao longo de 25 passos com buffers de 128 KB, o contexto ultrapassa 3.2 MB (~1 milhão de tokens), estourando o limite da API ou gerando contas astronômicas. Além disso, se a LLM repetir uma chamada errônea consecutivamente, o motor não detecta o loop de falha.

### Remediação
Implementar poda deslizante (sliding window) ou compactação de contexto quando a lista de mensagens ultrapassar 64.000 tokens, e disjuntor para 3 falhas idênticas consecutivas.

---

## SEC-013: Travamento de Memória por Listagem Ilimitada em `list_directory`

* **Identificador:** SEC-013  
* **Severidade:** **MÉDIA**  
* **CVSS v3.1:** `5.3` (`CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:L`)  
* **CWEs:** [CWE-400](https://cwe.mitre.org/data/definitions/400.html), [CWE-770](https://cwe.mitre.org/data/definitions/770.html)  
* **Arquivo Afetado:** [`services/engine/src/tools/implementations.py:126`](file:///home/joao/projetos/the%20agency/services/engine/src/tools/implementations.py#L126)  

### Análise de Causa-Raiz
`list_directory` usa `target_dir.iterdir()` sem limites de paginação. Em pastas com milhares de itens (como `node_modules` ou caches de build), a função cria uma lista gigantesca em memória, consumindo centenas de megabytes.

### Remediação
Limitar o retorno a no máximo 500 itens com indicação de contagem total truncada.

---

## SEC-014: Escritas Não-Atômicas em Arquivos Provocando Corrupção do Workspace

* **Identificador:** SEC-014  
* **Severidade:** **MÉDIA**  
* **CVSS v3.1:** `5.9` (`CVSS:3.1/AV:N/AC:H/PR:N/UI:N/S:U/C:N/I:H/A:L`)  
* **CWEs:** [CWE-367](https://cwe.mitre.org/data/definitions/367.html), [CWE-377](https://cwe.mitre.org/data/definitions/377.html)  
* **Arquivo Afetado:** [`services/engine/src/tools/implementations.py:77`](file:///home/joao/projetos/the%20agency/services/engine/src/tools/implementations.py#L77) e [`line 110`](file:///home/joao/projetos/the%20agency/services/engine/src/tools/implementations.py#L110)  

### Análise de Causa-Raiz
`write_file` e `patch_file` executam `target_file.write_text()`. Se o processo for interrompido durante a escrita, o arquivo original é truncado e perde dados.

### Remediação
Escrever em arquivo temporário no mesmo diretório e realizar renomeação atômica via `os.replace`:
```python
tmp_file = target_file.with_suffix(".tmp." + uuid.uuid4().hex[:8])
tmp_file.write_text(content, encoding="utf-8")
os.replace(tmp_file, target_file)
```

---

## SEC-015: Leitura Descontrolada de Arquivos Binários Gigantes em `read_file`

* **Identificador:** SEC-015  
* **Severidade:** **MÉDIA**  
* **CVSS v3.1:** `5.3` (`CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:L`)  
* **CWEs:** [CWE-400](https://cwe.mitre.org/data/definitions/400.html)  
* **Arquivo Afetado:** [`services/engine/src/tools/implementations.py:59`](file:///home/joao/projetos/the%20agency/services/engine/src/tools/implementations.py#L59)  

### Análise de Causa-Raiz
`read_file` lê todo o arquivo na memória (`read_text`) sem inspecionar `st_size`. A leitura de arquivos de banco (`.db`) ou binários grandes esgota a memória do processo.

### Remediação
Verificar o tamanho antes da leitura: recusar arquivos maiores que 2 MB com mensagem de instrução para o agente.

---

## SEC-016: Precificação Estática Incorreta de Modelos na Telemetria Financeira

* **Identificador:** SEC-016  
* **Severidade:** **MÉDIA**  
* **CVSS v3.1:** `5.3` (`CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:L/A:N`)  
* **CWEs:** [CWE-682](https://cwe.mitre.org/data/definitions/682.html)  
* **Arquivo Afetado:** [`services/engine/src/runner/agent_runner.py:78`](file:///home/joao/projetos/the%20agency/services/engine/src/runner/agent_runner.py#L78)  

### Análise de Causa-Raiz
`calculate_token_costs` fixa valores do Gemini Flash. Agentes configurados com modelos caros (Gemini Pro, Claude Sonnet) têm seus custos subdimensionados em até 95%, distorcendo relatórios de margem financeira do CFO.

### Remediação
Criar tabela dinâmica de preços mapeada por prefixo de modelo.

---

## SEC-017: Conflito de Transação e Commit Prematuro em `send_agent_message`

* **Identificador:** SEC-017  
* **Severidade:** **MÉDIA**  
* **CVSS v3.1:** `4.8` (`CVSS:3.1/AV:N/AC:H/PR:N/UI:N/S:U/C:N/I:L/A:L`)  
* **CWEs:** [CWE-662](https://cwe.mitre.org/data/definitions/662.html), [CWE-675](https://cwe.mitre.org/data/definitions/675.html)  
* **Arquivo Afetado:** [`services/engine/src/tools/implementations.py:189`](file:///home/joao/projetos/the%20agency/services/engine/src/tools/implementations.py#L189)  

### Análise de Causa-Raiz
`send_agent_message` recebe a `session` do chamador e executa `await session.commit()`. Isso encerra a transação do `AgentRunner` no meio do registro de `AuditLog`, gerando conflitos de concorrência ou commits parciais.

### Remediação
Remover o commit interno de ferramentas de biblioteca e deixar o commit sob governança exclusiva da camada do runner.

---

## SEC-018: Falta de Nomenclatura Determinística em Containers (Zumbis no Host)

* **Identificador:** SEC-018  
* **Severidade:** **MÉDIA**  
* **CVSS v3.1:** `5.3` (`CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:L`)  
* **CWEs:** [CWE-404](https://cwe.mitre.org/data/definitions/404.html)  
* **Arquivo Afetado:** [`services/engine/src/runner/sandbox.py:143`](file:///home/joao/projetos/the%20agency/services/engine/src/runner/sandbox.py#L143)  

### Análise de Causa-Raiz
Ao atingir timeout, o motor mata o processo CLI do Docker com `SIGKILL`. Sem um nome identificador único no container (`--name`), o daemon do Docker pode manter o container rodando em segundo plano indefinidamente.

### Remediação
Passar `--name f"agency-{run_id}-{int(time.time())}"` e, em caso de timeout, invocar `docker kill <name>` explicitamente.

---

## SEC-019: Ausência da Infraestrutura de Migração do Alembic

* **Identificador:** SEC-019  
* **Severidade:** **BAIXA**  
* **CVSS v3.1:** `3.3` (`CVSS:3.1/AV:L/AC:L/PR:N/UI:N/S:U/C:N/I:L/A:N`)  
* **CWEs:** [CWE-1059](https://cwe.mitre.org/data/definitions/1059.html)  
* **Arquivo Afetado:** [`services/engine/alembic`](file:///home/joao/projetos/the%20agency/services/engine/alembic)  

### Análise de Causa-Raiz
O diretório existe mas não contém `env.py`, `alembic.ini` nem scripts de migração. Alterações de tabelas em produção não podem ser aplicadas sem perda de dados no SQLite.

---

## SEC-020: Lacuna de Auditoria no Crash Recovery de Tarefas Órfãs

* **Identificador:** SEC-020  
* **Severidade:** **BAIXA**  
* **CVSS v3.1:** `3.1` (`CVSS:3.1/AV:N/AC:H/PR:N/UI:N/S:U/C:N/I:L/A:N`)  
* **CWEs:** [CWE-778](https://cwe.mitre.org/data/definitions/778.html)  
* **Arquivo Afetado:** [`services/engine/src/services/recovery.py:20`](file:///home/joao/projetos/the%20agency/services/engine/src/services/recovery.py#L20)  

### Análise de Causa-Raiz
A recuperação atualiza `AgentRun`, mas não insere um registro na tabela `audit_logs` documentando a queda do servidor e a interrupção da execução.

---

## SEC-021: Destinatários Não Validados e Payload Sem Limite na Mensageria

* **Identificador:** SEC-021  
* **Severidade:** **BAIXA**  
* **CVSS v3.1:** `3.7` (`CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:L/A:N`)  
* **CWEs:** [CWE-20](https://cwe.mitre.org/data/definitions/20.html)  
* **Arquivo Afetado:** [`services/engine/src/tools/implementations.py:160`](file:///home/joao/projetos/the%20agency/services/engine/src/tools/implementations.py#L160)  

### Análise de Causa-Raiz
`send_agent_message` permite enviar mensagens para destinatários inexistentes e aceita dicionários JSON de qualquer tamanho, permitindo poluição da fila.

---

## SEC-022: Injeção de Protocolo SSE por Quebras de Linha no Event Type

* **Identificador:** SEC-022  
* **Severidade:** **BAIXA**  
* **CVSS v3.1:** `3.7` (`CVSS:3.1/AV:N/AC:H/PR:N/UI:N/S:U/C:N/I:L/A:N`)  
* **CWEs:** [CWE-113](https://cwe.mitre.org/data/definitions/113.html)  
* **Arquivo Afetado:** [`services/engine/src/api/sse.py:20`](file:///home/joao/projetos/the%20agency/services/engine/src/api/sse.py#L20)  

### Análise de Causa-Raiz
`SSEEvent.encode()` interpola `event: {self.event}` sem sanitizar `\n`. Se o tipo de evento contiver quebras de linha, ele corrompe o enquadramento de pacotes SSE no cliente.

---

## SEC-023: Ausência de Correlation ID (`X-Request-ID`) nas Rotas e Logs

* **Identificador:** SEC-023  
* **Severidade:** **BAIXA**  
* **CVSS v3.1:** `2.5` (`CVSS:3.1/AV:N/AC:H/PR:N/UI:N/S:U/C:N/I:N/A:N`)  
* **CWEs:** [CWE-778](https://cwe.mitre.org/data/definitions/778.html)  
* **Arquivo Afetado:** [`services/engine/src/api/router.py:24`](file:///home/joao/projetos/the%20agency/services/engine/src/api/router.py#L24)  

### Análise de Causa-Raiz
Falta de rastreabilidade de correlação ponta a ponta entre a requisição HTTP inicial e as corrotinas em background no Loguru.

---

## SEC-024: Ausência de Rotina de Retenção e Compactação no SQLite WAL

* **Identificador:** SEC-024  
* **Severidade:** **BAIXA**  
* **CVSS v3.1:** `2.7` (`CVSS:3.1/AV:N/AC:H/PR:N/UI:N/S:U/C:N/I:N/A:L`)  
* **CWEs:** [CWE-770](https://cwe.mitre.org/data/definitions/770.html)  
* **Arquivo Afetado:** [`services/engine/src/models/database.py:33`](file:///home/joao/projetos/the%20agency/services/engine/src/models/database.py#L33)  

### Análise de Causa-Raiz
As tabelas `audit_logs` e `token_metrics` crescem sem expiração ou rotina de `PRAGMA incremental_vacuum`, gerando fragmentação contínua do banco com o tempo.
