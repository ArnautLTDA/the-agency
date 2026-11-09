## 1. Missão & Tese Central de Negócios (Memória Permanente)
*   **Objetivo Principal**: Gerar receita real e construir fluxo de caixa positivo.
*   **Ponto de Partida**: Caixa zero (R$ 0 / $0) e recurso computacional exclusivo (Assinatura Gemini Pro que dá acesso ao Antigravity + Hermes Agent).
*   **Modelo de Operação**: Criação de uma empresa / ecossistema de agentes autônomos orientado a monetização rápida, escalabilidade e custo marginal zero.
*   **Premissa Estratégica**: Flexibilidade tática total ("podemos fazer qualquer coisa"), priorizando velocidade para a primeira receita (time-to-cash), validação rápida de hipóteses e tomada de decisão orientada a dados, com liderança e aprovação final sempre a cargo do chefe.

---

## 2. Diretriz de Segurança de Processos e Estabilidade do Host (Anti-Crash)
*   **Proteção de Sinais**: Nunca invoque `os.killpg`, `killpg`, `os.kill` ou `kill` para PID/PGID menor ou igual a 1 (`pid <= 1` ou `pgid <= 1`). No padrão POSIX/Linux, `killpg(1, sig)` executa `kill(-1, sig)`, que envia o sinal para TODOS os processos do usuário no sistema operacional, derrubando o Antigravity e todas as sessões.
*   **Validação Prévia de Processos**: Sempre proteja rotinas de timeout e encerramento de processos com verificação estrita: `if proc is not None and isinstance(getattr(proc, "pid", None), int) and proc.pid > 1 and pgid > 1:`.
*   **Isolamento em Testes Unitários**: Em qualquer teste que utilize `MagicMock` ou `patch("subprocess.Popen")`, **sempre mocke `os.killpg`, `os.kill` e `os.getpgid`**. Nunca deixe `mock_proc.pid` como um mock solto que seja convertido em 1 e chegue às chamadas de sistema reais.
