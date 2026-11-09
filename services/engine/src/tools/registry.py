"""Tool Registry and JSON Schemas matching Gemini/LiteLLM function calling (TC-020)."""

import json
from pathlib import Path
from typing import Any
from sqlmodel.ext.asyncio.session import AsyncSession

from src.tools.implementations import (
    CouncilSecurityError,
    DirectoryListing,
    PathTraversalError,
    list_directory,
    patch_file,
    read_file,
    run_terminal_command,
    send_agent_message,
    write_file,
)


TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Reads and returns the complete text content of a file within the workspace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the file relative to the workspace root.",
                    }
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Creates a new file or overwrites an existing file with the provided text content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the file relative to the workspace root.",
                    },
                    "content": {
                        "type": "string",
                        "description": "Full text content to write into the file.",
                    },
                    "overwrite": {
                        "type": "boolean",
                        "description": "Whether to overwrite the file if it already exists. Defaults to true.",
                        "default": True,
                    },
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "patch_file",
            "description": "Surgically replaces a specific search block with replacement text in a file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the file relative to workspace root.",
                    },
                    "search_block": {
                        "type": "string",
                        "description": "The exact block of code or text to search for (must match uniquely).",
                    },
                    "replace_block": {
                        "type": "string",
                        "description": "The replacement block of code or text.",
                    },
                },
                "required": ["path", "search_block", "replace_block"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_directory",
            "description": "Lists the files and folders inside a given workspace directory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Directory path relative to workspace root. Defaults to '.' (root).",
                        "default": ".",
                    }
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_terminal_command",
            "description": "Runs a shell command in an isolated Docker sandbox container mounting only the workspace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The shell/bash command string to execute.",
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Timeout in seconds before terminating the process (clamped between 5 and 180s). Defaults to 60.",
                        "default": 60,
                        "minimum": 5,
                        "maximum": 180,
                    },
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_agent_message",
            "description": "Sends an asynchronous message to another agent or broadcasts to the entire pipeline.",
            "parameters": {
                "type": "object",
                "properties": {
                    "to_agent": {
                        "type": "string",
                        "description": "Target agent identifier slug or 'broadcast'.",
                    },
                    "message_type": {
                        "type": "string",
                        "description": "Message type enum value (e.g. task_assignment, status_update, etc.)",
                    },
                    "payload": {
                        "type": "object",
                        "description": "Structured JSON payload for the recipient.",
                    },
                    "priority": {
                        "type": "string",
                        "enum": ["critical", "high", "medium", "low"],
                        "default": "medium",
                    },
                    "requires_ack": {
                        "type": "boolean",
                        "default": False,
                    },
                    "correlation_id": {
                        "type": "string",
                        "description": "Optional correlation ID for conversation threading.",
                    },
                },
                "required": ["to_agent", "message_type", "payload"],
            },
        },
    },
]


def get_tool_definitions(allowed_tools: list[str] | None = None) -> list[dict[str, Any]]:
    """Filters and returns function schemas for allowed tools."""
    if not allowed_tools:
        return TOOL_SCHEMAS
    return [
        tool
        for tool in TOOL_SCHEMAS
        if tool["function"]["name"] in allowed_tools
    ]


async def execute_tool(
    name: str,
    arguments: dict[str, Any],
    workspace_dir: Path,
    session: AsyncSession | None = None,
    from_agent: str = "agent",
) -> str:
    """Dispatches a tool call with self-correction feedback on validation or security errors."""
    try:
        if name == "read_file":
            if "path" not in arguments:
                return "Error: Missing required parameter 'path'."
            return read_file(workspace_dir=workspace_dir, path=str(arguments["path"]))

        elif name == "write_file":
            if "path" not in arguments or "content" not in arguments:
                return "Error: Missing required parameters 'path' or 'content'."
            return write_file(
                workspace_dir=workspace_dir,
                path=str(arguments["path"]),
                content=str(arguments["content"]),
                overwrite=bool(arguments.get("overwrite", True)),
            )

        elif name == "patch_file":
            for param in ["path", "search_block", "replace_block"]:
                if param not in arguments:
                    return f"Error: Missing required parameter '{param}'."
            return patch_file(
                workspace_dir=workspace_dir,
                path=str(arguments["path"]),
                search_block=str(arguments["search_block"]),
                replace_block=str(arguments["replace_block"]),
            )

        elif name == "list_directory":
            path = str(arguments.get("path", "."))
            listing = list_directory(workspace_dir=workspace_dir, path=path)
            if isinstance(listing, DirectoryListing):
                if listing.has_more:
                    return json.dumps({
                        "items": list(listing),
                        "total_count": listing.total_count,
                        "has_more": True,
                        "notice": "Output truncated to 500 items.",
                    }, indent=2)
                return json.dumps(list(listing), indent=2)
            return json.dumps(listing, indent=2)

        elif name == "run_terminal_command":
            if "command" not in arguments:
                return "Error: Missing required parameter 'command'."
            try:
                raw_timeout = int(arguments.get("timeout", 60))
            except (ValueError, TypeError):
                raw_timeout = 60
            # SEC-006: Clamped strictly between 5 and 180 seconds
            clamped_timeout = max(5, min(raw_timeout, 180))
            result = run_terminal_command(
                workspace_dir=workspace_dir,
                command=str(arguments["command"]),
                timeout=clamped_timeout,
            )
            return json.dumps(result, indent=2)

        elif name == "send_agent_message":
            if session is None:
                return "Error: Database session unavailable for messaging."
            for param in ["to_agent", "message_type", "payload"]:
                if param not in arguments:
                    return f"Error: Missing required parameter '{param}'."
            return await send_agent_message(
                session=session,
                from_agent=from_agent,
                to_agent=str(arguments["to_agent"]),
                message_type=str(arguments["message_type"]),
                payload=dict(arguments["payload"]),
                priority=str(arguments.get("priority", "medium")),
                requires_ack=bool(arguments.get("requires_ack", False)),
                correlation_id=arguments.get("correlation_id"),
            )

        else:
            return f"Error: Unknown tool '{name}'. Authorized tools are {[t['function']['name'] for t in TOOL_SCHEMAS]}."

    except (PathTraversalError, CouncilSecurityError) as sec_exc:
        return f"Security Error: {sec_exc}"
    except Exception as exc:
        return f"Error executing tool '{name}': {exc}"
