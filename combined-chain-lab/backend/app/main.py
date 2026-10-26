"""FastAPI orchestrator for the dual-LLM MCP07 (auth & authz) lab."""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .config import config
from . import llm_agents, mcp_client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("main")

app = FastAPI(title="HelixChain — Dual-LLM MCP Kill-Chain Lab (MCP01 + MCP05 + MCP07)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"
    # Stable per-browser tenant id. Partitions this participant's lab world (tickets, notes,
    # admin account, board) on the MCP server so concurrent players never collide. Distinct
    # from session_id (which only keys conversation memory and is rotated by "New session").
    tenant_id: str = "default"


class ChatResponse(BaseModel):
    reply: str
    # Attack-surface node keys this request reached, for the live map (you/frontend/backend/mcp/
    # signer/board). Display metadata only -- it never affects flag retrieval.
    reached: list[str] = []


class ResetRequest(BaseModel):
    session_id: str = "default"


@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    """Route a user message through the frontend LLM, within its session's memory."""
    trace: set[str] = set()
    try:
        reply = await llm_agents.run_frontend_agent(
            req.message, req.session_id, req.tenant_id, trace
        )
    except Exception as exc:  # noqa: BLE001 - never return a bare 500 to the chat UI
        logger.exception("Unhandled error in /api/chat")
        reply = f"Sorry, something went wrong handling that request. ({exc})"
    return ChatResponse(reply=reply, reached=sorted(trace))


@app.post("/api/reset")
async def reset(req: ResetRequest) -> dict:
    """Clear a session's conversation memory (the 'rewind / new session' technique)."""
    llm_agents.reset_session(req.session_id)
    return {"ok": True}


@app.get("/api/health")
async def health() -> dict:
    """Liveness plus a best-effort probe of MCP reachability."""
    tools = await mcp_client.list_tools()
    return {
        "status": "ok",
        "mcp_reachable": len(tools) > 0,
        "mcp_tools": [t["name"] for t in tools],
        "frontend_model": config.FRONTEND_MODEL,
        "backend_model": config.BACKEND_MODEL,
    }
