# 🚀 The Agency: Software House Autônoma Standalone

> **Liderança & Decisor Supremo:** João (Chefe — *"A Palavra do Chefe é Sempre Lei"*)  
> **Comitê de Direção:** C-Suite de 4 Agentes Executivos de IA (CEO, CTO, CRO, COO)  
> **Arquitetura Técnica:** Opção A — Polyglot (Python Core + Node.js WhatsApp + Next.js Cockpit)  
> **Premissa Inviolável:** Sistema 100% autônomo, rodando de forma independente de qualquer IDE ou plugin.  
> **Diretriz Geral de Planejamento:** Todos os documentos e especificações contêm estritamente arquitetura, regras de negócio e contratos conceituais (zero código-fonte nos arquivos de roadmap, ficando a implementação a cargo dos desenvolvedores em cada fase).

---

## 🏗️ Estrutura do Repositório (Topologia de Microsserviços)

```text
the-agency/
├── services/
│   ├── engine/              # Orquestrador Central de Agentes (FastAPI :8000)
│   ├── whatsapp/            # WhatsApp Gateway & MCP Server (Node.js Baileys :3005)
│   ├── payment/             # Payment Gateway Banco Inter mTLS & MCP Server (FastAPI :3006)
│   ├── guardrail/           # Ingress Guardrail Groq LPU + Whisper (FastAPI :3007)
│   ├── telegram/            # Bot Telegram Bidirecional & MCP Server (FastAPI :3008)
│   ├── scraper/             # OSINT & Web Research MCP Server (SearXNG + ruyijs + Scraper Kit :3009)
│   ├── sandbox/             # Workspace Filesystem & Docker Execution MCP Server (:3010)
│   ├── git/                 # Git & GitHub VCS MCP Server (FastAPI :3011)
│   ├── deploy/              # Cloud & Deploy MCP Server Vercel/Supabase (FastAPI :3012)
│   ├── memory/              # Knowledge, Memory & CRAG MCP Server (Qdrant + BGE :3013)
│   ├── browser/             # Browser Automation & Playwright MCP Server (FastAPI :3014)
│   └── security/            # Security Audit & Code Quality MCP Server (FastAPI :3015)
├── apps/
│   └── cockpit/             # Painel de Comando Web de João (Next.js 15 / Tailwind :3000)
├── workspaces/              # Sandboxes isolados onde os projetos de clientes são programados
│   └── clients/             # /home/joao/projetos/<client-slug>/
├── database/                # SQLite local (pipeline.db) + Migrações
├── knowledge/               # Knowledge-as-Code: Playbooks Markdown (dev, sales, qa, c_suite)
└── docs/                    # Especificações e Documentação Técnica Detalhada
```

---

# 🗺️ Roadmap Arquitetural Oficial por Fases

Abaixo está o roteiro completo de planejamento e implementação, dividido em 7 fases sequenciais.

---

## FASE 0: Fundação Arquitetural & O Motor de Agentes (Python Core)

O objetivo desta fase é construir o runtime independente que permite aos agentes raciocinarem, executarem ferramentas em sandbox Docker, trocarem mensagens e persistirem seu estado (especificação soberana detalhada em `docs/fase-0-motor-agentes.md`).

* **0.1 Estrutura do Backend & Setup Python:**
  * Configuração do ambiente virtual Python 3.12+ (`uv` ou `poetry` para máxima performance).
  * Setup do FastAPI assíncrono expondo endpoints locais (`POST /agent/run` em 202 com `run_id`, `GET /agent/run/{run_id}`) e Server-Sent Events (SSE).
  * Roteador de modelos via LiteLLM com extração do payload bruto do Gemini (garantindo telemetria exata ao centavo) e fallback para Groq.
  * Validação de configuração no boot com `pydantic-settings` (.env fail-fast) e logs rotacionados com Loguru.
* **0.2 O Agent Runner ReAct (O Loop do Agente Individual):**
  * Classe base em Python que executa o ciclo ReAct determinístico assíncrono com perfis desacoplados em arquivos YAML/Markdown.
  * Controle estrito de teto de iterações (`max_iterations = 25`) com Circuit Breaker de interrupção segura.
