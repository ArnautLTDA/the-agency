# 🔬 Especificação Técnica: FASE 0 — O Motor de Agentes Standalone

> **Documento:** docs/fase-0-motor-agentes.md  
> **Status:** Especificação Consolidada e 100% Homologada por João (Chefe)

---

## 1. Objetivo & Escopo da Fase 0

Construir a infraestrutura computacional básica (o motor) que permite instanciar e executar agentes autônomos fora do Antigravity, com controle estrito de custos, isolamento seguro de terminal e persistência de dados.

### Fronteiras Rígidas da Fase 0:
* **O Que Está Incluso:** O servidor da API assíncrona, a estrutura canônica de pastas, o loop de execução de agentes individuais (Agent Runner), o pool de concorrência com semáforo, o registro de ferramentas com sandbox Docker descartável, a camada de banco de dados, o barramento de mensagens como repositório persistente, o carregamento de configurações e perfis declarativos, a consulta de câmbio e a telemetria financeira de tokens.
* **O Que NÃO Está Incluso:** Orquestração de equipes multi-agentes via LangGraph (Fase 2), C-Suite (Fase 2), funis de prospecção e leads (Fase 3), fábrica de software completa (Fase 4) ou deploys de produção (Fase 5).

---

## 2. Estrutura Canônica de Diretórios (`services/engine/`)

O backend da Fase 0 organiza seu código sob a estrutura canônica padrão da indústria:

```text
services/engine/
├── pyproject.toml              # Dependências, metadados e scripts de execução
├── .env.example                # Documentação de todas as variáveis obrigatórias
├── alembic/                    # Histórico e scripts de migração do banco de dados
│   ├── env.py
│   └── versions/
├── config/
│   └── agents/
│       ├── council/            # Perfis do C-Suite (imutáveis para IA, calibrados exclusivamente por João)
│       │   ├── ceo.yaml
│       │   ├── cto.yaml
│       │   ├── cro.yaml
│       │   └── coo.yaml
│       └── pipeline/           # Perfis dos agentes operacionais (otimizados pelo Conselho com foco em ROI)
│           └── homologation_agent.yaml
├── src/
│   ├── __init__.py
│   ├── main.py                 # Ponto de entrada FastAPI e ciclo de vida lifespan
│   ├── config.py               # Validação de variáveis via Pydantic-Settings
│   ├── runner/
│   │   ├── __init__.py
│   │   ├── agent_runner.py     # Loop ReAct determinístico assíncrono
│   │   └── sandbox.py          # Driver de execução em containers Docker descartáveis
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── registry.py         # Mapeamento de esquemas JSON e despacho de ferramentas
│   │   └── implementations.py  # Funções nativas (read, write, patch, terminal, message)
│   ├── models/
│   │   ├── __init__.py
│   │   ├── database.py         # Conexão assíncrona com SQLite em Modo WAL
│   │   └── entities.py         # Tabelas SQLModel (AgentMessage, AuditLog, TokenMetric)
│   ├── api/
│   │   ├── __init__.py
│   │   ├── router.py           # Endpoints HTTP (/health, /agent/run)
│   │   └── sse.py              # Gerenciador de streaming de eventos SSE
│   └── services/
│       ├── __init__.py
│       ├── currency.py         # Serviço de consulta e cache de câmbio USD/BRL
│       └── pool.py             # Semáforo de concorrência e enfileiramento assíncrono
├── tests/
│   ├── conftest.py             # Fixtures e setup do ambiente de testes
│   └── test_e2e_runner.py      # Bateria de testes E2E reais contra o Gemini
└── logs/
    └── engine.log              # Arquivo de logs rotacionado via Loguru
```

---

## 3. Especificação dos Componentes da Fundação

### 3.1 Backend de Serviços (FastAPI na porta :8000)
* **Pilha Tecnológica:** Python 3.12+ gerenciado com `uv` ou `poetry`.
* **Modo de Operação:** Servidor assíncrono local (`uvicorn`).
* **Validação de Configuração (Fail-Fast Boot):** As variáveis de ambiente e segredos são carregados a partir de um arquivo `.env` e validados no momento da inicialização via `pydantic-settings`. Se qualquer variável obrigatória (como `GEMINI_API_KEY`) estiver ausente ou malformatada, o servidor recusa iniciar e emite mensagem clara de configuração ausente.
* **Gerenciamento de Concorrência (Worker Pool):** O motor implementa um semáforo assíncrono com teto configurável via variável de ambiente `MAX_CONCURRENT_AGENTS` (padrão: 5 agentes simultâneos). Tarefas excedentes entram em fila ordenada, prevenindo sobrecarga de memória RAM na máquina e estouro de limites de concorrência nas APIs.
* **Armazenamento e Rotação de Logs Operacionais:** Utilização do Loguru para gerenciamento de logs. Os logs operacionais do servidor (requisições, erros de sistema e tracebacks) são gravados em arquivo local `logs/engine.log` com rotação automática ao atingir 10MB e retenção configurada, além de exibição formatada no console.

### 3.2 Contrato dos Endpoints da API

* `GET /api/v1/health`:
  * **Comportamento:** Retorna status de saúde do serviço, conectividade com SQLite, cotação atual do câmbio e validação das credenciais de IA.
  * **Status Code:** `200 OK` (ou `503 Service Unavailable` se o banco ou chaves estiverem inoperantes).

* `POST /api/v1/agent/run`:
  * **Modelo de Operação:** Estritamente Assíncrono (não bloqueante).
  * **Payload de Entrada (JSON):**
    * `agent_id` (string obrigatória): Identificador do perfil do agente em formato slug snake_case (ex: `homologation_agent`), mapeando diretamente para seu arquivo de configuração `config/agents/<agent_id>.yaml`.
    * `task` (string obrigatória): Instrução detalhada da tarefa a ser executada.
    * `workspace_dir` (string opcional): Caminho da pasta de trabalho (padrão: `workspaces/clients/default`).
    * `max_iterations` (inteiro opcional): Teto máximo de iterações (padrão: 25).
  * **Resposta Imediata:** `202 Accepted` contendo `run_id` (UUID v4), status `queued` e a URL do canal de streaming correspondente.
  * **Garantia de Segurança:** O servidor despacha a tarefa para o worker pool e libera a conexão HTTP em milissegundos, sendo imune a quedas por timeout de proxy (Cloudflare/Nginx 504) e esgotamento de conexões.

