"""
Shared mutable state, config, and utility functions.

Every other module imports from here for shared state.
No cross-imports between route modules — only from state.
"""

import json
from constants import (
    CONFIG_FILE, CHARS_PER_TOKEN, MEMORY_DIR,
    PROD_ROOT, BRANCH_ROOT,
    MAX_ACTION_TURNS,
)
from tools import TOOL_DEFINITIONS


# ── Config ────────────────────────────────────────────────────────────
config = {
    "providers": {
        "openrouter": {
            "name": "OpenRouter",
            "api_key": "",
            "base_url": "https://openrouter.ai/api/v1",
            "model": "openrouter/hunter-alpha",
        },
        "minimax": {
            "name": "MiniMax",
            "api_key": "",
            "base_url": "https://api.minimaxi.chat/v1",
            "model": "MiniMax-M2.7",
        },
    },
    "selected": "minimax",
    "pod_host": "100.92.245.67",
}

# CONFIG_FILE imported from constants
if CONFIG_FILE.exists():
    try:
        saved = json.loads(CONFIG_FILE.read_text())
        for k, v in saved.get("providers", {}).items():
            if k in config["providers"]:
                config["providers"][k].update(v)
            else:
                config["providers"][k] = v
        config["selected"] = saved.get("selected", config["selected"])
        config["pod_host"] = saved.get("pod_host", config["pod_host"])
    except Exception:
        pass


def _save_config():
    CONFIG_FILE.write_text(json.dumps(config, indent=2))


def _get_provider():
    return config["providers"][config["selected"]]


def _pod_url(port: int) -> str:
    return f"http://{config['pod_host']}:{port}"


def sse_event(event_type: str, data: dict) -> str:
    return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"


# ── Read-only tool detection ──────────────────────────────────────────
READ_ONLY_TOOLS = frozenset({
    "list_files", "read_file", "read_lines", "read_file_tail", "grep_code",
    "read_project", "memory_load", "memory_list",
})

_BASH_READONLY_PREFIXES = (
    "ls ", "ls\n", "cat ", "head ", "tail ", "grep ", "rg ", "find ", "wc ",
    "cd ", "pwd", "echo ", "which ", "file ", "stat ", "du ", "df ",
    "tree ", "less ", "more ", "diff ", "sort ", "uniq ", "cut ", "awk ",
    "sed -n", "type ", "printenv", "env ", "ps ", "ss ", "curl -s",
    "curl -I", "curl -v", "python3 -c \"import", "python3 -m py_compile",
    "node --check", "git status", "git log", "git diff", "git show",
    "git blame", "git branch", "podman ps", "docker ps",
)


def _is_readonly_tool_call(tc: dict) -> bool:
    name = tc.get("function_name", "")
    if name in READ_ONLY_TOOLS:
        return True
    if name == "bash":
        args = tc.get("arguments", {})
        cmd = (args.get("command", "") or "").strip()
        if cmd and any(cmd.startswith(p) for p in _BASH_READONLY_PREFIXES):
            return True
    return False


# ── Heartbeat progress tracking ───────────────────────────────────────
_heartbeat_progress = {
    "active": False,
    "project": "",
    "todo_id": "",
    "task": "",
    "step": "",
    "turn": 0,
    "max_turns": 0,
    "total_steps": 0,
    "started_at": "",
    "finished_at": "",
    "result_status": "",
    "result_message": "",
}