* **0.3 O MCP Client Host & Workspace MCP Server (`:3010`):**
  * Diretrizes soberanas: todas as ferramentas operam obrigatoriamente como **Servidores MCP (Model Context Protocol)** desacoplados via JSON-RPC 2.0 (transporte SSE/HTTP).
  * O orquestrador central (`engine-core` na porta `:8000`) atua como **MCP Client (Host)**, descobrindo ferramentas dinamicamente via `tools/list` e despachando execuções via `tools/call`.
  * O `workspace-sandbox-service` (`:3010`) opera como servidor MCP nativo expondo `read_file`, `write_file`, `patch_file`, `list_directory` e `run_terminal_command` isolado em Containers Docker descartáveis (`node:20-slim`), montando exclusivamente a pasta do workspace com teto de buffer de 128 KB.
* **0.4 O Message Bus & State Store Durável (SQLite WAL Mode):**
  * Tabelas de infraestrutura básica: `agent_messages` (fila assíncrona), `audit_logs` (rastreabilidade de pensamentos e tools) e `token_metrics` (custo financeiro).
  * Concorrência via semáforo assíncrono (pool de 3 a 5 agentes simultâneos) e rotina de Crash Recovery no boot identificando tarefas órfãs.
* **0.5 Telemetria Financeira de Tokens:**
  * Registro detalhado em banco do consumo real de tokens (prompt, completion e cache) e conversão automática para custos em Dólar e Reais.

---

## FASE 1: Suíte de Microsserviços e Ferramentas MCP (A Caixa 100% Fechada)

Criação e padronização de todos os sentidos, braços operacionais e ferramentas de execução da esteira sob o protocolo aberto MCP (especificação soberana detalhada em `docs/fase-1-gateways-mensageria.md`).

* **1.1 WhatsApp Gateway & MCP Server (Node.js / Baileys `:3005`):**
  * Microsserviço independente rodando em Node.js com reconexão automática e sessão Multi-Device (`storage/whatsapp/auth_info/`).
  * Expõe **Servidor MCP via SSE** com ferramentas: `send_whatsapp_message`, `send_whatsapp_media`, `check_whatsapp_numbers` e `get_whatsapp_session_status`.
  * Módulo `humanizer` completo com simulação de leitura (`read receipts`), delay inicial (3s a 8s), digitação proporcional (30ms/char) e janela de horário comercial.
* **1.2 Ingress Guardrail & Transcrição Microservice (`:3007`):**
  * Microsserviço independente executando inspeção em ultra-baixa latência (<150ms via Groq LPU Llama Guard 3).
  * Toda mensagem de cliente no WhatsApp é inspecionada antes de tocar o orquestrador central.
  * Transcrição instantânea de mensagens de voz (.ogg) recebidas de clientes via Groq Whisper (`whisper-large-v3`) em <500ms.
  * Bloqueio silencioso de prompt injection, jailbreaks e comandos maliciosos, com registro em `security_incidents` e alerta direto para o Telegram de João.
* **1.3 OSINT & Web Research MCP Server (`:3009`):**
  * Mineração comercial baseada no **`google-maps-scraper-kit`** com automação leve via Chrome DevTools Protocol (CDP) e grid search a custo zero (R$ 0,00).
  * Pesquisa web autônoma e inteligência de mercado via **SearXNG** (meta-buscador open-source agregando 70+ provedores).
  * Leitura e extração de conteúdo com bypass anti-bot via **`ruyijs`** (SpiderMonkey C++) e limpeza de boilerplate para Markdown limpo via **`Trafilatura`** (<45MB RAM).
  * Expõe **Servidor MCP via SSE** com ferramentas: `scrape_google_maps`, `enrich_lead_profile`, `search_web`, `fetch_page_markdown`, `scrape_social_profile` (cookies/perfis) e `deep_research`.
  * Validação ativa prévia de existência de WhatsApp via chamada ao `whatsapp-gateway` (`:3005`) e deduplicação no banco de dados.
