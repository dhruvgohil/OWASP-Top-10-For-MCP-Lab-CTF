"""Thin async client for the Kanban MCP server over Streamable HTTP.

Each call opens a short-lived session. This is slightly less efficient than a pooled
connection but is far simpler and robust across container restarts, which is the right
trade-off for a small educational lab. It is fully tool-agnostic.
"""

import logging

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from .config import config

logger = logging.getLogger("mcp_client")


async def list_tools() -> list[dict]:
    """Return the tool definitions advertised by the MCP server.

    Returns an empty list on failure so callers can degrade gracefully.
    """
    try:
        async with streamablehttp_client(config.MCP_SERVER_URL) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.list_tools()
                return [
                    {
                        "name": t.name,
                        "description": t.description or "",
                        "input_schema": t.inputSchema,
                    }
                    for t in result.tools
                ]
    except Exception as exc:  # noqa: BLE001 - lab: never crash the chat loop
        logger.warning("Failed to list MCP tools: %s", exc)
        return []


async def call_tool(name: str, arguments: dict, tenant_id: str = "default") -> dict:
    """Invoke an MCP tool and return a structured result.

    Always returns a dict of the shape {"ok": bool, "content": str} so the LLM loop
    can feed a stable string back into the conversation regardless of success/failure.

    `tenant_id` is forwarded as the ``X-Helix-Tenant`` header so the MCP server serves this
    participant's isolated data partition. It is transport-level metadata -- it never touches
    the tool arguments, so the LLM (and the exploit prompts) are unaffected.
    """
    headers = {"X-Helix-Tenant": tenant_id}
    try:
        async with streamablehttp_client(config.MCP_SERVER_URL, headers=headers) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(name, arguments or {})

                # Flatten the returned content blocks into text.
                parts: list[str] = []
                for block in result.content:
                    text = getattr(block, "text", None)
                    if text is not None:
                        parts.append(text)
                    else:
                        parts.append(str(block))
                content = "\n".join(parts) if parts else "(no content returned)"

                if getattr(result, "isError", False):
                    return {"ok": False, "content": content}
                return {"ok": True, "content": content}
    except Exception as exc:  # noqa: BLE001 - lab: surface error to the LLM, don't crash
        logger.warning("MCP tool call '%s' failed: %s", name, exc)
        return {"ok": False, "content": f"Tool '{name}' failed: {exc}"}
