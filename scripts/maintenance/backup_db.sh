#!/usr/bin/env bash
# =============================================================================
# The Agency - Hot SQLite WAL Backup and 7-Day Retention Script (TC-223, TC-224)
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

cd "${PROJECT_ROOT}"
python3 "${SCRIPT_DIR}/backup_db.py" "$@"