* **1.4 Payment Gateway & MCP Server (Banco Inter API `:3006`):**
  * Microsserviço dedicado isolado em Python FastAPI na porta `:3006` com mTLS nativo (certificados `.crt` e `.key` em pasta restrita).
  * Expõe **Servidor MCP via SSE** com ferramentas: `create_pix_charge`, `get_pix_status`, `simulate_pix_payment`, `get_account_balance` e `get_billing_metrics`.
  * Consulta de saldo consolidado em tempo real e consolidação de faturamento via API Banking v2 (`extrato.read`).
  * Emissão de cobrança com PIX dinâmico (QR Code em Base64 + chave Copia e Cola) e webhook de confirmação instantânea.
* **1.5 Telegram Gateway & MCP Server (`:3008`):**
  * Microsserviço isolado para comunicação bidirecional com João: alertas de pagamentos, tentativas de invasão e quedas de sessão.
  * Expõe **Servidor MCP via SSE** com ferramentas: `send_telegram_alert` e `request_owner_approval`.
  * Comandos de controle rápido pelo celular (`/status`, `/pausar`, `/retomar`, `/aprovar <lead_id>`).
* **1.6 Git & GitHub VCS MCP Server (`:3011`):**
  * Microsserviço isolado para controle de versão local e remoto via GitHub API REST v3 (`GITHUB_TOKEN` confinado).
  * Expõe **Servidor MCP via SSE** com ferramentas: `git_init_repository`, `git_create_branch`, `git_commit` (Conventional Commits com assinatura granular por agente), `git_get_diff`, `github_create_repo` e `github_create_pull_request`.
* **1.7 Cloud & Deploy MCP Server (`:3012`):**
  * Microsserviço isolado integrando Vercel REST API e Supabase Management API.
  * Expõe **Servidor MCP via SSE** com ferramentas: `deploy_preview_demo` (demos comerciais livres com URLs públicas instantâneas), `deploy_production` (gate triplo estrito: 50%+50% PIX pago, QA 100% verde e auditoria de segurança limpa), `provision_database` (Postgres Supabase) e `set_project_env_vars`.
* **1.8 Knowledge, Memory & Corrective RAG (CRAG) MCP Server (`:3013`):**
  * Cérebro de memória técnica, playbooks e aprendizado contínuo sem dependência de abstrações lentas (sem Mem0).
  * Banco vetorial **Qdrant** em Docker (`:6333`) com isolamento multi-tenant por agente (`private`), agência (`shared`) e projeto (`project`).
  * Motor de embeddings local **FastEmbed** (ONNX Runtime em CPU, ~90MB RAM, BGE-M3 com suporte nativo a português e custo R$ 0,00).
  * Juiz discriminativo **BGE-Reranker-v2-M3** (BAAI - China) avaliando relevância em 15ms: respostas locais de alta confiança (`>= 0.80`) entregues em <25ms; baixa confiança (`< 0.50`) aciona fallback em tempo real para o SearXNG (`:3009`) com extração de *Knowledge Strips*.
  * Expõe **Servidor MCP via SSE** com ferramentas: `recall`, `remember`, `forget`, `ingest_document` e `get_project_context`.
  * Ingestão automatizada no boot via padrão **Knowledge-as-Code** (diretório raiz `knowledge/` fatiado semanticamente em <3s com validação de hashes MD5).
* **1.9 Browser Automation & Viewport Gateway (`:3014`):**
  * Microsserviço independente em Python com **Microsoft Playwright** rodando em container oficial com Chromium e Firefox headless isolados.
  * Expõe **Servidor MCP via SSE** com ferramentas: `browser_screenshot`, `browser_inspect_console`, `browser_interact` e `browser_run_e2e_tests`.
  * Atendimento multi-persona: CRO (screenshots fidedignos de demos para WhatsApp), QA (inspeção de erros de console/rede e suítes E2E), Designer (testes responsivos mobile 375x812 e desktop 1920x1080) e Dev (validação de renderização/hidratação).
  * Arquitetura de pooling de `BrowserContext` efêmero: inicialização em <30ms, consumo médio de apenas ~180MB RAM e isolamento total de cookies/cache por teste.
