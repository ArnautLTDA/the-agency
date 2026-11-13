# Análise Completa: Fase 1 — Gateways & Mensageria

## Veredito Geral

> [!IMPORTANT]
> O documento da Fase 1 é **excepcionalmente detalhado e maduro**. Está num nível de prontidão muito alto para desenvolvimento. Os contratos MCP, schemas de banco, cenários de teste BDD e topologia de portas estão todos bem definidos. Existem, porém, pontas soltas e inconsistências que devem ser resolvidas antes de iniciar a implementação.

---

## 1. Aderência à Ideia Original (especificacao-esteira.md)

A especificação original e o roadmap são versões anteriores da visão que evoluiu bastante. A Fase 1 é **aderente à essência**, mas com refinamentos significativos que representam maturação da ideia:

### Evoluções Positivas (Refinamentos Bem-Vindos)

| Aspecto | Especificação Original | Fase 1 (Refinada) | Avaliação |
|:---|:---|:---|:---|
| **Protocolo de Ferramentas** | "Serviços compartilhados" genéricos com REST | MCP (Model Context Protocol) via JSON-RPC 2.0 + SSE | Excelente evolução. Padroniza tudo. |
| **Scraper** | Motor Go compilado na porta `:8080` | Python + `google-maps-scraper-kit` (CDP) na `:3009` | Mudança de tech stack justificada. |
| **Browser** | OpenCLI / Chrome genérico | Playwright oficial com context pooling | Muito mais robusto. |
| **Payment** | Asaas / Mercado Pago (taxa %) | Banco Inter com mTLS direto | Eliminação de intermediário = mais margem. |
| **Memória** | Não existia na especificação original | Knowledge-Memory-Gateway com CRAG + Qdrant + BGE | Adição crítica e bem arquitetada. |
| **Guardrail** | Inline no WhatsApp Gateway | Microsserviço dedicado `:3007` com Groq LPU | Desacoplamento correto. |
| **Observabilidade** | Não especificada | Grafana + Loki + Promtail | Adição essencial para operação. |
| **Git/Deploy** | Genéricos na especificação | Microsserviços MCP dedicados (`:3011`, `:3012`) | Governança muito mais granular. |

### Inconsistências com a Especificação Original

> [!WARNING]
> Estas mudanças não são problemas — são evoluções. Mas precisam ser **documentadas como decisões conscientes** para não gerar confusão futura.

1. **Porta do Scraper: `:8080` → `:3009`**
   - Especificação original: Go Scraper em `:8080`
   - Roadmap: já corrige para `:3009`
   - Fase 1: confirma `:3009`
   - **Status:** Resolvido no roadmap, mas o diagrama da especificação original ainda mostra `:8080`

2. **Linguagem do Scraper: Go → Python**
   - Especificação original: "Motor compilado em Go de altíssima velocidade"
   - Fase 1: Python + `google-maps-scraper-kit` (CDP em Python)
   - **Status:** Decisão de trocar Go por Python precisa ser registrada como decisão arquitetural

3. **Payment Gateway: Asaas/Mercado Pago → Banco Inter mTLS**
   - Especificação original: "Asaas / Mercado Pago via API REST" com "custo R$ 0 de setup, taxa percentual apenas sobre o valor recebido"
   - Fase 1: Banco Inter com certificados mTLS, PIX direto pelo BACEN
   - **Status:** Mudança estratégica significativa (elimina intermediário), mas a especificação original nem menciona Banco Inter

4. **Cockpit e Backend: Java/Go → Removido da Fase 1**
   - Especificação original mencionava Java (Spring Boot / Micronaut) ou Go para "módulos de backend pesados"
   - Fase 1 e Roadmap: Cockpit é Fase 6 (Next.js), sem menção a Java/Go
   - **Status:** Simplificação correta. Java/Go eram over-engineering para o momento.

5. **Message Bus: TypeScript interface → RabbitMQ AMQP**
   - Especificação original: interface `AgentMessage` em TypeScript, event-driven genérico
   - Fase 0 (roadmap): já introduz RabbitMQ
   - Fase 1: Seção 15.2 formaliza AMQP com exchanges e DLX
   - **Status:** Evolução coerente, mas a interface TypeScript da especificação original não aparece mais (o sistema agora é Python-first com Pydantic)

---

## 2. Inconsistências com o Roadmap

| # | Aspecto | Roadmap | Fase 1 | Severidade |
|:--|:---|:---|:---|:---|
| 1 | **Portas do `/status`** | TC-122: portas 8000, 3005, 3006, 3007, 3009, 3010 | Seção 7.3: "`:8000`, `:3005`, `:3006`, `:3007`, `:3009`, `:3010`" — **falta `:3011`, `:3012`, `:3013`, `:3014`** | Média |
| 2 | **Gateways críticos no Fail-Fast** | Roadmap 1.10: "whatsapp, payment, guardrail" | Fase 1 seção 16.3: confirma os 3 mesmos | OK, mas **por que o Telegram não é crítico?** Se cair, João fica cego. |
| 3 | **SearXNG porta** | Diagrama da seção 6.4 mostra `:8888` | Nenhuma outra referência à porta `:8888` na topologia principal da seção 2 | Baixa |
| 4 | **Porta do Grafana** | Roadmap 1.10 e Fase 1 seção 16.2: `:3001` | Topologia da seção 2 NÃO lista Grafana/Loki como serviços | Baixa |

