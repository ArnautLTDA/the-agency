# 🎯 Especificação Técnica Preliminar: FASE 3 — Prospecção, Prototipação & Funil de Vendas

> **Status:** Rascunho / Conceitos Preservados da Fase 0 (Aguardando destrinchamento completo na Fase 3)

---

## 1. Modelagem de Dados: Ficha de Leads & Estágios do Funil

```sql
CREATE TABLE leads (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    niche TEXT NOT NULL,
    phone TEXT NOT NULL,
    address TEXT,
    rating REAL,
    reviews_count INTEGER,
    instagram_url TEXT,
    extracted_data JSON,
    stage TEXT NOT NULL DEFAULT 'MINED', 
    -- Estágios do ciclo de vida:
    -- 'MINED': Minerado no Maps/Instagram
    -- 'DEMO_READY': Protótipo interativo gerado na Vercel
    -- 'OUTREACH': Abordagem enviada no WhatsApp
    -- 'NEGOTIATING': Em negociação / quebra de objeções
    -- 'DEV': Sinal de 50% pago, projeto em desenvolvimento
    -- 'QA': Em testes e pentest
    -- 'HOMOLOGATING': Em teste guiado com o cliente
    -- 'PROD': 50% finais pagos e deploy definitivo
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

---

## 2. Endpoints do Ciclo de Vida do Lead

* `POST /api/v1/pipeline/lead`: Injeta um novo lead minerado para processamento pela esteira.
* `GET /api/v1/pipeline/state/{lead_id}`: Retorna o estágio atual e histórico do lead no grafo.
* `POST /api/v1/pipeline/resume/{lead_id}`: Retoma a execução após aprovação manual de João (Human-in-the-Loop na Calibragem).