* **1.10 Security Audit & Code Quality MCP Server (`:3015`):**
  * Microsserviço independente em Python integrando suíte enterprise de 5 motores de segurança e qualidade.
  * Servidor oficial **SonarQube Community Edition** em Docker (`:9000`) com banco PostgreSQL (`:5432`) avaliando débitos técnicos, code smells, cobertura de testes e homologação de Quality Gates (`Passed` / `Failed`).
  * Ferramenta **Gitleaks** para Secret Scanning pré-commit/push impedindo vazamento de tokens e credenciais.
  * Ferramenta **Semgrep** para análise estática (SAST) semântica e regras OWASP Top 10 em < 3 segundos.
  * Ferramenta **Trivy / OSV-Scanner** para Software Composition Analysis (SCA) detectando CVEs ativas em dependências npm e python.
  * Ferramenta **Nuclei** para pentest dinâmico (DAST) em URLs efêmeras de preview na Vercel antes de produção.
  * Expõe **Servidor MCP via SSE** com ferramentas: `run_sonarqube_scan`, `scan_secrets`, `scan_sast_semgrep`, `scan_dependencies`, `run_dast_scan` e `get_security_gate_status`.
* **1.11 Orquestração, Observabilidade, Segurança & Backups:**
  * Docker Compose unificado com rede interna bridge `agency-network`, DNS interno e healthchecks com auto-restart e ordem estrita de boot (Infraestrutura -> Gateways -> Core).
  * Stack de observabilidade Grafana (`:3001`) + Loki (`:3100`) + Promtail coletando logs estruturados JSON de todos os 11 contêineres com dashboards pré-configurados.
  * Autenticação inter-serviços unificada via token secreto compartilhado `X-Agency-Key` em todos os endpoints REST e conexões MCP SSE.
  * Política Fail-Fast com Pausa Emergencial por queda de gateways críticos (`whatsapp`, `payment`, `guardrail`), Degradação Parcial Controlada (`telegram`) e Auto-Retomada automática a cada 5s ao recuperar status `healthy`.
  * Sandbox Docker efêmero via DooD (`/var/run/docker.sock`) garantindo isolamento sem privilégios root de DinD.
  * Rotina de backup atômico diário local às 03:00 com `sqlite3 VACUUM INTO` (sem locks no WAL) e snapshots nativos do Qdrant com política de retenção de 7 dias.

---

## FASE 2: O Comitê Executivo (C-Suite Board de 4 Agentes)

O cérebro estratégico da empresa, operando sob sua autoridade absoluta.

* **2.1 Personas & Diretrizes dos 4 Diretores (Pydantic Schemas):**
  * 👑 **CEO Agent:** Visão estratégica macro, foco em lucro líquido e sintetizador final de propostas.
  * 💻 **CTO Agent:** Excelência em arquitetura, auditoria de código e austeridade radical no gasto de tokens.
  * 📈 **CRO Agent:** Maximização de receita, precificação dinâmica e testes A/B de abordagem.
  * ⚙️ **COO Agent:** Monitoramento de tempo de ciclo, detecção de gargalos e gestão da telemetria da calibragem.
* **2.2 O Deliberation Engine (Grafos Cíclicos LangGraph):**
  * Orquestração de debate Round-Robin: CRO propõe ➔ CTO desafia os custos ➔ COO analisa a viabilidade ➔ CEO sintetiza o parecer.
* **2.3 Relatório de Proposta Padronizado:**
  * Geração automática do relatório com a **Matriz Comparativa Tripla Obrigatória** (Buy vs Host vs Build).
* **2.4 Cláusula Pétrea de Isolamento & Imutabilidade:**
  * Bloqueio estrutural: o Conselho não pode modificar seus próprios prompts, parâmetros ou modelos.

---

## FASE 3: Prospecção & Prototipação Comercial (Front-of-the-House)

A engrenagem comercial que atrai o lead e gera senso imediato de valor.

* **3.1 Mining Agent:**
  * Extração de ficha limpa do negócio: nome, nicho, dores nas avaliações, fotos de fachada e trabalhos reais.
  * Regras mandatórias de fidelidade ética e anti-racismo na seleção de imagens.
* **3.2 Demo Builder Agent:**
  * Montagem do protótipo interativo sob medida (bespoke) personalizado com a marca do lead.
  * Auditoria pré-voo headless (Playwright) verificando que o site retorna HTTP 200 e todas as imagens carregam sem erro 404.
  * Deploy instantâneo na Vercel e devolução da URL ativa.
