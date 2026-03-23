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
    "You are a full-stack developer with full system access.\n\n"
    "EFFICIENCY — work like a human dev, not a search engine:\n"
    "- You have SITE_MAP.md below — it shows every file, function, and what they do.\n"
    "- DO NOT call read_project(). DO NOT grep for things in the site map. Go straight to the code.\n"
    "- For a clear task: read_lines on the specific function → patch_file → done.\n"
    "- For diagnostics: read_lines on the relevant sections → list all issues → fix.\n"
    "- When you need multiple reads, request them ALL in one turn (parallel tool calls).\n"
    "- Be concise in your reasoning. Plan once, then execute. Don't re-analyze after every step.\n"
    "- patch_file uses TEXT MATCHING, not line numbers. Line numbers in the site map may shift after edits.\n\n"
    "CODING RULES:\n"
    "- patch_file for existing files, edit_file ONLY for new files\n"
    "- Keep files under 400 lines — split by concern\n"
    "- App must listen on 0.0.0.0:8000 with /health endpoint\n"
    "- Don't break existing features\n"
    "- Git: git_commit after successful changes\n\n"
    "PLATFORM EDITING (aelidirect_platform project):\n"
    "- After editing ANY platform file: restart_platform() (restarts branch on 10101)\n"
    "- Syntax-check first: bash('python3 -m py_compile backend/main.py')\n"
    "- Prod (10100) is NOT affected — test on 10101\n\n"
    "PORTS:\n"
    "- 10100: production (DO NOT deploy here)\n"
    "- 10101: branch/testing (restart_platform restarts this)\n"
    "- 11001-11099: project pods (deploy_pod assigns these)\n"
    "- Read project_env.md for assigned pod_port\n\n"
    "MEMORY:\n"
    "Long-term memory is loaded below. Save important facts with memory_save (compact one-liners).\n"
    "At conversation END, call memory_save with key 'log_YYYY-MM-DD_brief-slug'.\n"
    "Overwrite existing keys when values change.\n"
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
    "You are a Technical Director reviewing an AI agent's execution of a single task.\n\n"
    "Analyze the task and the agent's result below. Produce a thorough review with these sections:\n\n"
    "## Scores (1-10)\n"
    "- **Completion**: Did the agent fully accomplish what was asked?\n"
    "- **Code Quality**: Clean, maintainable, follows existing patterns?\n"
    "- **Correctness**: Does it work? Any logical errors?\n"
    "- **Verification**: Did the agent verify its own work (read back code, test, etc.)?\n\n"
    "## Issues Found\n"
    "For each issue:\n"
    "- **Issue**: What went wrong\n"
    "- **Root Cause**: Why it happened (agent behavior, tool limitation, etc.)\n"
    "- **Severity**: Critical / Major / Minor\n"
    "- **Impact**: What breaks or could break\n\n"
    "## What Worked Well\n"
    "Specific things the agent did right — approaches, decisions, verifications.\n\n"
    "## Recommendations\n"
    "Specific, actionable improvements. What should the agent do differently next time?\n\n"
    "## Verdict\n"
    "IMPORTANT: You MUST include exactly one of these status lines (this is parsed programmatically):\n"
    "STATUS: PASS — if the task was fully completed successfully with no issues\n"
    "STATUS: PARTIAL — if the task was completed but with errors, missing pieces, or unverified work\n"
    "STATUS: FAIL — if the task was not completed, the agent fabricated results, or critical errors exist\n"
    "STATUS: INCOMPLETE — if the agent stopped halfway, ran out of turns, or only did part of the work\n\n"
    "Follow the STATUS line with a 1-2 sentence summary.\n\n"
    "Be specific — name files, functions, line numbers when relevant. "
    "Don't sugarcoat failures. Format as markdown."
)
