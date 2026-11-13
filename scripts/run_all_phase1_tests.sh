#!/usr/bin/env bash
set -e

echo "================================================================="
echo "   THE AGENCY - SUÍTE COMPLETA DE TESTES DE INTEGRAÇÃO FASE 1    "
echo "================================================================="

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

declare -A RESULTS
FAILURES=0

run_test() {
    local svc_name="$1"
    local dir="$2"
    local cmd="$3"
    echo ""
    echo ">>> Executando testes: $svc_name ($dir)"
    echo "-----------------------------------------------------------------"
    if (cd "$ROOT_DIR/$dir" && eval "$cmd"); then
        RESULTS["$svc_name"]="PASSED"
        echo ">>> [OK] $svc_name passou com sucesso!"
    else
        RESULTS["$svc_name"]="FAILED"
        FAILURES=$((FAILURES + 1))
        echo ">>> [FALHA] $svc_name falhou!"
    fi
}

# 1. common
run_test "agency-common" "services/common" ".venv/bin/pytest"

# 2. whatsapp-gateway (:3005)
run_test "whatsapp-gateway (:3005)" "services/whatsapp" "npm test"

# 3. payment-gateway (:3006)
run_test "payment-gateway (:3006)" "services/payment" ".venv/bin/pytest"

# 4. guardrail-gateway (:3007)
run_test "guardrail-gateway (:3007)" "services/guardrail" ".venv/bin/pytest"

# 5. telegram-gateway (:3008)
run_test "telegram-gateway (:3008)" "services/telegram" ".venv/bin/pytest"

# 6. osint-scraper-gateway (:3009)
run_test "osint-scraper-gateway (:3009)" "services/scraper" ".venv/bin/pytest"

# 7. workspace-sandbox-service (:3010)
run_test "workspace-sandbox-service (:3010)" "services/sandbox" ".venv/bin/pytest"

# 8. git-vcs-gateway (:3011)
run_test "git-vcs-gateway (:3011)" "services/git" ".venv/bin/pytest"

# 9. deploy-cloud-gateway (:3012)
run_test "deploy-cloud-gateway (:3012)" "services/deploy" ".venv/bin/pytest"

# 10. knowledge-memory-gateway (:3013)
run_test "knowledge-memory-gateway (:3013)" "services/memory" ".venv/bin/pytest"

# 11. browser-gateway (:3014)
run_test "browser-gateway (:3014)" "services/browser" ".venv/bin/pytest"

# 12. security-audit-gateway (:3015)
run_test "security-audit-gateway (:3015)" "services/security" ".venv/bin/pytest"

# 13. engine-core (:8000)
run_test "engine-core (:8000)" "services/engine" ".venv/bin/pytest --ignore=tests/test_e2e_runner.py"

echo ""
echo "================================================================="
echo "                RESUMO CONSOLIDADO DE TESTES                     "
echo "================================================================="
for svc in "agency-common" \
           "whatsapp-gateway (:3005)" \
           "payment-gateway (:3006)" \
           "guardrail-gateway (:3007)" \
           "telegram-gateway (:3008)" \
           "osint-scraper-gateway (:3009)" \
           "workspace-sandbox-service (:3010)" \
           "git-vcs-gateway (:3011)" \
           "deploy-cloud-gateway (:3012)" \
           "knowledge-memory-gateway (:3013)" \
           "browser-gateway (:3014)" \
           "security-audit-gateway (:3015)" \
           "engine-core (:8000)"; do
    printf "%-38s : %s\n" "$svc" "${RESULTS[$svc]}"
done
echo "================================================================="

if [ $FAILURES -eq 0 ]; then
    echo "TODOS OS MICROSSERVIÇOS E GATEWAYS DA FASE 1 PASSARAM COM 100% DE SUCESSO!"
    exit 0
else
    echo "FALHAS ENCONTRADAS EM $FAILURES SERVIÇO(S)."
    exit 1
fi