# ── Direct Agent Prompt ───────────────────────────────────────────────
DIRECT_AGENT_PROMPT = (
    "Full-stack developer editing a branch copy of a live platform.\n\n"
    "WHERE YOU ARE:\n"
    "- You edit files at /home/aeli/projects/aelidirect_branch/ (the branch)\n"
    "- This is a full copy of prod at /home/aeli/projects/aelidirect/\n"
    "- Prod runs on port 10100. Branch runs on port 10101.\n"
    "- You run on prod (10100). Your file edits go to the branch directory.\n"
    "- restart_platform() restarts branch (10101). Prod is unaffected.\n"
    "- User project pods run on ports 11001-11099.\n\n"
    "DIRECTORY STRUCTURE (branch root — all paths relative to here):\n"
    "  backend/app.py            — FastAPI entry, config/project routes, serve frontend\n"
    "  backend/state.py          — Shared config, agent prompt, tool definitions\n"
    "  backend/pipeline.py       — Chat pipeline (stream endpoint, agent loop, TD review)\n"
    "  backend/heartbeat.py      — Todo scheduler, heartbeat routes, todo CRUD routes\n"
    "  backend/platform_routes.py — Branch status, wipe, deploy to prod\n"
    "  backend/history.py        — Conversation save/load/summarize\n"
    "  backend/td.py             — TD analysis endpoints and reports\n"
    "  backend/docs.py           — Auto-doc regeneration (SPEC, CONTEXT_MAP, DATA_FLOW, SITE_MAP)\n"
    "  backend/tools.py          — File tool executors (read_file, patch_file, edit_file, read_lines)\n"
    "  backend/llm_client.py     — LLM API client (OpenRouter, MiniMax)\n"
    "  backend/pod.py            — Podman container lifecycle (build, run, health check)\n"
    "  backend/direct_todo.py    — Todo CRUD + heartbeat config persistence\n"
    "  backend/constants.py      — All shared constants (ports, paths, limits)\n"
    "  backend/test_agent.py     — Automated test runner\n"
    "  frontend/index.html       — Full standalone UI (single HTML file)\n"
    "  SPEC.md                   — Platform specification (at ROOT)\n"
    "  SITE_MAP.md               — File/function tree (at ROOT)\n"
    "  CONTEXT_MAP.md            — API/data format reference (at ROOT)\n"
    "  DATA_FLOW.md              — Data flow diagrams (at ROOT)\n\n"
    "IMPORTANT:\n"
    "- NEVER look in projects/ subdirectory — user project data, not platform source.\n"
    "- All platform source and docs are at ROOT level.\n"
    "- /api/platform/docs reads docs from the server's own root (each server reads its own).\n"
    "- /api/projects/{dir}/docs reads from projects/{dir}/ — different path, different content.\n\n"
    "LIFECYCLE:\n"
    "  1. User clicks Wipe Branch → prod copies everything to branch\n"
    "  2. User sends chat → you edit branch files\n"
    "  3. You call restart_platform() → branch restarts on 10101\n"
    "  4. User tests on 10101\n"
    "  5. User clicks Deploy to Prod → branch source + docs copied to prod, prod restarts\n\n"
    "FRONTEND UI (frontend/index.html):\n"
    "  Project bar buttons (class='ctx-map-btn'):\n"
    "    - Spec → onclick='showSpec(state.projectDir)' → modal via /api/projects/{dir}/docs\n"
    "    - Context Map → onclick='showContextMap(state.projectDir)' → modal via /api/projects/{dir}/docs\n"
    "    - Erase History → onclick='eraseHistory()' → DELETE /api/direct/history/{dir}\n"
    "  Sidebar buttons:\n"
    "    - New Project → createNewProject()\n"
    "    - TD Analysis → toggleTDView()\n"
    "    - Config → toggleConfig()\n"
    "  Modal pattern: ctx-modal-backdrop > ctx-modal > ctx-modal-header (h3 + close btn) + ctx-modal-body\n"
    "  To add a button: follow the exact same pattern as showSpec/showContextMap.\n\n"
    "EDITING:\n"
    "- read_file/read_lines to read. patch_file to edit existing. edit_file for new files.\n"
    "- patch_file uses text matching, not line numbers (they shift after edits).\n"
    "- After edits: bash('python3 -m py_compile backend/FILE.py') then restart_platform()\n"
    "- git_commit after successful changes.\n\n"
    "MEMORY:\n"
    "memory_save compact one-liners. Key: 'log_YYYY-MM-DD_slug'. Overwrite existing. Save at end.\n"
)

# ── State & storage dirs ──────────────────────────────────────────────
_direct_state = {"project_dir": None, "project_name": "", "port": 0}
# Storage dirs and limits imported from constants


def _estimate_tokens(text: str) -> int:
    return len(text) // CHARS_PER_TOKEN


# ── Tool definitions for direct mode ──────────────────────────────────
# Filter out exploration tools — agent has site_map, shouldn't need these.
# Keep read_file, read_lines, patch_file, edit_file (still needed for targeted reads/edits).
_SKIP_TOOLS = {"read_project", "grep_code", "list_files", "read_file_tail"}
_FILTERED_TOOL_DEFS = [t for t in TOOL_DEFINITIONS if t["function"]["name"] not in _SKIP_TOOLS]