* `GET /api/v1/agent/run/{run_id}`:
  * **Comportamento:** Consulta o estado de uma execução a qualquer momento.
  * **Resposta:** Status atual (`queued`, `running`, `completed`, `failed`, `interrupted`), data de início/fim, iterações consumidas, total de tokens gastos, custo em Reais e resumo da resposta final.

* `GET /api/v1/events/stream`:
  * **Comportamento:** Canal contínuo Server-Sent Events (SSE) que aceita o parâmetro opcional `?run_id=<uuid>` para filtrar eventos de uma tarefa específica (ou transmite o fluxo global se omitido).
  * **Estrutura dos Eventos Transmitidos:** Cada evento segue a especificação padrão SSE (`event`, `data` em JSON estruturado e `id` incremental para reconexão automática).
  * **Tipos de Eventos Padronizados:**
    * `thought`: Raciocínio emitido pelo modelo.
    * `tool_call`: Chamada de ferramenta com nome e argumentos passados.
    * `tool_result`: Retorno recebido da execução da ferramenta.
    * `token_usage`: Parcial de tokens e custo financeiro apurado.
    * `error`: Registro de falha ou retentativa em andamento.
    * `task_completed`: Notificação de encerramento da execução com o veredito final.

### 3.3 O Motor de Execução (Agent Runner)
* **Mecanismo:** Loop ReAct determinístico assíncrono (Entrada ➔ Raciocínio ➔ Chamada de Ferramenta ➔ Observação ➔ Resposta).
* **Proxy de Modelos & Roteamento:** Utilização do LiteLLM como roteador de modelos com suporte a fallback multi-provedor (Gemini Flash como primário, com fallback automático configurado para Groq ou Claude).
* **Captura Fiel de Telemetria:** Para eliminar qualquer perda de precisão, o motor extrai a contagem de tokens e dados de cache diretamente do payload original da API (`response._hidden_params["original_response"]`), garantindo cálculo financeiro exato ao centavo.
* **Perfis de Agente Desacoplados (Configuração em YAML):** Cada agente possui seu perfil em YAML contendo identificador único, modelo LLM atribuído, temperatura, ferramentas autorizadas e system prompt:
  * **Perfis do Conselho (`config/agents/council/`):** De edição e calibragem exclusiva e soberana de João via Cockpit (bloqueio estrutural contra qualquer tentativa de alteração por IAs).
  * **Perfis da Esteira Operacional (`config/agents/pipeline/`):** Podem ser testados e refinados pelo Conselho Executivo com foco em maximização de lucro líquido e Token Economy (troca de modelos por alternativas mais custo-eficientes e tuning de prompts). No momento da execução, o motor carrega o arquivo e interpola dinamicamente as variáveis de contexto (`workspace_dir`, `task_id`, data atual).
* **Teto de Segurança:** Limite estrito de 25 iterações por tarefa. Atingido o teto, o disjuntor (Circuit Breaker) congela a execução com segurança.

### 3.4 Registro de Ferramentas & Padrão MCP (Model Context Protocol)

O motor obedece a duas diretrizes arquiteturais invioláveis estabelecidas por João:
1. **Todas as ferramentas e gateways são microsserviços desacoplados e independentes.**
2. **Todas as ferramentas operam obrigatoriamente sob o padrão oficial MCP (Model Context Protocol).**

#### Arquitetura MCP no Motor de Agentes:
* **O Motor como MCP Client (Host):**
  * O orquestrador central (`engine-core` na porta `:8000`) atua como um **MCP Client (Host)** compatível com a especificação JSON-RPC 2.0 via transporte SSE/HTTP (Server-Sent Events) ou subprocessos locais.
  * No carregamento do perfil de cada agente, o motor conecta-se aos servidores MCP configurados e descobre dinamicamente as ferramentas disponíveis através do protocolo padrão `tools/list`.
  * O motor converte automaticamente os `inputSchema` de cada ferramenta MCP para a especificação de *Function Calling* nativa da LLM (Gemini Flash / LiteLLM).
  * Quando a LLM emite uma chamada de ferramenta, o motor roteia a execução disparando uma requisição JSON-RPC `tools/call` diretamente para o servidor MCP responsável, devolvendo a resposta estruturada para o loop de raciocínio.

* **Servidor MCP de Workspace & Sandbox (`workspace-mcp-server` na porta `:3010` via MCP SSE):**
  * Microsserviço independente que implementa um **MCP Server oficial**, expondo as ferramentas de manipulação de código e terminal via JSON-RPC:

| Ferramenta MCP (`tools/list`) | Servidor MCP Responsável | Schema de Entrada (`inputSchema`) | Comportamento no Servidor MCP | Regra de Bloqueio / Falha |
| :--- | :--- | :--- | :--- | :--- |
| `read_file` | `workspace-mcp-server (:3010)` | `path: string` | Lê e retorna o conteúdo textual do arquivo. | Erro se o arquivo não existir ou tentar escapar da raiz do workspace (Path Traversal). |
| `write_file` | `workspace-mcp-server (:3010)` | `path: string, content: string, overwrite: boolean` | Grava ou sobrescreve o arquivo com criação automática de pastas. | Bloqueio imediato se o destino estiver fora da pasta de trabalho. |
| `patch_file` | `workspace-mcp-server (:3010)` | `path: string, search_block: string, replace_block: string` | Substitui cirurgicamente um bloco específico de código (diff exato). | Erro se o bloco de busca não for encontrado exatamente uma vez ou se o arquivo for inválido. |
| `run_terminal_command` | `workspace-mcp-server (:3010)` | `command: string, timeout_seconds: number` | Executa o comando em container Docker descartável e devolve stdout, stderr e exit code. | Bloqueio se exceder timeout ou o teto de buffer de 128 KB. |
| `send_agent_message` | `engine-core (:8000)` | `to_agent: string, message_type: string, payload: object` | Grava mensagem validada na fila do banco para outro agente ou broadcast. | Erro se o tipo de mensagem não constar no enum oficial da esteira. |

