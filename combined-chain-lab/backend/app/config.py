"""Central configuration read from environment variables.

Defaults target a local Ollama setup so the lab comes up with `docker compose up` after
`cp .env.example .env`.
"""

import os


class Config:
    # OpenAI-compatible endpoint (Ollama, vLLM, ...). Must end in /v1 for Ollama.
    LLM_BASE_URL: str = os.getenv("LLM_BASE_URL", "http://100.64.138.60:11434/v1")
    LLM_API_KEY: str = os.getenv("LLM_API_KEY", "ollama")

    # Any tool-calling-capable model works. rafw007/gemma4-e4b-claude-coder:latest is a strong default.
    FRONTEND_MODEL: str = os.getenv("FRONTEND_MODEL", "rafw007/gemma4-e4b-claude-coder:latest")
    BACKEND_MODEL: str = os.getenv("BACKEND_MODEL", "rafw007/gemma4-e4b-claude-coder:latest")

    # Streamable HTTP endpoint exposed by the Support MCP server.
    MCP_SERVER_URL: str = os.getenv("MCP_SERVER_URL", "http://mcp-server:8001/mcp")

    # The four staged objectives. Neither LLM is ever given these; flag submission/grading is
    # handled by the separate scoreboard app.
    FLAG1: str = os.getenv("FLAG1", "FLAG{CHAIN_STATUS_INFO_DISCLOSURE}")
    FLAG2: str = os.getenv("FLAG2", "FLAG{CHAIN_SIGNER_PRIVILEGE_ESCALATION}")
    FLAG3: str = os.getenv("FLAG3", "FLAG{CHAIN_ADMIN_BOLA_CONFUSED_DEPUTY}")
    FLAG4: str = os.getenv("FLAG4", "FLAG{CHAIN_ADMIN_RCE_COMMAND_INJECTION}")

    # Per-LLM-call timeout in seconds.
    LLM_TIMEOUT: float = float(os.getenv("LLM_TIMEOUT", "60"))

    # Sampling temperature for the FIRST attempt of each agent turn. This local Ollama build
    # ignores `tool_choice`, and at temperature 0 the model deterministically LOCKS onto a
    # refusal for "exploit-looking" requests (e.g. minting a token from the leaked key) and
    # never calls the tool. A moderate temperature gives the sampling variance that lets it
    # comply; the retry loop below then drives reliability up toward 100%.
    LLM_TEMPERATURE: float = float(os.getenv("LLM_TEMPERATURE", "0.6"))

    # Resample-on-refusal: when an agent SHOULD act but returns no tool call (a soft refusal
    # like "I can't do that"), we re-ask up to this many extra times at a rising temperature
    # to shake it off the refusal path. Costs latency only on turns the model initially
    # balks at; a compliant sample is accepted the moment it appears.
    TOOL_CALL_RETRIES: int = int(os.getenv("TOOL_CALL_RETRIES", "6"))

    # Temperature floor for those retries (each retry nudges it higher, capped at 1.2).
    RETRY_TEMPERATURE: float = float(os.getenv("RETRY_TEMPERATURE", "0.85"))

    # Max tool-call iterations per agent loop (guards against runaway loops).
    MAX_ITERATIONS: int = int(os.getenv("MAX_ITERATIONS", "6"))

    # Auth is multi-turn, so unlike the sibling labs we keep per-session conversation
    # memory. This caps how many prior messages we retain per agent, per session.
    HISTORY_LIMIT: int = int(os.getenv("HISTORY_LIMIT", "40"))

    # Per-agent tight caps. This local model (rafw007/gemma4-e4b-claude-coder:latest via Ollama) starts emitting EMPTY
    # turns -- no text, no tool call -- once the context grows past ~16-18 messages, which
    # silently breaks the later stages: the BACKEND stops calling escalation tools (env_debug,
    # reset) and, just as damaging, the FRONTEND stops FORWARDING the request inward at all.
    # Both agents' histories bloat with big tool results (the frontend's tool result is the
    # backend's full reply). The exploit prompts re-pass every token/value they need, so
    # neither agent needs deep memory; we keep only the last couple of exchanges to stay well
    # under the cliff. Raise these and the later stages start returning blank again.
    BACKEND_HISTORY_LIMIT: int = int(os.getenv("BACKEND_HISTORY_LIMIT", "8"))
    FRONTEND_HISTORY_LIMIT: int = int(os.getenv("FRONTEND_HISTORY_LIMIT", "8"))

    # Comma-separated list of allowed CORS origins for the frontend. This lab's frontend is
    # served on the remapped host port 3100 (so it can run alongside the three source labs),
    # so the browser's Origin is http://localhost:3100 -- it MUST be in this list or every
    # fetch (including /api/health) is blocked by CORS and the UI shows "backend unreachable".
    CORS_ORIGINS: list[str] = os.getenv(
        "CORS_ORIGINS",
        "http://localhost:3100,http://127.0.0.1:3100,"
        "http://localhost:3000,http://127.0.0.1:3000,"
    ).split(",")

config = Config()