DIRECT_TOOL_DEFS = _FILTERED_TOOL_DEFS + [
    {"type": "function", "function": {
        "name": "deploy_pod",
        "description": "Build and deploy the project as a live pod. Returns success/failure with details.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    }},
    {"type": "function", "function": {
        "name": "restart_platform",
        "description": "Restart the aelidirect platform server. Call this after editing any platform files (backend/*.py, frontend/index.html) so changes take effect. The page will reload automatically.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    }},
    {"type": "function", "function": {
        "name": "http_check",
        "description": "Make an HTTP GET request to the live pod and return status + response body.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string", "description": "URL path (e.g. '/', '/health')"},
        }, "required": ["path"]},
    }},
    {"type": "function", "function": {
        "name": "bash",
        "description": "Run any shell command. Use for: python3, git, curl, pip, ls, cat, grep, tests, etc.",
        "parameters": {"type": "object", "properties": {
            "command": {"type": "string", "description": "Shell command to execute"},
        }, "required": ["command"]},
    }},
    {"type": "function", "function": {
        "name": "git_status",
        "description": "Run git status in the project directory. Auto-initializes git if needed.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    }},
    {"type": "function", "function": {
        "name": "git_diff",
        "description": "Show git diff of uncommitted changes in the project.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    }},
    {"type": "function", "function": {
        "name": "git_log",
        "description": "Show recent git commits in the project.",
        "parameters": {"type": "object", "properties": {
            "n": {"type": "integer", "description": "Number of commits to show (default: 5)"},
        }, "required": []},
    }},
    {"type": "function", "function": {
        "name": "git_commit",
        "description": "Stage all changes and commit with a message.",
        "parameters": {"type": "object", "properties": {
            "message": {"type": "string", "description": "Commit message"},
        }, "required": ["message"]},
    }},
    {"type": "function", "function": {
        "name": "memory_save",
        "description": "Save a piece of information to persistent memory. Survives across conversations.",
        "parameters": {"type": "object", "properties": {
            "key": {"type": "string", "description": "Memory key"},
            "content": {"type": "string", "description": "Content to remember"},
        }, "required": ["key", "content"]},
    }},
    {"type": "function", "function": {
        "name": "memory_load",
        "description": "Load a previously saved memory by key.",
        "parameters": {"type": "object", "properties": {
            "key": {"type": "string", "description": "Memory key to load"},
        }, "required": ["key"]},
    }},
    {"type": "function", "function": {
        "name": "memory_list",
        "description": "List all saved memory keys.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    }},
    {"type": "function", "function": {
        "name": "test_agent",
        "description": (
            "Run the automated test agent. Two phases: (1) Plans tests by reading all source code "
            "in one batch and asking the LLM to generate a test plan based on scope + context, "
            "(2) Executes tests — API tests via httpx, browser tests via Playwright, unit tests "
            "via direct import. Can auto-fix: failures feed back through the chat pipeline, then "
            "tests re-run to verify. Use this to verify features work, catch bugs, or validate fixes."
        ),
        "parameters": {"type": "object", "properties": {
            "scope": {
                "type": "string",
                "description": "What to test (e.g. 'heartbeat countdown timer', 'chat pipeline', 'todo CRUD')",
            },
            "context": {
                "type": "string",
                "description": "Context: what's broken, what was reported, recent changes. Helps focus the test plan.",
            },
            "phase": {
                "type": "string",
                "description": "Which phase: 'plan' (just generate test plan), 'run' (execute existing plan), 'full' (plan + run + fix loop). Default: 'full'.",
                "enum": ["plan", "run", "full"],
            },
            "fix_loop": {
                "type": "boolean",
                "description": "If true (default), failures auto-feed back to chat for fix, then re-test. Set false for report-only.",
            },
        }, "required": ["scope"]},
    }},
]


# ── Per-todo TD Review Prompt ─────────────────────────────────────────
TODO_TD_REVIEW_PROMPT = (
    "You are a Technical Director reviewing an AI agent's execution of a task.\n\n"
    "You receive: Original Task, Agent Plan, Code Changes Made, Agent Response, and Test Results.\n"
    "Review the ORIGINAL TASK completion — not just test results.\n\n"
    "## Scores (1-10)\n"
    "- **Completion**: Did agent accomplish what was asked? Focus on original task, not test infra.\n"
    "- **Code Quality**: Clean, maintainable, follows existing patterns?\n"
    "- **Correctness**: Does it work? Root cause fixed or just a workaround?\n"
    "- **Verification**: Tests ran? What did they cover? Any gaps?\n\n"
    "## Issues Found\n"
    "For each: Issue, Root Cause, Severity (Critical/Major/Minor), Impact.\n\n"
    "## What Worked Well\n\n"
    "## Recommendations\n\n"
    "## Verdict\n"
    "Exactly one status line (parsed programmatically):\n"
    "STATUS: PASS — task fully completed, tests pass, no issues\n"
    "STATUS: PARTIAL — completed with errors, missing pieces, or workarounds\n"
    "STATUS: FAIL — not completed, fabricated results, or critical errors\n"
    "STATUS: INCOMPLETE — stopped halfway or only partial work\n\n"
    "1-2 sentence summary after STATUS. Be specific. Don't sugarcoat.\n\n"
    "OUTPUT FORMAT: Plain markdown only. No <think> blocks. No [TOOL_CALL] blocks. "
    "No code execution. Just write your review as text."
)