#### Política de Sandbox de Terminal no Servidor MCP (:3010):
1. **Isolamento via Containers Docker Descartáveis (Padrão Devin / OpenHands):**
   * Toda execução da ferramenta MCP `run_terminal_command` roda isolada dentro de um container Docker efêmero (`node:20-slim`), gerenciado pelo microsserviço `:3010`, criado e destruído sob demanda.
   * O container monta estritamente a pasta do projeto (`/workspaces/clients/<client-slug>`) como volume interno `/workspace`.
   * **Imunidade Total do Host:** O agente não possui qualquer acesso ao sistema operacional da sua máquina, chaves SSH, credenciais ou arquivos fora da pasta montada.
   * **Limites de Recursos do Container:** Teto de memória RAM (máx 2GB), cota de processamento (máx 1.5 CPUs) e limite de processos simultâneos.
2. **Teto de Buffer de Saída (128 KB):**
   * As saídas `stdout` e `stderr` retornadas no `content` da resposta MCP são repassadas 100% integrais para a LLM até o limite de 128 KB (~3.000 linhas de texto).
   * Se um comando exceder 128 KB, o excesso é truncado com mensagem explícita de alerta no payload MCP, impedindo estouro de memória no orquestrador.

### 3.5 Persistência, Fila e Cotação de Câmbio (`pipeline.db`)
* **Mecanismo de Armazenamento:** SQLite local configurado obrigatoriamente em Modo WAL (Write-Ahead Logging) para permitir leituras e escritas simultâneas com altíssima velocidade.
* **Camada de Acesso a Dados:** SQLModel (unindo modelos Pydantic com SQLAlchemy Async) com controle de migrações automáticas via Alembic.
* **Cotação de Câmbio em Tempo Real:** No boot do servidor, o motor consulta a taxa de câmbio oficial do Dólar para Reais (USD/BRL) via API pública do Banco Central / AwesomeAPI, armazenando o valor em cache com renovação automática a cada 24 horas. Esse valor é utilizado para computar a conversão exata de custos em Reais.
* **Estrutura das Entidades da Fase 0:**
  * **Entidade `AgentMessage` (Protocolo Oficial de Mensagens):**
    * `id`: Identificador único (UUID v4).
    * `timestamp`: Carimbo de data e hora UTC.
    * `from_agent`: Identificador do agente emissor.
    * `to_agent`: Identificador do agente destinatário ou string `"broadcast"` para comunicação a toda a esteira.
    * `message_type`: Tipo validado contra o Enum oficial da esteira (`task_assignment`, `task_completed`, `improvement_request`, `qa_failure`, `pentest_report`, `status_update`, `escalation`, `metric_report`, `context_share`, `approval_request`, `approval_response`).
    * `priority`: Nível de prioridade (`critical`, `high`, `medium`, `low`).
    * `payload`: Corpo da mensagem estruturado em JSON.
    * `correlation_id`: Identificador opcional para encadeamento e rastreamento de threads de conversa.
    * `requires_ack`: Booleano indicando se a mensagem exige confirmação de recebimento.
    * `status`: Estado atual da mensagem (`pending`, `processing`, `completed`, `failed`).
  * **Entidade `AuditLog` (Rastreabilidade):** Identificador, data/hora, identificador da execução (`run_id`), agente responsável, tipo de ação (pensamento, chamada de ferramenta, retorno de ferramenta, resposta final) e conteúdo detalhado.
  * **Entidade `TokenMetric` (Telemetria Financeira):** Identificador, carimbo de data/hora, identificador da execução (`run_id`), agente executor, modelo de IA acionado, tokens de prompt (entrada), tokens de completion (saída), custo financeiro em Dólar (USD) e custo convertido em Reais (BRL) baseado na cotação real apurada no dia.

---

## 4. Matriz de Resiliência: Tratamento Especializado de Erros

Em conformidade com o princípio de que **cada erro é um erro**, o motor aplica tratamentos específicos para cada categoria:

### 4.1 Categoria 1: Erros de Infraestrutura & Limites da LLM (HTTP 429, 500, 503)
* **Regra de Rate Limit Inteligente:**
  1. **Inspeção de Contrato da API:** O motor inspeciona a resposta oficial da API do provedor em busca do cabeçalho oficial de espera (`retry-after`). Se presente e o valor for de até 30 segundos, o motor aguarda exatamente o tempo especificado pelo provedor antes de retentar.
  2. **Diferenciação de Cotas:**
     * Se o erro indicar esgotamento de cota diária ou saldo insuficiente (`insufficient_quota`), o tempo de espera é zero: o motor dispara **Fallback Imediato** para o provedor secundário (ex: Groq ou Claude).
     * Se for limite transitório por minuto (RPM/TPM) sem cabeçalho específico, aplica retentativas graduais respeitando teto máximo de espera.
  3. **Limite de Falha:** Se todas as retentativas e o fallback falharem, o motor pausa a execução com segurança, salva o estado no banco e notifica a interface com o erro de rede.

### 4.2 Categoria 2: Erros de Validação de Ferramentas (Argumentos Inválidos)
* **Regra de Auto-Correção (Self-Correction):**
  * O backend não interrompe o processo.
  * O erro de validação do esquema da ferramenta é encapsulado e devolvido à LLM como a observação do turno.
  * A LLM recebe a explicação do parâmetro que faltou ou que foi preenchido incorretamente e tem até 3 tentativas para reformular a chamada correta.

