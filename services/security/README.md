# Security Audit Gateway (Port :3015)

Audits and gatekeeper microservice providing:
- SonarQube API integration (port 9000)
- Secrets scanning (Gitleaks)
- SAST scanning (Semgrep OWASP Top 10)
- SCA / Dependency vulnerability scanning (Trivy)
- DAST preview scanning (Nuclei)
- Security gate policy evaluation
- Native MCP Server exposing tools
