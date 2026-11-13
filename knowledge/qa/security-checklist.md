# Checklist de Homologação de Segurança

## Auditoria Pré-Deploy
1. Zero segredos ou credenciais expostas no código (validado via Gitleaks).
2. Semgrep SAST limpo contra vulnerabilidades críticas do OWASP Top 10 (SQLi, XSS, SSRF).
3. Dependências auditadas via Trivy SCA sem CVEs críticas ativas.
4. Quality Gate oficial do SonarQube aprovado com cobertura mínima de 80%.

## Pentest Dinâmico Nuclei
Validar cabeçalhos de segurança obrigatórios: Content-Security-Policy, HSTS, X-Frame-Options, X-Content-Type-Options.