### 4.3 Categoria 3: Erros de Execução de Comandos (Exit Code != 0)
* **Regra de Transparência Integral:**
  * O motor repassa 100% das saídas de `stdout` e `stderr` (respeitando o teto de segurança de 128 KB) para o contexto da LLM, sem truncamentos artificiais.
  * O agente utiliza essas mensagens de erro do compilador ou dos testes como dado empírico para raciocinar sobre o próximo passo de correção.

### 4.4 Categoria 4: Esgotamento de Recursos / Loops (Circuit Breaker)
* **Regra de Interrupção Segura:**
  * Se o contador atingir o teto de 25 iterações sem que o agente termine a tarefa, o motor aciona o disjuntor (Circuit Breaker).
  * A execução é pausada, o estado é congelado no SQLite com status `PAUSED_CIRCUIT_BREAKER` e uma notificação de intervenção humana é gerada.

### 4.5 Recuperação de Falhas e Queda de Servidor (Crash Recovery no Boot)
* **Rotina de Inicialização:** Ao subir, antes de abrir as portas HTTP, o motor executa uma varredura nas mensagens e tarefas registradas no `pipeline.db`.
* **Tratamento de Tarefas Órfãs:** Qualquer execução que tenha permanecido com status `running` (indicando que o servidor caiu ou o terminal foi fechado durante uma iteração) é automaticamente atualizada para `INTERRUPTED_BY_CRASH`. O último snapshot é preservado para permitir auditoria ou reinício controlado sem risco de repetições cegas de comandos.

---

## 5. Estratégia de Testes e Homologação da Fase 0

### 5.1 Testes de Ponta a Ponta com Provedor Real:
* Os testes automatizados da Fase 0 não utilizarão dados simulados (mocks) para inferência; eles executam **diretamente contra a API ativa real do Google Gemini**.
* Isso assegura que a formatação de function calling, parsing de schemas e cálculo de tokens reflitam a resposta genuína de produção.

### 5.2 Critérios de Aceite Mandatórios:
1. O servidor FastAPI sobe e valida as chaves do `.env` no boot, recusando iniciar se faltar configuração essencial.
2. A rotina de câmbio consulta e valida a cotação real do Dólar no início da execução.
3. A rotina de crash recovery identifica e sinaliza corretamente tarefas interrompidas de sessões anteriores.
4. O endpoint `/api/v1/health` responde status OK com conectividade confirmada com a API e o banco de dados.
5. O disparo assíncrono via `POST /api/v1/agent/run` devolve `202 Accepted` imediatamente com `run_id`, e a consulta via `GET /api/v1/agent/run/{run_id}` reflete o progresso e resultado final.
6. O canal SSE transmite com precisão os eventos tipados (`thought`, `tool_call`, `tool_result`, `token_usage`, `task_completed`).
7. Um agente de homologação recebe a instrução de criar um arquivo no workspace, modificá-lo cirurgicamente via `patch_file` e listar a pasta via terminal em container Docker, concluindo a tarefa sozinho.
8. O sandbox em container Docker comprova isolamento completo do host, barrando qualquer tentativa de leitura fora da pasta montada.
9. O semáforo de concorrência respeita o valor de `MAX_CONCURRENT_AGENTS` do `.env`, enfileirando tarefas adicionais de forma ordenada.
10. As métricas reais de tokens devolvidas pela chamada ao Gemini são computadas e salvas na tabela `token_metrics` com os valores financeiros correspondentes em USD e BRL.
11. Os logs de sistema são gravados e rotacionados no arquivo `logs/engine.log`.


---

## 6. Matriz Completa de Cenários de Teste & Especificações BDD

Esta seção documenta a suíte exaustiva de testes de aceitação e conformidade do Motor de Agentes (Fase 0), servindo como guia mandatório para desenvolvimento via TDD (Test-Driven Development) e homologação com a API real do Gemini.

### 6.1 Seção A: Matriz Completa de Cenários de Teste