---

## 3. Pontas Soltas Identificadas (Coisas que Faltam)

### 3.1 Arquiteturais — Críticas

> [!CAUTION]
> Estes pontos podem bloquear ou complicar significativamente o desenvolvimento se não forem resolvidos antes.

1. **Autenticação inter-serviços não especificada de ponta a ponta**
   - O `payment-gateway` menciona "Bearer token interno" (seção 5.1), mas **nenhum outro serviço** especifica como se autentica com os demais.
   - Pergunta: Quem emite esse token? Como é rotacionado? Os outros 9 serviços usam o mesmo mecanismo?
   - O `X-Engine-Key` do Fase 0 (roadmap seção 0.6) não é referenciado na Fase 1.

2. **Fluxo exato do webhook Baileys → Guardrail → Core não está 100% claro**
   - O diagrama da seção 2 mostra: `WPP_SVC → GUARD_SVC → CORE`
   - Mas a seção 4.2 mostra o endpoint `POST /api/v1/inbound/whatsapp-webhook` no **guardrail**, sugerindo que o Baileys envia webhook direto para o guardrail
   - Enquanto isso, o guardrail supostamente NÃO é MCP Server para o Core (não aparece na lista de conexões MCP do Core na seção 2) — ele é REST puro.
   - **Pergunta:** O guardrail é chamado pelo Core via MCP? Ou o Baileys envia direto para o guardrail? Se é o segundo, como o Core descobre novas mensagens? Poll? Webhook do guardrail para o Core?

3. **RabbitMQ vs. MCP SSE: Dois padrões de comunicação coexistindo**
   - Seção 15.2 introduz RabbitMQ AMQP com exchanges, queues e DLX.
   - Mas TODOS os serviços usam MCP via SSE para comunicação.
   - **Pergunta:** Qual é o canal primário? O RabbitMQ substitui o MCP para mensageria assíncrona? Ou são complementares? Quem publica e quem consome em cada queue? Isto precisa de um diagrama claro de separação de responsabilidades.

4. **Onde fica o SearXNG no Docker Compose?**
   - O SearXNG é mencionado na `:8888` mas não aparece na tabela de topologia (seção 2).
   - Ele é um container Docker separado? É sub-processo do `osint-scraper-gateway`?
   - Da mesma forma, o **Qdrant (`:6333`)** é mencionado mas também não está na tabela de portas como serviço próprio.

5. **Numeração de seções com erro**
   - Seção 13 se chama "Esquemas de Banco de Dados da Fase 1" mas as subseções são numeradas como "12.1", "12.2", "12.3", "12.4", "12.5" — deveriam ser 13.x.

### 3.2 Funcionais — Médias

6. **Falta de schema para a tabela `leads`**
   - Vários serviços (scraper, payment, deploy) referenciam `lead_id` e a tabela `leads`, mas o schema dela NÃO está na seção 13 (schemas de banco).
   - A tabela `leads` é provavelmente definida na Fase 0, mas deveria ser referenciada ou ao menos linkada aqui.

7. **Falta de schema para tabelas de agentes/mensagens**
   - `agent_messages`, `audit_logs`, `token_metrics` são mencionadas no roadmap Fase 0, mas não aparecem no banco da Fase 1.
   - **Pergunta:** Elas já existem da Fase 0? Se sim, uma nota de referência cruzada ajudaria.

8. **`/api/v1/session/logout` — Quem pode chamar?**
   - Endpoint perigoso (desconecta WhatsApp). Não há menção de autenticação/autorização para endpoints administrativos REST do WhatsApp Gateway.

9. **Webhook PIX do Banco Inter — Exposição pública**
   - O endpoint `/api/v1/inter/webhook` precisa receber webhooks HTTPS da internet.
   - A seção 15.3 menciona rate limiting e whitelist de IPs, mas:
     - **Pergunta:** Quem faz a validação de assinatura/autenticidade do webhook do Inter? A seção 5.2 diz "valida autenticidade" mas não especifica como (HMAC? Certificado? Header?).

10. **`deep_research` — Ferramenta composta sem limites claros**
    - Combina `search_web` + `fetch_page_markdown` para N páginas.
    - **Pergunta:** Qual o timeout total? Qual o consumo máximo de memória? Pode travar se uma das páginas for gigante?

### 3.3 Operacionais — Baixas

11. **Ordem de inicialização dos containers**
    - Docker Compose `depends_on` só garante que o container subiu, não que está `healthy`.
    - **Pergunta:** Qual é a ordem de boot? O `engine-core` precisa que TODOS os MCP servers estejam up antes de iniciar? Ou faz discovery lazy?

