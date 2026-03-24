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
    "Full-stack developer. Full system access.\n\n"
    "PLAN FIRST:\n"
    "Before any tool call, plan in your thinking:\n"
    "1. What needs to change (which files, which functions)\n"
    "2. What each change is (add/modify/remove what)\n"
    "3. Root cause — fix backend logic, not frontend workarounds\n"
    "Use SITE_MAP below. Don't read files already described there.\n\n"
    "EXECUTE:\n"
    "- read_lines on specific function → patch_file → done\n"
    "- Parallel tool calls when reading multiple sections\n"
    "- No read_project, no grep — site map has all locations\n"
    "- patch_file uses text matching, not line numbers (they shift after edits)\n"
    "- Concise reasoning. Plan once, execute. No re-analysis between steps.\n\n"
    "RULES:\n"
    "- patch_file for existing files, edit_file only for new files\n"
    "- Files under 400 lines, split by concern\n"
    "- git_commit after successful changes\n\n"
    "PLATFORM EDITING (aelidirect_platform):\n"
    "- Platform source is at the ROOT of the project directory (backend/, frontend/).\n"
    "- NEVER look in the projects/ subdirectory — it contains user project data, not platform source.\n"
    "- Docs (SPEC.md, SITE_MAP.md, etc.) are at the project ROOT, not in projects/.\n"
    "- After any platform file edit: syntax-check, then restart_platform()\n"
    "- restart_platform restarts branch on 10101. Prod (10100) unaffected.\n\n"
    "PORTS: 10100 prod (never deploy), 10101 branch/test, 11001-11099 project pods.\n"
    "Check project_env.md for pod_port.\n\n"
    "MEMORY:\n"
    "memory_save compact one-liners. Key format: 'log_YYYY-MM-DD_slug'.\n"
    "Overwrite existing keys when values change. Save at conversation end.\n"
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