| ID | Dimensão | Módulo / Contexto | Cenário / Condição | Entrada / Parâmetros | Resultado Esperado | Prioridade |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **TC-001** | Happy Path | Boot & Config | Inicialização com `.env` íntegro e chaves válidas | Arquivo `.env` preenchido com `GEMINI_API_KEY`, `MAX_CONCURRENT_AGENTS=5`, banco `sqlite:///pipeline.db` | Servidor FastAPI sobe com sucesso na porta 8000, valida conexões e inicializa pool SQLite com WAL habilitado. | Alta |
| **TC-002** | Negative Testing | Boot & Config | Inicialização sem chave mandatória da LLM | Variável `GEMINI_API_KEY` ausente ou vazia no `.env` | Servidor recusa iniciar (exit code != 0), emitindo log de erro crítico indicando a variável ausente. | Alta |
| **TC-003** | Boundary / Edge | Boot & Config | Configuração de concorrência com valores anômalos | `MAX_CONCURRENT_AGENTS=0` ou valor negativo | Sistema rejeita valor inválido ou assume fallback seguro (default=1), alertando no log de inicialização. | Média |
| **TC-004** | Happy Path | Câmbio BRL | Consulta da taxa de câmbio USD/BRL no boot | Requisição inicial para AwesomeAPI / Banco Central | Cotação atual (ex: 5.80) é registrada na memória com timestamp e cache configurado para 24 horas. | Alta |
| **TC-005** | Resilience | Câmbio BRL | Falha de rede na consulta externa de câmbio | API de câmbio externa inacessível (HTTP 500 ou Timeout) | Sistema utiliza último valor persistido em cache ou fallback de contingência predefinido, sem travar o boot. | Média |
| **TC-006** | State / Lifecycle | Crash Recovery | Varredura de tarefas órfãs durante boot do motor | Banco contém runs com status `running` da sessão anterior | Motor identifica os registros, atualiza status para `INTERRUPTED_BY_CRASH` com timestamp de encerramento e preserva snapshots. | Alta |
| **TC-007** | Happy Path | Health Check | Consulta de integridade operacional do motor | Requisição `GET /api/v1/health` | HTTP 200 OK com payload detalhando status `healthy` do banco SQLite e conectividade com a API Gemini. | Alta |
| **TC-008** | Negative Testing | Health Check | Degradação de integridade por perda de conectividade | Banco SQLite corrompido ou API externa inacessível | HTTP 503 Service Unavailable com detalhamento do componente inoperante no corpo da resposta. | Alta |
| **TC-009** | Happy Path | Perfis de Agente | Carregamento de perfis YAML válidos em `config/agents/` | Arquivos `pipeline/minerador.yaml` e `council/ceo.yaml` íntegros | Perfis instanciados corretamente na memória com nome, modelo, temperatura e ferramentas mapeadas. | Alta |
| **TC-010** | Negative Testing | Perfis de Agente | Perfil YAML com schema malformatado | Arquivo YAML com sintaxe inválida ou campos obrigatórios ausentes | Motor descarta o perfil inválido, registra log de aviso/erro e não disponibiliza o agente para execução. | Média |
| **TC-011** | Security | Perfis de Agente | Bloqueio de mutação nos perfis do Conselho | Chamada interna ou externa tentando editar arquivos em `config/agents/council/` | Operação estritamente bloqueada com erro de permissão. Somente arquivos em `pipeline/` aceitam edição autônoma. | Crítica |
| **TC-012** | Happy Path | Despacho Assíncrono | Envio de comando para agente existente | `POST /api/v1/agent/run` com `{"agent_id": "minerador", "prompt": "Pesquise leads", "workspace_id": "ws-01"}` | HTTP 202 Accepted retornado imediatamente contendo `run_id` UUID e status inicial `queued`. | Alta |
| **TC-013** | Negative Testing | Despacho Assíncrono | Envio de solicitação para `agent_id` inexistente | `POST /api/v1/agent/run` com `{"agent_id": "fantasma", "prompt": "teste"}` | HTTP 404 Not Found com mensagem de erro amigável informando agente não cadastrado. | Média |
| **TC-014** | Negative Testing | Despacho Assíncrono | Envio de payload inválido ou prompt vazio | `POST /api/v1/agent/run` com corpo `{}` ou `{"prompt": ""}` | HTTP 422 Unprocessable Entity detalhando os campos faltantes ou violados pelo schema de validação. | Média |
| **TC-015** | Boundary / Edge | Despacho Assíncrono | Prompt gigante excedendo o limite de caracteres aceito | `POST /api/v1/agent/run` com prompt de tamanho extremo (> 100k caracteres) | HTTP 413 Payload Too Large ou HTTP 422 indicando superação do comprimento máximo aceito no gateway de entrada. | Média |
| **TC-016** | Happy Path | Consulta de Run | Consulta de status de execução válida em andamento | `GET /api/v1/agent/run/{run_id}` | HTTP 200 com JSON contendo `run_id`, status atual (`running`), progresso de iterações e métricas acumuladas. | Alta |
| **TC-017** | Negative Testing | Consulta de Run | Consulta de `run_id` inexistente ou inválido | `GET /api/v1/agent/run/00000000-0000-0000-0000-000000000000` | HTTP 404 Not Found com código de erro padronizado. | Baixa |
| **TC-018** | Happy Path | SSE Stream | Assinatura e consumo de eventos em tempo real | Conexão HTTP `GET /api/v1/events/stream` com Header `Accept: text/event-stream` | Conexão mantida aberta (streaming), emitindo eventos estruturados e tipados (`thought`, `tool_call`, `tool_result`, etc.). | Alta |
| **TC-019** | Resilience | SSE Stream | Desconexão súbita do cliente leitor de SSE | Cliente fecha socket ou encerra conexão abruptamente durante o streaming | Motor trata a quebra de canal sem lançar exceções não tratadas e prossegue a execução do agente em background. | Média |
| **TC-020** | Happy Path | Reasoning Loop | Ciclo ReAct completo (Pensar -> Agir -> Observar -> Concluir) | Agente recebe instrução direta que demanda uso de ferramenta e responde conclusão | Agente emite pensamento, invoca ferramenta, recebe resultado via tool call real do Gemini e gera resposta final. | Alta |
| **TC-021** | Boundary / Edge | Reasoning Loop | Esgotamento do limite máximo de passos (`max_steps`) | Tarefa em loop infinito ou sem convergência atingindo o teto de passos configurado (ex: 20 iterações) | Execução é encerrada com status `failed` / `max_steps_exceeded`, registrando erro explicativo sem travar o motor. | Alta |
| **TC-022** | Happy Path | Tool: `read_file` | Leitura de arquivo existente no workspace | `path="src/index.js"` dentro do diretório do workspace | Conteúdo textual do arquivo retornado com sucesso para a LLM. | Alta |
| **TC-023** | Negative Testing | Tool: `read_file` | Tentativa de leitura de arquivo inexistente | `path="src/nao_existe.txt"` | Ferramenta retorna mensagem de erro explicativa ("File not found"), permitindo que a LLM tome ação corretiva. | Média |
| **TC-024** | Security | Tool: `read_file` | Tentativa de Path Traversal para fora do workspace | `path="../../../../../etc/passwd"` ou caminhos absolutos de sistema | Acesso sumariamente negado com erro de segurança; caminho restrito estritamente à raiz do workspace do cliente. | Crítica |
| **TC-025** | Happy Path | Tool: `write_file` | Criação de novo arquivo com diretórios aninhados | `path="docs/specs/api.md"`, `content="# Title"` (diretório pai ainda não criado) | Diretórios intermediários criados automaticamente e arquivo gravado com o conteúdo especificado. | Alta |
| **TC-026** | Happy Path | Tool: `write_file` | Sobrescrita de arquivo existente | `path="docs/specs/api.md"`, `content="# Novo Conteudo"`, `overwrite=True` | Conteúdo do arquivo é totalmente substituído pelo novo texto sem corrupção. | Alta |
| **TC-027** | Happy Path | Tool: `patch_file` | Edição cirúrgica de bloco de código único | `path="main.py"`, `target="def old(): pass"`, `replacement="def new(): return True"` | Apenas o bloco especificado é substituído; restante do arquivo preservado caractere por caractere. | Alta |
| **TC-028** | Negative Testing | Tool: `patch_file` | Bloco `target` não localizado no arquivo | `path="main.py"`, `target="trecho inexistente"`, `replacement="..."` | Operação abortada com erro amigável ("Target block not found"); arquivo original permanece 100% inalterado. | Alta |
| **TC-029** | Boundary / Edge | Tool: `patch_file` | Múltiplas ocorrências do bloco `target` sem especificação de índice | `path="main.py"`, `target="x = 1"` presente 3 vezes no mesmo arquivo | Ferramenta rejeita ou alerta ambiguidade se exigida unicidade, evitando substituições acidentais indesejadas. | Média |
| **TC-030** | Happy Path | Tool: `list_directory` | Listagem de conteúdo de subpasta do workspace | `path="src"` | Retorna array estruturado de itens contendo nomes, tipos (arquivo/pasta) e tamanhos relativos. | Média |
| **TC-031** | Happy Path | Tool: `run_command` | Execução de comando bash determinístico no container | `command="node --version"` | Comando é executado dentro do container isolado; stdout retorna a versão do Node com exit code 0. | Alta |
| **TC-032** | Negative Testing | Tool: `run_command` | Execução de comando com erro de sintaxe ou falha | `command="ls --opcao-invalida"` | Retorna stderr completo, stdout e exit code diferente de zero (ex: 2) para a LLM contextualizar. | Média |
| **TC-033** | Boundary / Edge | Tool: `run_command` | Saída volumosa excedendo o limite de buffer de 128 KB | `command="yes 'linha de teste longa' | head -n 100000"` | Saída truncada com segurança exatamente no teto de 128 KB com sufixo indicando número de linhas e bytes cortados. | Alta |
| **TC-034** | Resilience | Tool: `run_command` | Comando travado ou em loop infinito (Timeout) | `command="sleep 120"` com limite de timeout definido em 30 segundos | Container ou processo recebe `SIGKILL` após 30 segundos; ferramenta retorna erro de timeout sem prender a thread. | Alta |
| **TC-035** | Security | Sandbox Docker | Tentativa de escalação de privilégios ou acesso ao Docker Host | `command="cat /etc/shadow"` ou manipulação de `/proc` | Permissão negada; usuário do container sem privilégios de root e sem acesso ao socket `/var/run/docker.sock`. | Crítica |
| **TC-036** | Concurrency | Fila de Agentes | Concorrência máxima atingida (`MAX_CONCURRENT_AGENTS`) | 6 solicitações simultâneas de execução quando o limite configurado é 5 | 5 agentes iniciam execução ativa; a 6ª solicitação permanece enfileirada (`queued`) e é executada assim que um slot é liberado. | Alta |
| **TC-037** | Concurrency | Integridade DB | Gravações concorrentes de métricas e estados de múltiplos agentes | Vários agentes disparando escritas simultâneas de eventos no banco SQLite | Todas as escritas são serializadas com sucesso pelo modo WAL sem erros de `database is locked`. | Alta |
| **TC-038** | Happy Path | Métricas & Custos | Extração de tokens reais e precificação precisa | Resposta da API Gemini contendo `prompt_token_count`, `cached_content_token_count` e `candidates_token_count` | Extrai valores brutos de `_hidden_params["original_response"]`, calcula custo em USD pela tabela e converte para BRL via cotação em cache. | Alta |
| **TC-039** | Happy Path | Métricas & Custos | Persistência na tabela `token_metrics` | Fim de cada turno de inferência | Linha inserida no SQLite com `run_id`, `agent_name`, contagens exatas de tokens, `cost_usd` e `cost_brl` devidamente indexados. | Alta |
| **TC-040** | State / Lifecycle | Rotação de Logs | Escrita e rotação contínua de logs do motor | Registro intensivo de logs no arquivo `logs/engine.log` | Logs formatados sem dados sensíveis (sem chaves de API); rotação ocorre ao atingir o limite estipulado (ex: 10MB) gerando backups compactados. | Média |

