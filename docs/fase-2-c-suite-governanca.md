# 🏛️ Especificação Técnica Preliminar: FASE 2 — O Comitê Executivo (C-Suite Board) & Governança

> **Status:** Rascunho / Conceitos Preservados da Fase 0 (Aguardando destrinchamento completo na Fase 2)

---

## 1. Régua de Autonomia Progressiva (De Calibragem a Piloto Automático)

A esteira opera sob um parâmetro global `AUTONOMY_LEVEL` configurável por João no Cockpit:

| Nível de Autonomia | Comportamento da Esteira | Papel do Chefe João |
| :--- | :--- | :--- |
| **Nível 1: Calibragem Inicial** | Pausa obrigatória em todas as etapas (`interrupt_before`). Nenhuma mensagem sai no WhatsApp e nenhum código é mergeado sem clique de aprovação. | **Comandante Tático:** Inspeciona cada artefato, valida copies e aprova deploys. |
| **Nível 2: Supervisão por Exceção** | Mineração, geração de demos, abordagem padrão e correções de bugs com 100% de testes aprovados rodam **automaticamente**. | **Gestor Estratégico:** Intervém apenas quando um teste falhar, se o lead fizer pedidos atípicos ou na confirmação de sinais PIX. |
| **Nível 3: Piloto Automático Total** | A esteira opera de ponta a ponta com auto-aprimoramento contínuo, prospecção e fechamento autônomos. | **Presidente / Investidor:** Acompanha o Dashboard de Lucro Líquido e recebe relatórios executivos periódicos. |

### Lógica Condicional de Pausa:
```python
def check_human_approval_gate(state: PipelineState) -> str:
    # No Nível 1 (Calibragem): SEMPRE pausa para João
    if state.autonomy_level == AutonomyLevel.CALIBRATION:
        return "pause_for_joao"

    # No Nível 2 ou 3: avalia confiança e bateria de testes
    if state.tests_passed and state.confidence_score >= 0.95:
        return "auto_advance_to_production"
    else:
        return "pause_for_joao"
```

---

## 2. Modelagem do Banco: Configurações do Conselho

```sql
CREATE TABLE council_configs (
    agent_id TEXT PRIMARY KEY, -- ceo, cto, cro, coo
    model_name TEXT NOT NULL DEFAULT 'gemini-2.5-flash',
    temperature REAL NOT NULL DEFAULT 0.2,
    system_instructions TEXT NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

---

## 3. Endpoints do Conselho Executivo

* `POST /api/v1/council/deliberate`: Dispara uma sessão de debate do C-Suite sobre uma pauta estratégica (precificação, análise de gargalos, Buy vs Host vs Build).

---

## 4. Barramento Multi-Agentes RabbitMQ, Concorrência e Governança de Decisão

> [!IMPORTANT]
> **Evolução Arquitetural das Fases 0 e 1:** Esta seção estabelece como o barramento RabbitMQ e a governança de dados evoluem na Fase 2 para suportar a deliberação autônoma entre múltiplos agentes executivos (CEO, CTO, CRO, COO).

### 4.1 Barramento de Deliberação AMQP (`agency.council.*`)
* **Topic Exchange:** Utiliza a exchange `agency.topic` estabelecida nas fases anteriores.
* **Tópicos de Deliberação do C-Suite:**
  * `council.deliberate.request`: Pautas estratégicas submetidas para discussão executiva.
  * `council.deliberate.opinion.{agent_id}`: Pareceres técnicos emitidos individualmente por cada membro do conselho (`ceo`, `cto`, `cro`, `coo`).
  * `council.deliberate.consensus`: Síntese de consenso gerada pelo CEO ou mediação solicitada a João via Telegram.
* **Orquestração com LangGraph:** O fluxo de deliberação multi-agentes opera sobre nós do LangGraph com estado compartilhado imutável, despachando turnos de fala e coletando votos com controle estrito de concorrência.

### 4.2 Isolamento Transacional e Bloqueio Otimista de Decisões
* **Prevenção de Race Conditions:** Quando múltiplos agentes avaliam ou alteram planos simultaneamente, o estado é protegido por versionamento com **bloqueio otimista (`version_id`)** no SQLite WAL.
* **Detecção de Conflitos:** Se dois agentes tentarem atualizar a mesma diretriz ou alocação de verba simultaneamente, a transação conflituosa é rejeitada e re-executada sobre o estado consolidado mais recente.

### 4.3 Trilha de Auditoria Executiva & Retenção de Governança
* **Rastreabilidade Soberana de Decisões:**
  * Todas as deliberações do C-Suite, mudanças no parâmetro `AUTONOMY_LEVEL` e aprovações de João via Telegram são registradas na tabela `AuditLog` com assinaturas digitais e carimbos de data/hora UTC.
* **Política de Retenção Diferenciada:**
  * Enquanto métricas operacionais e logs de ferramentas descartáveis seguem a janela de expurgo de 30 dias (Fase 0), **os registros de decisões executivas do Conselho e relatórios financeiros possuem retenção estendida de 365 dias**, servindo de base histórica para o auto-aprimoramento contínuo da agência.

