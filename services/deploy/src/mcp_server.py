"""Native MCP Server registering Cloud Deploy & Infrastructure tools (:3012)."""

from datetime import datetime, timezone
from typing import Any
import aiosqlite
from loguru import logger
from mcp.server.mcpserver import MCPServer

from config import settings
from supabase_client import SupabaseClient
from triple_gate import validate_triple_gate
from vercel_client import VercelClient


def create_deploy_mcp_server(
    vercel_client: VercelClient | None = None,
    supabase_client: SupabaseClient | None = None,
    db_path: str = settings.DATABASE_PATH,
) -> MCPServer:
    """Builds and configures the deploy-cloud-gateway MCP server instance."""
    server = MCPServer(
        name="deploy-cloud-gateway",
        version="0.1.0",
        instructions="Official Agency Cloud Deploy & Infrastructure Gateway MCP Server",
    )

    vercel = vercel_client or VercelClient()
    supabase = supabase_client or SupabaseClient()

    @server.tool(
        name="deploy_preview_demo",
        description="Deploys sales demo preview on Vercel without requiring full payment or production gates (TC-136).",
    )
    async def deploy_preview_demo(workspace_id: str, project_name: str) -> dict[str, Any]:
        dep = await vercel.create_deployment(project_name=project_name, target="preview")
        return {
            "deployment_id": dep.id,
            "url": dep.url,
            "ready_state": dep.ready_state,
            "target": "preview",
            "workspace_id": workspace_id,
        }

    @server.tool(
        name="deploy_production",
        description="Deploys production application on Vercel strictly enforcing the Triple Gate (Finance + QA + Security) (TC-137 to TC-140).",
    )
    async def deploy_production(
        workspace_id: str,
        project_name: str,
        lead_id: str,
        custom_domain: str | None = None,
        force_override: bool = False,
    ) -> dict[str, Any]:
        # 1. Enforce Triple Gate
        gate = await validate_triple_gate(
            lead_id=lead_id,
            workspace_id=workspace_id,
            db_path=db_path,
            force_override=force_override,
        )

        if not gate.allowed:
            return {
                "success": False,
                "error": "Triple Gate Rejected: All 3 gates (Finance, QA, Security) must pass before production deployment.",
                "gate_status": gate.model_dump(),
            }

        # 2. Trigger Vercel Production deployment
        dep = await vercel.create_deployment(
            project_name=project_name,
            target="production",
            custom_domain=custom_domain,
        )

        # 3. Record in SQLite deployments table
        try:
            async with aiosqlite.connect(db_path) as db:
                await db.execute(
                    """
                    INSERT INTO deployments (lead_id, workspace_id, deployment_type, deployment_url, status, qa_approved, security_approved, payment_cleared, created_at)
                    VALUES (?, ?, 'PRODUCTION', ?, 'SUCCESS', ?, ?, ?, ?)
                    """,
                    (
                        lead_id,
                        workspace_id,
                        dep.url,
                        1 if gate.qa_approved else 0,
                        1 if gate.security_approved else 0,
                        1 if gate.finance_cleared else 0,
                        datetime.now(timezone.utc).isoformat(),
                    ),
                )
                await db.commit()
            logger.info("Recorded production deployment for lead {lid} -> {url}", lid=lead_id, url=dep.url)
        except Exception as exc:
            logger.error("Failed recording deployment in database: {err}", err=exc)

        return {
            "success": True,
            "deployment_id": dep.id,
            "url": dep.url,
            "ready_state": dep.ready_state,
            "target": "production",
            "gate_status": gate.model_dump(),
        }

    @server.tool(
        name="get_deployment_status",
        description="Queries current build and ready status of a Vercel deployment.",
    )
    async def get_deployment_status(deployment_id: str) -> dict[str, Any]:
        dep = await vercel.get_deployment(deployment_id)
        return dep.model_dump()

    @server.tool(
        name="provision_database",
        description="Provisions a PostgreSQL database on Supabase for project infrastructure (TC-196).",
    )
    async def provision_database(project_name: str, region: str = "sa-east-1") -> dict[str, Any]:
        res = await supabase.provision_database(project_name=project_name, region=region)
        return res.model_dump()

    @server.tool(
        name="set_project_env_vars",
        description="Injects encrypted environment variables into a Vercel project (preview/production).",
    )
    async def set_project_env_vars(
        project_name: str,
        env_vars: dict[str, str],
        target: str = "preview",
    ) -> dict[str, Any]:
        res = await vercel.set_project_env_vars(project_name=project_name, env_vars=env_vars, target=target)
        return res

    return server