---

### 6.2 Seção B: Cenários Críticos em Formato BDD (Gherkin)

Abaixo estão formalizados os cenários de maior criticidade e risco operacional da Fase 0.

#### BDD-01: Inicialização do Motor e Validação de Ambiente (TC-001 & TC-002)
```gherkin
Funcionalidade: Inicialização e Verificação de Sanidade do Motor
  Como operador da esteira autônoma
  Quero que o motor valide todas as variáveis obrigatórias e dependências no boot
  Para garantir que nenhuma execução seja iniciada sem condições operacionais

  Cenário: Inicialização bem-sucedida com ambiente completo
    Dado que o arquivo ".env" contém "GEMINI_API_KEY" preenchida com uma chave válida
    E a variável "MAX_CONCURRENT_AGENTS" está configurada como 5
    E o banco SQLite "pipeline.db" está acessível com suporte a WAL
    Quando o serviço do motor de agentes é inicializado
    Então o servidor FastAPI deve vincular a porta 8000 com sucesso
    E a rotina de câmbio deve obter a cotação do Dólar e registrá-la em cache
    E o log de inicialização deve registrar o status "READY"

  Cenário: Bloqueio de inicialização por ausência de chave de API
    Dado que o arquivo ".env" não contém o parâmetro "GEMINI_API_KEY"
    Quando o serviço do motor de agentes tenta ser inicializado
    Então o processo deve ser interrompido imediatamente com código de encerramento diferente de zero
    E o arquivo "logs/engine.log" deve conter uma mensagem de erro indicando "CRITICAL: Missing GEMINI_API_KEY"
```