12. **Backup do SQLite e do Qdrant**
    - Nenhuma menção a política de backup para `pipeline.db` ou para os dados do Qdrant.
    - Em produção, crash do disco = perda total.

13. **Certificados mTLS do Inter — Rotação**
    - Os certificados têm validade. Não há menção a alertas de expiração ou procedimento de renovação.

14. **Cookies de redes sociais — Expiração em massa**
    - Se todos os cookies expirarem simultaneamente (ex: Instagram muda política), toda a prospecção para.
    - **Sugestão:** Adicionar um health-check periódico dos cookies ativos.

---

## 4. Qualidade da Matriz de Testes

> [!TIP]
> A matriz de testes (seção 14) é **excelente e muito completa**. São 61 cenários (TC-101 a TC-161) cobrindo Happy Path, Boundary, Security, Resilience e Concurrency para todos os 10 microsserviços. Os cenários BDD Gherkin são claros e testáveis.

### Gaps nos testes:

| # | Gap | Microsserviço | Sugestão |
|:--|:---|:---|:---|
| 1 | Nenhum teste de **carga/stress** | Todos | Adicionar TC para: 50 mensagens simultâneas no WhatsApp, 10 PIX concorrentes |
| 2 | Nenhum teste de **expiração de QR Code** | `:3005` | QR expira a cada ~60s. O que acontece se o intervalo de regeneração falhar? |
| 3 | Nenhum teste de **webhook duplicado** | `:3006` | Banco Inter pode enviar o mesmo webhook 2x. Idempotência? |
| 4 | Nenhum teste de **rate limiting** do humanizer | `:3005` | Se 100 leads estão na fila, o intervalo de 15-45s é respeitado? |
| 5 | Nenhum teste de **fallback do Guardrail** quando Groq cai E o regex também falha | `:3007` | TC-113 cobre regex fallback. Mas e se o regex bloquear uma mensagem legítima? |
| 6 | Nenhum teste de **concurrent browser contexts** | `:3014` | Pooling de 5+ contexts simultâneos |

---

## 5. Pontos Fortes do Documento

1. **Isolamento de credenciais por microsserviço** — Cada gateway confina suas chaves. Padrão de segurança sólido.
2. **Multi-tenancy no Qdrant com payload filtering** — Elegante e sem overhead.
3. **CRAG com fallback web** — Pipeline de memória com auto-healing genuinamente inovador.
4. **Gate Triplo de Deploy** — Financeiro + QA + Segurança antes de produção. Anti-fraude nativo.
5. **Knowledge-as-Code** — Playbooks em Markdown versionados no Git. Excelente para manutenibilidade.
6. **Cenários BDD completos** — 12 funcionalidades em Gherkin cobrindo todos os fluxos críticos.
7. **Humanizer detalhado** — Política anti-ban bem pensada com limites concretos.
8. **DooD vs DinD** — Escolha correta de Docker-outside-of-Docker para sandbox.

---

## 6. Checklist de Prontidão para Desenvolvimento

| Critério | Status | Notas |
|:---|:---|:---|
| Topologia de portas definida | ✅ | 10 serviços + Qdrant + SearXNG + Grafana/Loki |
| Contratos MCP (tools/list) definidos | ✅ | Todos os inputSchemas documentados |
| Endpoints REST definidos | ✅ | Tabelas com método, path, params e resposta |
| Schemas de banco definidos | ⚠️ | Falta tabela `leads`, referência a tabelas da Fase 0 |
| Cenários de teste definidos | ✅ | 61 TCs + 12 BDDs Gherkin |
| Fluxo de comunicação inter-serviços | ⚠️ | MCP vs RabbitMQ ambíguo |
| Autenticação inter-serviços | ❌ | Não especificada uniformemente |
| Docker Compose definido | ⚠️ | Mencionado conceitualmente, falta `docker-compose.yml` spec |
| Política de backup | ❌ | Não mencionada |
| Política de rotação de credenciais | ❌ | Não mencionada |

---

## 7. Recomendações Prioritárias

1. **Resolver a ambiguidade MCP vs RabbitMQ** — Definir claramente: "MCP é para invocação síncrona de ferramentas. RabbitMQ é para eventos assíncronos (webhooks, alertas, filas de prospecção)."
2. **Especificar autenticação inter-serviços** — Propor: API key compartilhada via env (`X-Engine-Key`) para todos, ou mTLS interno.
3. **Corrigir numeração de seções** (13.x em vez de 12.x nos schemas).
4. **Adicionar tabela `leads`** ao schema ou referenciar explicitamente a Fase 0.
5. **Incluir SearXNG e Qdrant** na tabela de topologia da seção 2 como infraestrutura de suporte.
6. **Definir fluxo Baileys→Guardrail→Core** com diagrama sequencial explícito (quem chama quem, via qual protocolo).
7. **Adicionar testes de idempotência** para webhooks PIX e resiliência de carga.
