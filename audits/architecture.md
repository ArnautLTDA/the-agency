# 🏛️ Architecture & Reconnaissance Summary

> **Audit Run:** `run-20261106-phase0-engine`  
> **Repository Target:** `the-agency` (`services/engine`)  
> **Standard:** `security-audit` skill (Phase 1 Reconnaissance)  

---

## 1. Product, Principals, Authority & Protected Resources

* **Product Type:** Standalone Autonomous Agent Runtime (Phase 0 Foundation Engine).
* **Principals:**
  * **External Caller / Client:** Sends HTTP instructions via `/api/v1/agent/run` and subscribes to SSE streaming.
  * **Autonomous Agent (e.g. `homologation_agent`):** Executes reasoning steps, calls tools, and writes code.
  * **Council C-Suite Agents (`ceo`, `cto`, `cro`, `coo`):** Governance profiles with immutable business directives.
  * **Engine Host / Daemon (`uvicorn`):** System process running with host user privileges.
* **Protected Resources:**
  * Host file system and environment variables (SSH keys, AWS/cloud tokens, system binaries).
  * Client workspace directories (`workspaces/clients/<client-slug>/`).
  * Council configuration profiles (`config/agents/council/*.yaml`).
  * Inter-agent message bus and telemetry store (`pipeline.db`).
  * LLM provider API credentials and financial quotas.

---

## 2. Tech Stack, Deployment & Local Execution Boundaries

* **Languages & Runtime:** Python 3.12+ managed via `uv`, SQLite 3 (WAL mode).
* **Frameworks:** FastAPI, Uvicorn, SQLModel / Async SQLAlchemy, LiteLLM, Pydantic v2, Loguru.
* **Execution Drivers:**
  * `DockerSandboxDriver`: Ephemeral `node:20-slim` container with mounted workspace `/workspace`.
  * `SubprocessSandboxDriver`: Local fallback executing directly via `subprocess.Popen(shell=True)`.
* **Offline Execution Limits:** Tests and offline verification run without external network using local fixtures; live E2E test requires Google Gemini API credentials.

---

## 3. Entry Surfaces & Source-to-Sink Paths

* **Surface 1: HTTP API (`POST /api/v1/agent/run`):** Ingests `agent_id`, `task`, `workspace_dir`, `max_iterations`. Flows to `AgentRunner`, `DockerSandboxDriver` and SQLite.
* **Surface 2: Real-time Streaming (`GET /api/v1/events/stream`):** Ingests optional `run_id` filter and streams SSE packets to subscribers.
* **Surface 3: Health & Diagnostics (`GET /api/v1/health`):** Queries database connectivity and checks exchange rate from `AwesomeAPI`.
* **Surface 4: Tool Execution Loop:** Native tools (`read_file`, `write_file`, `patch_file`, `list_directory`, `run_terminal_command`, `send_agent_message`) invoked during agent turns.

---

## 4. Trust Boundaries & Control Locations

* **Boundary 1 (External ➔ API):** Boundary between unauthenticated callers and engine core. Intended control: authentication, rate limiting and input validation (Identified as absent/weak in `sec-001`, `sec-003`, `sec-014`).
* **Boundary 2 (Engine ➔ Client Workspace):** Boundary between agent tools and host filesystem. Intended control: `resolve_safe_path` in `src/tools/implementations.py:25` enforcing `target.relative_to(resolved_ws)`.
* **Boundary 3 (Agent ➔ Sandbox Terminal):** Boundary between agent bash execution and host system. Intended control: Docker container with resource quotas. Defeated if Docker unavailable (`sec-002`) or if network isolation is omitted (`sec-007`).
* **Boundary 4 (Pipeline ➔ Council Governance):** Boundary preventing agent modification of executive rules. Control: `CouncilSecurityError` check in `src/tools/implementations.py:43`.

---

## 5. Companion Selection Summary

In accordance with [ATTACK-CLASSES.md](file:///home/joao/.gemini/config/skills/security-audit/ATTACK-CLASSES.md), the following companion modules were selected:
* **`AI-AND-LLM.md`:** Agent tool calling, prompt injection, context window governance, token pricing.
* **`WEB-PROTOCOL-AND-AUTH.md`:** FastAPI endpoints, authentication headers, SSE framing, CORS.
* **`RESOURCE-EXHAUSTION-AND-AVAILABILITY.md`:** Concurrency semaphores, queue limits, terminal timeouts, memory leaks.
* **`CLOUD-AND-DEPLOYMENT.md`:** Container capabilities, network isolation, host volume mounts.
* **`PROTOCOLS-RPC-AND-MESSAGING.md`:** SSE pub/sub event broker, inter-agent messaging protocol.
* **`DATA-ISOLATION-AND-LIFECYCLE.md`:** SQLite WAL concurrency, audit trails, crash recovery, retention.