#### BDD-02: Recuperação de Falhas e Queda de Servidor (TC-006)
```gherkin
Funcionalidade: Crash Recovery de Tarefas Órfãs no Boot
  Como arquiteto do sistema
  Quero que execuções pendentes de sessões que sofreram queda sejam identificadas
  Para evitar duplicidade cega de comandos e estados inconsistentes

  Cenário: Atualização de tarefas órfãs durante o boot do motor
    Dado que o banco de dados contém uma execução com "run_id" "run-abc-123" e status "running"
    E a última atualização ocorreu antes da queda do servidor anterior
    Quando o motor de agentes inicia sua rotina de boot
    Então a varredura inicial do banco deve localizar a execução "run-abc-123"
    E o status dessa execução deve ser alterado para "INTERRUPTED_BY_CRASH"
    E o snapshot e histórico de eventos anteriores devem permanecer preservados para auditoria
```

#### BDD-03: Despacho Assíncrono e Consulta de Status (TC-012 & TC-016)
```gherkin
Funcionalidade: Despacho Assíncrono de Execução de Agente
  Como cliente da API do motor
  Quero disparar uma instrução e receber um identificador imediato
  Para acompanhar o ciclo de vida da execução sem travar a requisição HTTP

  Cenário: Submissão de execução válida aceita pelo motor
    Dado que o agente "minerador" está cadastrado com perfil válido
    Quando uma requisição POST é enviada para "/api/v1/agent/run" com o corpo:
      """
      {
        "agent_id": "minerador",
        "prompt": "Pesquise leads do segmento de odontologia em Curitiba",
        "workspace_id": "ws-client-curitiba"
      }
      """
    Então o código de resposta HTTP deve ser 202 Accepted
    E o corpo da resposta deve conter um "run_id" em formato UUID
    E o status inicial retornado no payload deve ser "queued" ou "running"
    E a tarefa em background deve ser despachada para o semáforo de concorrência

  Cenário: Consulta do status de uma execução em andamento
    Dado que existe uma execução com "run_id" "d9f8b4a2-1111-4b1a-9876-000000000001" em processamento
    Quando uma requisição GET é enviada para "/api/v1/agent/run/d9f8b4a2-1111-4b1a-9876-000000000001"
    Então o código de resposta HTTP deve ser 200 OK
    E o JSON deve conter o status "running", iteração atual e contadores de tokens parciais
```

#### BDD-04: Transmissão de Eventos em Tempo Real via SSE (TC-018 & TC-019)
```gherkin
Funcionalidade: Streaming de Eventos via Server-Sent Events (SSE)
  Como interface cliente ou cockpit
  Quero assinar o feed de eventos de uma execução
  Para exibir o fluxo de pensamento, chamadas de ferramentas e progresso em tempo real

  Cenário: Recebimento contínuo de eventos tipados do ciclo de vida
    Dado que uma execução de agente está ativa com múltiplas iterações
    Quando um cliente conecta com requisição GET em "/api/v1/events/stream?run_id=d9f8b4a2"
    E envia o cabeçalho "Accept: text/event-stream"
    Então a resposta HTTP deve retornar status 200 com "Content-Type: text/event-stream"
    E os pacotes recebidos devem incluir eventos tipados como "thought", "tool_call", "tool_result" e "token_usage"
    E ao finalizar a execução o fluxo deve emitir o evento final "task_completed"

  Cenário: Resiliência contra desconexão abrupta do cliente leitor
    Dado que o cliente está recebendo dados via SSE de uma execução em andamento
    Quando a conexão HTTP é interrompida pelo cliente sem handshake de encerramento
    Então o motor deve capturar o encerramento do socket sem gerar erro não tratado no servidor
    E a execução do agente em background deve continuar normalmente até sua conclusão
```

#### BDD-05: Isolamento de Segurança e Path Traversal nas Ferramentas (TC-024 & TC-035)
```gherkin
Funcionalidade: Segurança, Confinamento de Diretório e Sandbox Docker
  Como mantenedor da infraestrutura
  Quero que todas as ferramentas do agente operem exclusivamente dentro do workspace designado
  Para evitar vazamento de segredos do host, contaminação do servidor ou acesso indevido

  Cenário: Bloqueio de leitura de arquivo fora dos limites do workspace
    Dado que o agente possui um workspace isolado em "/workspaces/clients/cliente-alpha"
    Quando a LLM invoca a ferramenta "read_file" com o parâmetro "path=../../../../etc/passwd"
    Então a ferramenta deve interceptar e rejeitar a solicitação
    E a ferramenta deve retornar uma mensagem de erro indicando "Access denied: Path escapes workspace root"
    E o conteúdo do arquivo externo jamais deve ser transmitido para a LLM

  Cenário: Isolamento total no comando bash via container descartável
    Dado que o agente precisa executar um comando de instalação ou compilação
    Quando a ferramenta "run_command" é invocada com o comando "cat /etc/shadow"
    Então o comando deve ser executado no container descartável sem privilégios de superusuário
    E a saída deve retornar código de erro com mensagem de "Permission denied"
    E nenhuma pasta do sistema operacional hospedeiro fora do workspace montado deve ser visível no container
```