* **3.3 Sales Executive Agent:**
  * Condução da conversa no WhatsApp com metodologia SPIN Selling e técnicas de negociação de Chris Voss.
  * Apresentação da demo pronta como isca irresistível de alto valor.
* **3.4 Optimization Agent:**
  * Análise de perdas e recusas no funil para ajuste contínuo de ganchos e catálogos.

---

## FASE 4: Fábrica de Software & Blindagem Cibernética (Back-of-the-House)

A equipe técnica que projeta, programa, testa e faz o pentest do software contratado.

* **4.1 PO Agent (Product Owner):**
  * Estruturação do escopo fechado, histórias de usuário e critérios de aceitação.
  * Trava de segurança: a engenharia só inicia após a confirmação financeira do sinal de 50% via PIX.
* **4.2 Architect Agent:**
  * Criação do repositório Git em `/workspaces/clients/<client-slug>/`.
  * Desenho da Clean Architecture (Next.js 15 App Router, Supabase, Drizzle ORM, Zod schemas).
  * Documentação `ARCHITECTURE.md` e decomposição de tarefas atômicas.
* **4.3 Dev Team Agents:**
  * Subagentes especializados (Database/Supabase, Backend/Use-cases, Frontend/UI).
  * Geração de código com tipagem estrita TypeScript e commits atômicos convencionais.
* **4.4 QA Agent:**
  * Execução autônoma de testes unitários, de integração e E2E (Playwright) no sandbox do cliente.
  * Gate Mandatório: reprovação sumária se a cobertura for inferior a 80% ou se houver testes instáveis.
* **4.5 Security Agent:**
  * Auditoria estática (SAST com Semgrep, Secret Scanning com Gitleaks).
  * Pentest dinâmico ativo em staging (Nuclei, Schemathesis, OWASP ZAP).
* **4.6 Autonomous Self-Healing Loop:**
  * Se QA ou Security encontrarem falhas, emitem um `improvement_request` estruturado para o Dev Team.
  * O Dev Team corrige e notifica para re-teste automático até atingir 100% verde.

---

## FASE 5: Homologação, Entrega & Suporte (Handover)

A validação final pelo cliente, liquidação financeira e pós-venda.

* **5.1 Homologação Guiada com o Cliente:**
  * O PO envia o link de staging para o cliente no WhatsApp com roteiro de testes guiado.
  * Caso o cliente peça ajustes, o PO aciona o loop de refinamento com o time técnico.
* **5.2 Liquidação Financeira Final:**
  * Homologação aprovada pelo cliente ➔ Emissão do PIX dos 50% restantes.
* **5.3 Deploy de Produção & Handover:**
  * Deploy definitivo com domínio próprio e SSL ativo.
  * Entrega do repositório Git limpo e sem lock-in para o cliente.
* **5.4 Sustaining Engineering Agent:**
  * Ativação da garantia gratuita incondicional de 3 meses (90 dias de suporte a bugs).
  * Acompanhamento de NPS e funil de conversão para o plano mensal (MRR).

---

## FASE 6: O Cockpit de Comando (A Torre de Controle de João)

A interface gráfica web local (`http://localhost:3000`) para você pilotar toda a operação.

* **6.1 Dashboard Executivo:**
  * Saldo real em caixa, faturamento por nicho, margem líquida e contador de tokens por modelo.
* **6.2 Kanban Interativo com Modo de Calibragem:**
  * Visão clara de todos os leads por coluna.
  * **Pausas Assistidas por Etapa:** Botões para você inspecionar dados minerados, ver a demo, aprovar a copy do WhatsApp ou autorizar deploys.
* **6.3 WhatsApp Inbox com Copilot:**
  * Chat em tempo real conectado ao Baileys. A IA redige a sugestão de resposta; você pode editar ou enviar com 1 clique.
* **6.4 A Mesa Redonda do C-Suite:**
  * Chat multilateral onde você debate com o CEO (👑), CTO (💻), CRO (📈) e COO (⚙️), além de abas 1-a-1.
* **6.5 Centro de Governança de IA:**
  * Painel onde você calibra os modelos LLM, temperaturas e diretrizes de cada agente do Conselho.
