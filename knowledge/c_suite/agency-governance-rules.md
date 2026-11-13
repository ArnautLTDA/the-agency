# Regras de Governança Executiva da Software House

## Soberania e Decisões Críticas
Deploys em produção exigem aprovação no Gate Triplo: 100% de pagamentos liquidados no Banco Inter, homologação integral de testes QA, e gate de segurança verde.
Ações com impacto financeiro ou desvio de orçamento necessitam de aprovação explícita de João via bot do Telegram com janela de timeout de 24 horas.

## Política de Continuidade Operacional (Fail-Fast)
Instabilidades em gateways vitais (WhatsApp, Pagamento ou Guardrail) provocam Pausa Emergencial imediata da esteira comercial.
Recuperação autônoma automática é acionada assim que os healthchecks normalizam.
