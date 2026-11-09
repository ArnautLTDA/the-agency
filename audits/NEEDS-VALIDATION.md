# ⏳ Itens que Requerem Validação em Produção (Needs Validation)

Este documento registra as hipóteses e condições de segurança cuja confirmação ou refutação definitiva depende de fatores externos de infraestrutura, deployment em nuvem ou configurações de rede não visíveis no repositório local.

---

## SEC-NV-001: Validação de Rate Limiting e Proteção contra DoS no Ingress de Produção

* **Fingerprint:** `sec-nv-001-production-reverse-proxy-rate-limit`  
* **Veredito:** `needs_validation`  
* **Título:** Verificação de Rate Limiting e Filtros de Ingress no Reverse Proxy em Produção  
* **Causa-Raiz Alegada:** O repositório local não contém manifests de infraestrutura de borda (Cloudflare Workers, Nginx configs, Traefik ou AWS Application Load Balancer), impedindo comprovar se há limitação de requisições implementada fora da camada da aplicação.  

### Arquivos e Rastreamento
* **Ponto de Entrada:** [`services/engine/src/config.py:52`](file:///home/joao/projetos/the%20agency/services/engine/src/config.py#L52) (`HOST: str = "127.0.0.1"`)
* **Ponto de Execução:** [`services/engine/src/main.py:69`](file:///home/joao/projetos/the%20agency/services/engine/src/main.py#L69) (`uvicorn.run(...)`)

### Bloqueadores Identificados
* Os arquivos de configuração de borda (Cloudflare / Nginx / ALB) não estão versionados dentro deste repositório de aplicação.

### Planos de Validação
1. **Plano de Validação Local:** Inspecionar o repositório de infraestrutura (`infra` ou `terraform`) da software house e verificar se existem regras de rate limit aplicadas à rota `/api/v1/agent/run`.
2. **Plano de Validação em Homologação/Staging:** Em ambiente de staging controlado, disparar rajadas de 200 requisições simultâneas e registrar se o proxy de borda devolve `HTTP 429 Too Many Requests` antes de sobrecarregar o Uvicorn.