#### BDD-06: Edição Cirúrgica de Código via patch_file (TC-027 & TC-028)
```gherkin
Funcionalidade: Edição Cirúrgica de Arquivos via patch_file
  Como arquiteto da esteira de desenvolvimento
  Quero que o agente substitua blocos específicos de código sem reescrever o arquivo inteiro
  Para economizar até 90% dos tokens de saída e prevenir alucinações acidentais

  Cenário: Substituição exata de trecho com correspondência única
    Dado que existe um arquivo "app/services.py" no workspace contendo o bloco:
      """
      def calcular_taxa(valor):
          return valor * 0.05
      """
    Quando o agente aciona a ferramenta "patch_file" com:
      | path        | target                                       | replacement                                   |
      | app/services.py | def calcular_taxa(valor):\n    return valor * 0.05 | def calcular_taxa(valor):\n    return valor * 0.10 |
    Então o arquivo "app/services.py" deve ter apenas esse método modificado
    E as demais linhas e imports do arquivo devem permanecer exatamente idênticos
    E a ferramenta deve retornar sucesso na operação com a contagem de linhas afetadas

  Cenário: Aborto seguro quando o bloco de busca não é localizado
    Dado que o arquivo "app/services.py" não contém o trecho exato informado no parâmetro "target"
    Quando o agente tenta aplicar a ferramenta "patch_file"
    Então a modificação deve ser rejeitada
    E a ferramenta deve responder erro claro informando que o trecho de destino não foi localizado
    E o arquivo original não deve sofrer alteração em nenhum de seus bytes
```

#### BDD-07: Proteção de Buffer e Timeout no Terminal Docker (TC-033 & TC-034)
```gherkin
Funcionalidade: Governança de Buffer e Proteção de Timeout no Terminal
  Como administrador da infraestrutura
  Quero limitar o volume de saída e o tempo máximo de cada comando bash
  Para evitar travamento de memória do servidor e bloqueio por processos infinitos

  Cenário: Truncamento automático de saída de log gigantesca (buffer > 128 KB)
    Dado que um comando em execução gera 500 KB de dados em stdout
    Quando o comando é processado pela ferramenta "run_command"
    Então a saída retornada para a LLM deve ser truncada exatamente em 128 KB (~3.000 linhas)
    E deve ser anexado ao final um rodapé indicando:
      "[AVISO: Saída truncada em 128 KB para preservar a memória do motor. Restante omitido.]"
    E o motor não deve sofrer degradação ou estouro de memória (Out Of Memory)

  Cenário: Encerramento forçado por excesso de tempo de execução
    Dado que o limite de timeout para comandos bash no container está estipulado em 30 segundos
    Quando a ferramenta "run_command" executa uma rotina bloqueante que excede 30 segundos
    Então o container/processo deve receber o sinal "SIGKILL" imediatamente ao atingir o trigésimo segundo
    E a ferramenta deve retornar uma mensagem de erro indicando "Command timed out after 30 seconds"
```

#### BDD-08: Concorrência e Enfileiramento com Semáforo Assíncrono (TC-036)
```gherkin
Funcionalidade: Limite de Concorrência de Agentes e Enfileiramento
  Como operador da esteira
  Quero controlar a quantidade máxima de agentes executando simultaneamente
  Para manter o consumo de CPU, RAM e limites de requisição da LLM sob controle

  Cenário: Enfileiramento e liberação ordenada de vagas no semáforo
    Dado que o limite "MAX_CONCURRENT_AGENTS" está configurado como 5
    E exatamente 5 agentes já estão em status "running" executando tarefas
    Quando uma 6ª solicitação de execução chega via API
    Então a 6ª solicitação deve ser aceita com status "queued"
    E essa execução deve aguardar no semáforo assíncrono sem iniciar inferências
    Quando uma das 5 tarefas ativas é concluída e libera sua vaga
    Então a 6ª solicitação deve transicionar automaticamente para status "running" e iniciar seu processamento
```

#### BDD-09: Contabilização Financeira e Métrica de Tokens Reais (TC-038 & TC-039)
```gherkin
Funcionalidade: Auditoria Precisa de Tokens e Custos em Moeda Dupla (USD e BRL)
  Como diretor financeiro (CFO) da agência
  Quero que cada inferência registre a quantidade real de tokens cobrados e o valor em Reais
  Para acompanhar a margem de lucro e custo operacional de cada cliente em tempo real

  Cenário: Processamento e gravação de custos de uma chamada ao Gemini
    Dado que uma chamada de inferência ao modelo "gemini-2.5-flash" foi concluída
    E a resposta nativa do provedor informou:
      | prompt_token_count | cached_content_token_count | candidates_token_count |
      | 1500               | 1000                       | 350                    |
    E a cotação do Dólar registrada no cache é de R$ 5,80
    Quando a resposta é interceptada pelo extrator de métricas
    Então o custo em USD deve ser calculado aplicando a tabela de preços oficial sobre cada tipo de token
    E o custo em BRL deve ser calculado multiplicando o total em USD pela taxa de R$ 5,80
    E uma nova linha deve ser persistida na tabela "token_metrics" contendo "run_id", "agent_name", as contagens de tokens, "cost_usd" e "cost_brl"
```

#### BDD-10: Governança dos Arquivos do Conselho vs Esteira (TC-011)
```gherkin
Funcionalidade: Imutabilidade Estrita do Conselho e Flexibilidade da Esteira
  Como fundador e proprietário da software house
  Quero garantir que a IA jamais altere os arquivos do Conselho C-Suite
  Para manter a soberania das diretrizes e regras estratégicas de negócio

  Cenário: Tentativa de modificação em diretório restrito do Conselho
    Dado que um agente da esteira ou rotina autônoma tenta executar um comando ou ferramenta de escrita
    Quando o caminho de destino está localizado em "config/agents/council/"
    Então a operação deve ser categoricamente bloqueada pelo motor
    E deve ser disparado um evento de alerta de segurança no log do sistema
    E nenhum arquivo da diretoria C-Suite deve ser modificado

  Cenário: Modificação permitida em diretório evoluível da esteira operacional
    Dado que o Conselho aprovou uma melhoria de prompt ou parâmetros para um agente operacional
    Quando a ferramenta de escrita é acionada para alterar um arquivo em "config/agents/pipeline/"
    Então a modificação deve ser validada contra o schema do agente
    E a atualização deve ser concluída e versionada com sucesso
```
