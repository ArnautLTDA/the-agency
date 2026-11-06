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
