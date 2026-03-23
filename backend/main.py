"""
aelidirect — Standalone direct-mode agent server.

Single agent, one conversation, all tools. No pipeline, no handoffs.
Completely standalone — no dependency on aelimini.
"""

import json
import asyncio
import re
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from starlette.responses import Response

from llm_client import call_llm, extract_response, LLMError
from tools import TOOL_DEFINITIONS, execute_tool
from pod import spin_up_pod, http_get, get_available_port

app = FastAPI(title="aelidirect")

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

CONFIG_FILE = Path(__file__).parent / ".config.json"
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
    "TOOLS:\n"
    "File ops: list_files, read_file, read_lines, read_file_tail, grep_code, "
    "read_project, edit_file (new files), patch_file (existing files)\n"
    "System: bash(command) — run ANY shell command (python3, git, curl, pip, ls, cat, grep, tests, etc.)\n"
    "Deploy: deploy_pod() — build and deploy to a live pod\n"
    "Test: http_check(path) — test live endpoints\n"
    "Git: git_status(), git_diff(), git_log(n), git_commit(message)\n"
    "Long-term memory: memory_save(key, content), memory_load(key), memory_list()\n\n"
    "APPROACH — match depth to the task:\n"
    "For DIAGNOSTIC tasks ('what's wrong', 'why is X broken', 'find bugs', 'review'):\n"
    "  1. Call read_project() first — it reads all code in one call if the project fits,\n"
    "     or returns a file listing with sizes if too large (then read key files individually)\n"
    "  2. LIST ALL issues found — enumerate every bug, every problem, miss nothing\n"
    "  3. Be skeptical — don't rationalize code as 'intentional' without evidence\n"
    "  4. Only THEN plan and apply fixes\n"
    "  5. After fixing, verify each fix specifically, not just HTTP 200\n"
    "For CLEAR tasks ('change X to Y', 'add feature Z', 'deploy'):\n"
    "  1. Read the relevant code (SPEC.md, target files — or read_project() if small)\n"
    "  2. Plan briefly\n"
    "  3. Code the change\n"
    "  4. Verify and deploy\n"
    "For LARGE PROJECTS (when read_project says 'too large'):\n"
    "  1. Read the file listing from read_project to understand structure\n"
    "  2. Read SPEC.md, CONTEXT_MAP.md, and entry points first\n"
    "  3. Use grep_code to find patterns related to the task\n"
    "  4. Read specific files that are relevant\n"
    "  5. Don't try to read everything — focus on what the task needs\n\n"
    "TOOL PREFERENCES — use the right tool for the job:\n"
    "- ALWAYS use read_file or read_project to read files — NEVER bash('cat ...') or bash('head ...')\n"
    "- ALWAYS use patch_file to edit existing files — NEVER bash('sed ...') or bash('echo ... > ...')\n"
    "- ALWAYS use grep_code to search project files — NEVER bash('grep ...')\n"
    "- Use bash ONLY for: running commands (python3, pip, curl, git), checking processes, installing packages\n"
    "- Read-only tools (read_file, grep_code, list_files, read_project) are FREE — no turn cost. Use them generously.\n\n"
    "CODING RULES:\n"
    "- patch_file for existing files, edit_file ONLY for new files\n"
    "- Keep files under 400 lines — split by concern\n"
    "- App must listen on 0.0.0.0:8000 with /health endpoint\n"
    "- Don't break existing features (read SPEC.md)\n"
    "- Git: git_commit after successful changes\n\n"
    "PORTS — know what runs where:\n"
    "- Port 10100: production aelidirect (DO NOT deploy here)\n"
    "- Port 10101: branch/testing aelidirect (restart_platform restarts this)\n"
    "- Ports 11001-11099: project pods (deploy_pod assigns these)\n"
    "- ALWAYS read project_env.md to check the assigned pod_port — NEVER guess ports\n"
    "- After deploy_pod, the URL is http://{pod_host}:{pod_port} — read it from the deploy result\n\n"
    "PLATFORM EDITING (when working on the 'aelidirect_platform' project):\n"
    "- The platform files are in backend/ and frontend/\n"
    "- After editing ANY platform file, you MUST call restart_platform() — this restarts the BRANCH on 10101\n"
    "- Test your changes on port 10101 before promoting to prod\n"
    "- Always syntax-check Python files before restarting: bash('python3 -m py_compile backend/main.py')\n"
    "- If restart fails, check the error and fix — prod (10100) is NOT affected\n\n"
    "VERIFICATION:\n"
    "- bash('python3 -m py_compile file.py') to syntax check\n"
    "- deploy_pod() then http_check to verify (for regular projects)\n"
    "- restart_platform() then http_check on port 10101 (for platform edits)\n"
    "- For bug fixes: verify each specific bug is resolved, not just that the server responds\n"
    "- Read the patched code back to confirm the fix is correct\n\n"
    "MEMORY:\n"
    "You have two kinds of memory:\n"
    "1. LONG-TERM MEMORY — loaded automatically every conversation (shown below if any exist). "
    "Use memory_save to persist important facts across ALL future conversations. "
    "ALWAYS save after making significant changes. Keep saves VERY compact — "
    "one-liners preferred, e.g. 'token limit: 16k', 'fixed: keypress start game bug', "
    "'arch: FastAPI+HTMX, port 11001'. Never save verbose explanations.\n"
    "2. SHORT-TERM MEMORY — recent conversation history is loaded automatically. "
    "You can see what was discussed and done in previous conversations. "
    "This is managed by the system — no action needed from you.\n\n"
    "At the END of every conversation, you MUST call memory_save to record what you did. "
    "Key name format: 'log_YYYY-MM-DD_brief-slug' for session logs, or a descriptive key "
    "for facts (e.g. 'architecture', 'known_bugs', 'config'). "
    "Overwrite existing keys when the value changes rather than creating new ones."
)

# ── State & storage dirs ──────────────────────────────────────────────
_direct_state = {"project_dir": None, "project_name": "", "port": 0}
_DIRECT_MEMORY_DIR = Path(__file__).parent / ".direct_memory"
_DIRECT_MEMORY_DIR.mkdir(exist_ok=True)
_DIRECT_CONVERSATIONS_DIR = Path(__file__).parent / ".direct_conversations"
_DIRECT_CONVERSATIONS_DIR.mkdir(exist_ok=True)

_CONVERSATION_HISTORY_LIMIT = 50
_CONVERSATION_TOKEN_BUDGET = 50_000
_CHARS_PER_TOKEN = 4


def _estimate_tokens(text: str) -> int:
    return len(text) // _CHARS_PER_TOKEN


def _save_conversation(project_name: str, user_message: str, messages: list, test_evidence: list = None):
    from datetime import datetime, timezone
    conv_dir = _DIRECT_CONVERSATIONS_DIR / project_name
    conv_dir.mkdir(exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")

    full_messages = []
    for m in messages:
        role = m.get("role", "")
        if role == "system":
            continue
        if role == "user":
            full_messages.append({"role": "user", "content": m.get("content", "")})
        elif role == "assistant":
            content = m.get("content", "") or ""
            tool_calls = m.get("tool_calls", [])
            entry = {"role": "assistant"}
            if content.strip():
                entry["content"] = content
            if tool_calls:
                entry["tools"] = [
                    f"{tc['function']['name']}({tc['function'].get('arguments', '')})"
                    for tc in tool_calls
                ]
            full_messages.append(entry)
        elif role == "tool":
            full_messages.append({
                "role": "tool",
                "name": m.get("name", ""),
                "result": m.get("content", ""),
            })

    conv = {"timestamp": ts, "user_message": user_message, "messages": full_messages, "llm_summary": None}
    if test_evidence:
        conv["test_evidence"] = test_evidence
    (conv_dir / f"{ts}.json").write_text(json.dumps(conv, indent=1))


def _load_conversation_history(project_name: str, prov: dict = None, selected: str = None) -> str:
    conv_dir = _DIRECT_CONVERSATIONS_DIR / project_name
    if not conv_dir.exists():
        return ""
    conv_files = sorted(conv_dir.glob("*.json"), key=lambda p: p.name)
    if not conv_files:
        return ""
    if len(conv_files) > _CONVERSATION_HISTORY_LIMIT:
        for old_file in conv_files[:-_CONVERSATION_HISTORY_LIMIT]:
            old_file.unlink()
        conv_files = conv_files[-_CONVERSATION_HISTORY_LIMIT:]

    conversations = []
    for f in conv_files:
        try:
            conv = json.loads(f.read_text())
            conv["_path"] = str(f)
            conversations.append(conv)
        except (json.JSONDecodeError, OSError):
            continue
    if not conversations:
        return ""

    def _conv_to_text(conv):
        summary = conv.get("llm_summary") or conv.get("summary")
        if summary:
            return f"[{conv['timestamp']}] {summary}"
        lines = [f"[{conv['timestamp']}] User: {conv.get('user_message', '?')}"]
        for m in (conv.get("messages") or []):
            if m.get("role") == "assistant" and m.get("content"):
                lines.append(f"  Assistant: {m['content'][:800]}")
            elif m.get("role") == "assistant" and m.get("tools"):
                lines.append(f"  Tools: {', '.join(m['tools'][:8])}")
        return "\n".join(lines)

    total_text = "\n\n".join(_conv_to_text(c) for c in conversations)
    total_tokens = _estimate_tokens(total_text)

    if total_tokens > _CONVERSATION_TOKEN_BUDGET and prov and prov.get("api_key"):
        _summarize_old_conversations(conversations, prov, selected)
        total_text = "\n\n".join(_conv_to_text(c) for c in conversations)

    return total_text


def _summarize_old_conversations(conversations: list, prov: dict, selected: str):
    unsummarized = [c for c in conversations[:-10]
                    if not c.get("llm_summary") and not c.get("summary")]
    if not unsummarized:
        return
    batch = unsummarized[:10]
    batch_text = ""
    for conv in batch:
        lines = [f"[{conv['timestamp']}] User: {conv.get('user_message', '?')}"]
        for m in (conv.get("messages") or []):
            if m.get("role") == "assistant" and m.get("content"):
                lines.append(f"  Assistant: {m['content'][:800]}")
            elif m.get("role") == "assistant" and m.get("tools"):
                lines.append(f"  Tools: {', '.join(m['tools'][:8])}")
            elif m.get("role") == "tool" and m.get("result"):
                lines.append(f"  Tool result ({m.get('name', '?')}): {m['result'][:300]}")
        batch_text += "\n".join(lines) + "\n---\n"

    try:
        result = call_llm(
            selected, prov["api_key"], prov["base_url"], prov["model"],
            [
                {"role": "system", "content": (
                    "You are summarizing developer conversations for future LLM context.\n\n"
                    "For EACH conversation delimited by ---:\n"
                    "1. List EVERY bug found (with root cause)\n"
                    "2. List EVERY fix applied (with what changed)\n"
                    "3. List EVERY feature added or config changed\n"
                    "4. Note any deploy/test results\n\n"
                    "Format: one conversation per line, starting with the timestamp.\n"
                    "Be specific — name functions, files, line numbers, error types.\n"
                    "DO NOT merge or skip items. If 3 bugs were found, list all 3.\n\n"
                    "Max 2000 chars per summary if needed, but keep it concise — don't pad. "
                    "Accuracy over brevity — never drop a bug or fix."
                )},
                {"role": "user", "content": batch_text},
            ],
            tools=None, temperature=0.2,
        )
        parsed = extract_response(result)
        summaries = [s.strip() for s in parsed["content"].strip().split("\n") if s.strip()]
        for i, conv in enumerate(batch):
            summary = summaries[i] if i < len(summaries) else f"[{conv['timestamp']}] (summarized)"
            if not summary.startswith("["):
                summary = f"[{conv['timestamp']}] {summary}"
            conv["llm_summary"] = summary
            conv_path = conv.get("_path")
            if conv_path:
                save_data = json.loads(Path(conv_path).read_text())
                save_data["llm_summary"] = summary
                Path(conv_path).write_text(json.dumps(save_data, indent=1))
    except Exception:
        pass


# ── Tool definitions for direct mode ──────────────────────────────────
DIRECT_TOOL_DEFS = TOOL_DEFINITIONS + [
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


# ══════════════════════════════════════════════════════════════════════
# API ENDPOINTS
# ══════════════════════════════════════════════════════════════════════

@app.get("/api/config")
async def get_config():
    safe = {}
    for pid, p in config["providers"].items():
        key = p.get("api_key", "")
        safe[pid] = {
            "name": p["name"], "model": p["model"],
            "base_url": p.get("base_url", ""),
            "api_key_masked": (key[:8] + "..." + key[-4:]) if len(key) > 12 else ("***" if key else ""),
            "has_key": bool(key),
        }
    return {"providers": safe, "selected": config["selected"], "pod_host": config["pod_host"]}


@app.post("/api/config")
async def save_config_endpoint(request: Request):
    data = await request.json()
    if "selected" in data:
        config["selected"] = data["selected"]
    if "api_key" in data and "provider" in data:
        pid = data["provider"]
        if pid in config["providers"]:
            config["providers"][pid]["api_key"] = data["api_key"]
    if "model" in data and "provider" in data:
        pid = data["provider"]
        if pid in config["providers"]:
            config["providers"][pid]["model"] = data["model"]
    if "pod_host" in data:
        config["pod_host"] = data["pod_host"].strip() or "localhost"
    _save_config()
    return {"ok": True}


@app.post("/api/config/provider")
async def save_provider(request: Request):
    data = await request.json()
    pid = data.get("id", "").strip()
    if not pid:
        return {"error": "Provider ID is required"}
    existing = config["providers"].get(pid, {})
    config["providers"][pid] = {
        "name": data.get("name", existing.get("name", pid)),
        "model": data.get("model", existing.get("model", "")),
        "base_url": data.get("base_url", existing.get("base_url", "")),
        "api_key": data.get("api_key", existing.get("api_key", "")),
    }
    _save_config()
    return {"ok": True}


@app.delete("/api/config/provider/{provider_id}")
async def delete_provider(provider_id: str):
    if provider_id not in config["providers"]:
        return {"error": "Provider not found"}
    if provider_id == config["selected"]:
        return {"error": "Cannot delete the active provider"}
    del config["providers"][provider_id]
    _save_config()
    return {"ok": True}


@app.get("/api/projects")
async def list_projects():
    from tools import PROJECTS_ROOT, read_project_env
    projects = []
    if PROJECTS_ROOT.exists():
        for d in sorted(PROJECTS_ROOT.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            if d.is_dir() and not d.name.startswith("."):
                env = read_project_env(d)
                file_count = sum(1 for f in d.rglob("*") if f.is_file() and not f.name.startswith("."))
                projects.append({
                    "dir_name": d.name,
                    "project_name": env.get("project_name", d.name),
                    "file_count": file_count,
                })
    return {"projects": projects}


@app.get("/api/projects/{dir_name}/docs")
async def get_project_docs(dir_name: str):
    from tools import PROJECTS_ROOT
    project_dir = PROJECTS_ROOT / dir_name
    docs = {}
    for name in ("SPEC.md", "CONTEXT_MAP.md", "DATA_FLOW.md"):
        path = project_dir / name
        docs[name] = path.read_text() if path.exists() else None
    return docs


@app.get("/api/platform/docs")
async def get_platform_docs():
    """Get the platform's own documentation (SPEC, CONTEXT_MAP, DATA_FLOW)."""
    platform_root = Path(__file__).parent.parent
    docs = {}
    for name in ("SPEC.md", "CONTEXT_MAP.md", "DATA_FLOW.md"):
        path = platform_root / name
        docs[name] = path.read_text() if path.exists() else None
    return docs


# ── Branch vs Prod comparison ──────────────────────────────────────────
_PROD_ROOT = Path(__file__).parent.parent
_BRANCH_ROOT = Path("/home/aeli/projects/aelidirect_branch")
_IS_BRANCH = _PROD_ROOT.resolve() == _BRANCH_ROOT.resolve()
_PLATFORM_SOURCE_FILES = [
    "frontend/index.html",
    "backend/main.py",
    "backend/tools.py",
    "backend/direct_todo.py",
    "backend/llm_client.py",
    "backend/pod.py",
]


@app.get("/api/platform/branch-status")
async def get_branch_status():
    """Compare branch (10101) vs prod (10100) source files."""
    if _IS_BRANCH:
        return {"has_changes": False, "is_branch": True}
    if not _BRANCH_ROOT.exists():
        return {"has_changes": False, "error": "Branch directory not found"}

    import hashlib
    changes = []
    for rel in _PLATFORM_SOURCE_FILES:
        prod_file = _PROD_ROOT / rel
        branch_file = _BRANCH_ROOT / rel
        prod_exists = prod_file.exists()
        branch_exists = branch_file.exists()

        if not prod_exists and not branch_exists:
            continue
        if prod_exists != branch_exists:
            changes.append({"file": rel, "status": "added" if branch_exists else "removed"})
            continue

        prod_hash = hashlib.md5(prod_file.read_bytes()).hexdigest()
        branch_hash = hashlib.md5(branch_file.read_bytes()).hexdigest()
        if prod_hash != branch_hash:
            prod_mtime = prod_file.stat().st_mtime
            branch_mtime = branch_file.stat().st_mtime
            changes.append({
                "file": rel,
                "status": "modified",
                "branch_newer": branch_mtime > prod_mtime,
                "prod_mtime": prod_mtime,
                "branch_mtime": branch_mtime,
            })

    return {
        "has_changes": len(changes) > 0,
        "changes": changes,
        "branch_path": str(_BRANCH_ROOT),
    }


_PLATFORM_DATA_DIRS = [
    "backend/.direct_conversations",
    "backend/.direct_heartbeats",
    "backend/.direct_todos",
    "backend/.direct_memory",
    "backend/.td_reports",
    "projects",
]
_PLATFORM_DATA_FILES = [
    "backend/.config.json",
    "backend/.ports.json",
    "SPEC.md",
    "CONTEXT_MAP.md",
    "DATA_FLOW.md",
]


@app.get("/api/platform/heartbeat-progress")
async def get_heartbeat_progress():
    return _heartbeat_progress


@app.post("/api/platform/branch-wipe")
async def wipe_branch():
    """Reset branch to match prod — copies source, data, and config."""
    if _IS_BRANCH:
        return {"ok": False, "error": "Cannot wipe from branch server — use prod (10100)"}
    if not _BRANCH_ROOT.exists():
        return {"ok": False, "error": "Branch directory not found"}
    # Block wipe while main is actively editing branch files
    if _heartbeat_progress.get("active") and _heartbeat_progress.get("project") == "aelidirect_platform":
        return {"ok": False, "error": "Agent is actively editing branch files — wait for completion"}

    import shutil
    wiped = []
    errors = []

    # 1. Source files
    for rel in _PLATFORM_SOURCE_FILES:
        try:
            prod_file = _PROD_ROOT / rel
            branch_file = _BRANCH_ROOT / rel
            if prod_file.exists():
                branch_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(prod_file), str(branch_file))
                wiped.append(rel)
        except Exception as e:
            errors.append(f"{rel}: {e}")

    # 2. Data directories (full sync, preserve symlinks)
    for rel in _PLATFORM_DATA_DIRS:
        try:
            prod_dir = _PROD_ROOT / rel
            branch_dir = _BRANCH_ROOT / rel
            if prod_dir.exists():
                if branch_dir.exists():
                    shutil.rmtree(str(branch_dir))
                shutil.copytree(str(prod_dir), str(branch_dir), symlinks=True)
                wiped.append(rel + "/")
        except Exception as e:
            errors.append(f"{rel}: {e}")

    # 3. Data files
    for rel in _PLATFORM_DATA_FILES:
        try:
            prod_file = _PROD_ROOT / rel
            branch_file = _BRANCH_ROOT / rel
            if prod_file.exists():
                branch_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(prod_file), str(branch_file))
                wiped.append(rel)
        except Exception as e:
            errors.append(f"{rel}: {e}")

    # Sync file caches: main → branch
    from tools import file_cache_wipe_branch
    file_cache_wipe_branch()

    # Restart branch server so its file cache is cleared
    import subprocess
    try:
        subprocess.run(
            ["systemctl", "--user", "restart", "aelidirect-branch.service"],
            check=True, timeout=10,
        )
    except Exception as e:
        errors.append(f"branch restart: {e}")

    return {"ok": len(errors) == 0, "wiped": wiped, "errors": errors}


@app.post("/api/platform/branch-deploy")
async def deploy_branch():
    """Deploy branch source files to prod and restart the prod server."""
    if _IS_BRANCH:
        return {"ok": False, "error": "Cannot deploy from branch server — use prod (10100)"}
    # Block deploy while main is updating or branch is being tested
    if _heartbeat_progress.get("active"):
        return {"ok": False, "error": "Agent is running — wait for completion before deploying"}
    # Also check branch server's heartbeat
    hb = get_heartbeat("aelidirect_platform")
    if hb.get("running"):
        return {"ok": False, "error": "Branch is running a task — wait for completion before deploying"}
    if not _BRANCH_ROOT.exists():
        return {"ok": False, "error": "Branch directory not found"}

    import shutil, subprocess
    deployed = []
    errors = []

    for rel in _PLATFORM_SOURCE_FILES:
        try:
            branch_file = _BRANCH_ROOT / rel
            prod_file = _PROD_ROOT / rel
            if branch_file.exists():
                prod_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(branch_file), str(prod_file))
                deployed.append(rel)
        except Exception as e:
            errors.append(f"{rel}: {e}")

    if errors:
        return {"ok": False, "deployed": deployed, "errors": errors}

    # Sync file caches: branch → main (only after successful file copy)
    from tools import file_cache_deploy_to_main
    file_cache_deploy_to_main()

    # Restart prod server to pick up changes
    try:
        subprocess.run(
            ["systemctl", "--user", "restart", "aelidirect.service"],
            check=True, timeout=10,
        )
    except Exception as e:
        return {"ok": False, "deployed": deployed, "errors": [f"restart failed: {e}"]}

    return {"ok": True, "deployed": deployed}


@app.post("/api/direct/start")
async def direct_start(request: Request):
    from tools import PROJECTS_ROOT, init_project_dir, write_project_env, set_active_project, read_project_env

    data = await request.json()
    message = data.get("message", "")
    project_dir_name = data.get("project_dir", "")
    raw_name = data.get("project_name", "").strip()

    if project_dir_name:
        project_dir = PROJECTS_ROOT / project_dir_name
        if not project_dir.exists():
            return {"error": "Project not found"}
        env = read_project_env(project_dir)
        project_name = env.get("project_name", project_dir_name)
    else:
        # Use explicit project_name if provided, else derive from message
        if raw_name:
            project_name = raw_name
            safe_name = re.sub(r'[^a-zA-Z0-9_-]', '_', raw_name.lower())[:40]
        else:
            words = re.sub(r'[^a-zA-Z0-9 ]', '', message.lower()).split()[:4]
            safe_name = "_".join(words) if words else "project"
            project_name = " ".join(w.capitalize() for w in words) if words else "Project"
        project_dir = PROJECTS_ROOT / safe_name
        if project_dir.exists():
            i = 2
            while (PROJECTS_ROOT / f"{safe_name}_{i}").exists():
                i += 1
            safe_name = f"{safe_name}_{i}"
            project_dir = PROJECTS_ROOT / safe_name
        init_project_dir(project_dir)
        write_project_env(project_dir, project_name)
        project_dir_name = safe_name

    set_active_project(project_dir)
    env = read_project_env(project_dir)
    port = int(env.get("pod_port", 0)) or get_available_port(project_name) or 0

    _direct_state["project_dir"] = project_dir
    _direct_state["project_name"] = project_name
    _direct_state["port"] = port

    return {
        "project_dir": project_dir_name,
        "project_name": project_name,
        "port": port,
        "stream_url": f"/api/direct/stream?message={__import__('urllib.parse', fromlist=['quote']).quote(message)}&project_dir={project_dir_name}",
    }


@app.get("/api/direct/stream")
async def direct_stream(message: str, project_dir: str, auto_test: bool = False):
    from tools import PROJECTS_ROOT, set_active_project, read_project_env, file_cache_wipe_branch

    project_path = PROJECTS_ROOT / project_dir
    if not project_path.exists():
        return Response(content=json.dumps({"error": "Project not found"}), status_code=404)

    prov = _get_provider()
    if not prov["api_key"]:
        return Response(content=json.dumps({"error": "No API key configured"}), status_code=400)

    selected = config["selected"]

    # Platform self-editing: redirect to branch, auto-wipe if no testing in progress
    if project_dir == "aelidirect_platform" and _BRANCH_ROOT.exists():
        import hashlib
        branch_has_newer = False
        for rel in _PLATFORM_SOURCE_FILES:
            prod_f = _PROD_ROOT / rel
            branch_f = _BRANCH_ROOT / rel
            if prod_f.exists() and branch_f.exists():
                if hashlib.md5(branch_f.read_bytes()).hexdigest() != hashlib.md5(prod_f.read_bytes()).hexdigest():
                    if branch_f.stat().st_mtime > prod_f.stat().st_mtime:
                        branch_has_newer = True
                        break
        if not branch_has_newer:
            # Auto-wipe: copy prod → branch
            import shutil
            for rel in _PLATFORM_SOURCE_FILES:
                prod_f = _PROD_ROOT / rel
                branch_f = _BRANCH_ROOT / rel
                if prod_f.exists():
                    branch_f.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(str(prod_f), str(branch_f))
            file_cache_wipe_branch()
            import logging
            logging.getLogger("uvicorn").info("[platform] Auto-wiped branch from prod (no testing in progress)")
        # Agent works on branch files directly
        project_path = _BRANCH_ROOT

    set_active_project(project_path)

    env = read_project_env(PROJECTS_ROOT / project_dir)  # metadata stays in original project dir
    project_name = env.get("project_name", project_dir)
    port = int(env.get("pod_port", 0)) or _direct_state.get("port", 0)

    _direct_state["project_dir"] = project_path
    _direct_state["project_name"] = project_name
    _direct_state["port"] = port
    msg = message or ""

    async def event_generator():
        system_prompt = DIRECT_AGENT_PROMPT

        # Long-term memory
        mem_dir = _DIRECT_MEMORY_DIR / project_path.name
        if mem_dir.exists():
            memories = []
            for f in sorted(mem_dir.glob("*.md")):
                memories.append(f"[{f.stem}]: {f.read_text()[:500]}")
            if memories:
                system_prompt += "\n\n[LONG-TERM MEMORY]\n" + "\n".join(memories)

        # Short-term memory
        conv_history = await asyncio.to_thread(
            _load_conversation_history, project_path.name, prov, selected
        )
        if conv_history:
            system_prompt += "\n\n[RECENT CONVERSATION HISTORY]\n" + conv_history

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": msg},
        ]
        action_turns = 0
        max_turns = 80
        total_turns = 0
        _made_code_changes = False  # Track if agent wrote/edited files
        _test_fix_iteration = 0
        _max_test_fix = 3
        _test_evidence = []  # Collected for TD review

        try:
            while action_turns < max_turns:
                total_turns += 1
                yield sse_event("turn", {"turn": total_turns, "action_turns": action_turns, "max": max_turns})

                raw = await asyncio.to_thread(
                    call_llm, selected, prov["api_key"], prov["base_url"],
                    prov["model"], messages, DIRECT_TOOL_DEFS, 0.3,
                )
                parsed = extract_response(raw)

                if parsed["type"] == "text":
                    yield sse_event("response", {"content": parsed["content"]})

                    # ── TEST PHASE ──────────────────────────────────
                    # If auto_test enabled, agent made changes, and we have iterations left:
                    # run test agent, and if failures found, inject them back as user message
                    # with full context preserved and turn count reset.
                    if (auto_test and _made_code_changes
                            and _test_fix_iteration < _max_test_fix):
                        try:
                            from test_agent import plan_tests, run_tests, format_failures_as_message, load_source_batch

                            _test_fix_iteration += 1
                            yield sse_event("test_phase", {
                                "status": "planning",
                                "iteration": _test_fix_iteration,
                            })

                            # Build context from what the agent just did
                            _test_context = (
                                f"Task: {msg}\n"
                                f"Agent response: {parsed['content'][:1000]}\n"
                                f"Test iteration: {_test_fix_iteration}"
                            )
                            source_batch = await asyncio.to_thread(
                                load_source_batch, "platform"
                            )
                            plan = await plan_tests(
                                scope=msg,
                                context=_test_context,
                                source_batch=source_batch,
                            )

                            if not plan.get("error"):
                                tc_count = len(plan.get("test_cases", []))
                                yield sse_event("test_phase", {
                                    "status": "running",
                                    "test_count": tc_count,
                                    "iteration": _test_fix_iteration,
                                })

                                results = await run_tests(plan)
                                passed = sum(1 for r in results if r.get("status") == "pass")
                                failed = [r for r in results if r.get("status") in ("fail", "error")]

                                _test_evidence.append({
                                    "iteration": _test_fix_iteration,
                                    "plan_summary": plan.get("summary", ""),
                                    "total": len(results),
                                    "passed": passed,
                                    "failed": len(failed),
                                    "details": results,
                                })

                                if failed:
                                    failure_msg = format_failures_as_message(results, plan)
                                    yield sse_event("test_feedback", {
                                        "status": "failures_found",
                                        "passed": passed,
                                        "failed": len(failed),
                                        "iteration": _test_fix_iteration,
                                    })
                                    # Inject failures into same conversation —
                                    # LLM keeps all previous file reads + context
                                    messages.append({"role": "assistant", "content": parsed["content"]})
                                    messages.append({"role": "user", "content": failure_msg})
                                    action_turns = 0  # Reset turns for fix attempt
                                    continue  # Back to while loop
                                else:
                                    yield sse_event("test_phase", {
                                        "status": "all_passed",
                                        "passed": passed,
                                        "iteration": _test_fix_iteration,
                                    })
                        except Exception as _te:
                            import logging as _tlog
                            _tlog.getLogger("uvicorn").error(f"[test-phase] Error: {_te}")
                            yield sse_event("test_phase", {
                                "status": "error",
                                "error": str(_te)[:200],
                            })
                    # ── END TEST PHASE ──────────────────────────────

                    break

                if parsed["content"] and parsed["content"].strip():
                    yield sse_event("thinking", {"content": parsed["content"].strip()})

                assistant_msg = {"role": "assistant", "content": parsed["content"] or ""}
                assistant_msg["tool_calls"] = [
                    {"id": tc["id"], "type": "function",
                     "function": {"name": tc["function_name"], "arguments": json.dumps(tc["arguments"])}}
                    for tc in parsed["tool_calls"]
                ]
                messages.append(assistant_msg)

                all_readonly = all(_is_readonly_tool_call(tc) for tc in parsed["tool_calls"])

                for tc in parsed["tool_calls"]:
                    name = tc["function_name"]
                    args = tc["arguments"]
                    yield sse_event("tool_call", {"name": name, "args": args})

                    try:
                        if name == "deploy_pod" and project_path.name == "aelidirect_platform":
                            result = "ERROR: This is the platform itself — use restart_platform() instead of deploy_pod(). The platform runs as a systemd service, not a pod."
                        elif name == "deploy_pod":
                            from tools import write_project_env as _wpd
                            _env = read_project_env(project_path)
                            _port = int(_env.get("pod_port", 0)) or get_available_port(project_name) or 0
                            if _port:
                                _ver = int(_env.get("deploy_version", "0")) + 1
                                deploy_result = spin_up_pod(project_path, project_name, _port, _ver)
                                if deploy_result["success"]:
                                    _direct_state["port"] = _port
                                    _env2 = read_project_env(project_path)
                                    _extra = {k: v for k, v in _env2.items()
                                              if k not in ("project_name", "project_dir", "tech_stack", "os", "python", "pod_port", "deploy_version")}
                                    _extra["Pod Port"] = str(_port)
                                    _extra["Deploy Version"] = str(_ver)
                                    _wpd(project_path, _env2.get("project_name", project_name),
                                         _env2.get("tech_stack", "auto"), _extra if _extra else None)
                                    result = f"DEPLOYED: {_pod_url(_port)} (v{_ver})\nPod: {deploy_result['pod_name']}"
                                    yield sse_event("pod_url", {"url": _pod_url(_port)})
                                else:
                                    result = f"FAILED at {deploy_result['phase']}: {deploy_result['message']}\nLogs: {deploy_result.get('logs', '')[:500]}"
                            else:
                                result = "FAILED: No available ports"
                        elif name == "restart_platform":
                            import subprocess as _sp
                            try:
                                # Always restart the BRANCH (10101), never prod (10100)
                                # Prod is what we're running on — restarting it kills this conversation
                                r = _sp.run(
                                    ["systemctl", "--user", "restart", "aelidirect-branch"],
                                    capture_output=True, text=True, timeout=10,
                                )
                                if r.returncode == 0:
                                    import time as _time
                                    _time.sleep(2)
                                    # Verify branch came up
                                    _check = http_get(10101, "/")
                                    if _check.startswith("HTTP 200"):
                                        result = "Branch restarted on port 10101 and healthy. Test your changes there, then use TO PROD button when ready."
                                    else:
                                        result = f"Branch restarted but health check failed: {_check[:200]}. Check for syntax errors."
                                else:
                                    result = f"Branch restart failed: {r.stderr}"
                            except Exception as e:
                                result = f"Restart error: {e}"
                        elif name == "http_check":
                            _port = _direct_state.get("port", 0)
                            result = http_get(_port, args.get("path", "/")) if _port else "No pod running — call deploy_pod first"
                        elif name == "bash":
                            import subprocess as _sp
                            cmd = args.get("command", "")
                            try:
                                r = _sp.run(cmd, shell=True, capture_output=True, text=True, timeout=60, cwd=str(project_path))
                                result = f"exit code: {r.returncode}\n"
                                if r.stdout: result += f"stdout:\n{r.stdout[:3000]}\n"
                                if r.stderr: result += f"stderr:\n{r.stderr[:1000]}"
                                if not r.stdout and not r.stderr: result += "(no output)"
                            except _sp.TimeoutExpired:
                                result = "Command timed out (60s limit)"
                        elif name == "git_status":
                            import subprocess as _sp
                            if not (project_path / ".git").exists():
                                _sp.run(["git", "init"], cwd=str(project_path), capture_output=True)
                                _sp.run(["git", "add", "."], cwd=str(project_path), capture_output=True)
                                _sp.run(["git", "commit", "-m", "Initial commit"],
                                       cwd=str(project_path), capture_output=True,
                                       env={**__import__('os').environ, "GIT_AUTHOR_NAME": "aelidirect",
                                            "GIT_AUTHOR_EMAIL": "aelidirect@local",
                                            "GIT_COMMITTER_NAME": "aelidirect",
                                            "GIT_COMMITTER_EMAIL": "aelidirect@local"})
                            r = _sp.run(["git", "status"], cwd=str(project_path), capture_output=True, text=True, timeout=10)
                            result = r.stdout + r.stderr
                        elif name == "git_diff":
                            import subprocess as _sp
                            r = _sp.run(["git", "diff"], cwd=str(project_path), capture_output=True, text=True, timeout=10)
                            result = r.stdout[:5000] or "(no changes)"
                        elif name == "git_log":
                            import subprocess as _sp
                            n = int(args.get("n", 5))
                            r = _sp.run(["git", "log", "--oneline", f"-{n}"], cwd=str(project_path), capture_output=True, text=True, timeout=10)
                            result = r.stdout or "(no commits)"
                        elif name == "git_commit":
                            import subprocess as _sp
                            _commit_msg = args.get("message", "Update")
                            _sp.run(["git", "add", "."], cwd=str(project_path), capture_output=True)
                            r = _sp.run(["git", "commit", "-m", _commit_msg],
                                       cwd=str(project_path), capture_output=True, text=True, timeout=10,
                                       env={**__import__('os').environ, "GIT_AUTHOR_NAME": "aelidirect",
                                            "GIT_AUTHOR_EMAIL": "aelidirect@local",
                                            "GIT_COMMITTER_NAME": "aelidirect",
                                            "GIT_COMMITTER_EMAIL": "aelidirect@local"})
                            result = r.stdout + r.stderr
                        elif name == "memory_save":
                            key = args.get("key", "").replace("/", "_").replace("..", "")
                            content = args.get("content", "")
                            mem_dir = _DIRECT_MEMORY_DIR / project_path.name
                            mem_dir.mkdir(exist_ok=True)
                            (mem_dir / f"{key}.md").write_text(content)
                            result = f"Saved memory: {key} ({len(content)} chars)"
                        elif name == "memory_load":
                            key = args.get("key", "").replace("/", "_").replace("..", "")
                            mem_path = _DIRECT_MEMORY_DIR / project_path.name / f"{key}.md"
                            result = mem_path.read_text() if mem_path.exists() else f"Memory '{key}' not found"
                        elif name == "memory_list":
                            mem_dir = _DIRECT_MEMORY_DIR / project_path.name
                            if mem_dir.exists():
                                keys = [f.stem for f in sorted(mem_dir.glob("*.md"))]
                                result = "Saved memories:\n" + "\n".join(f"  - {k}" for k in keys) if keys else "No memories saved"
                            else:
                                result = "No memories saved"
                        elif name == "test_agent":
                            from test_agent import handle_test_agent
                            result = await handle_test_agent(args)
                        else:
                            result = execute_tool(name, args, project_dir=project_path)
                    except Exception as e:
                        result = f"Tool error in {name}: {e}"

                    yield sse_event("tool_result", {"name": name, "result": result[:2000]})
                    messages.append({"role": "tool", "tool_call_id": tc["id"], "content": result})

                    # Track if agent made code changes (for auto-test trigger)
                    if name in ("edit_file", "patch_file") and not result.startswith("ERROR"):
                        _made_code_changes = True

                if not all_readonly:
                    action_turns += 1

            yield sse_event("done", {
                "turns": total_turns,
                "action_turns": action_turns,
                "test_evidence": _test_evidence if _test_evidence else None,
            })
            try:
                _save_conversation(project_dir, msg, messages, test_evidence=_test_evidence)
                # Regenerate docs in background after chat completion
                loop = asyncio.get_event_loop()
                loop.create_task(_regenerate_docs())
                # Auto-restart branch server if we edited platform files
                if project_path.resolve() == _BRANCH_ROOT.resolve():
                    import subprocess
                    try:
                        subprocess.run(["systemctl", "--user", "restart", "aelidirect-branch.service"],
                                       check=True, timeout=10)
                    except Exception:
                        pass
            except Exception:
                pass

        except Exception as e:
            import traceback
            yield sse_event("error", {"message": str(e), "traceback": traceback.format_exc()})
            try:
                _save_conversation(project_dir, msg, messages)
            except Exception:
                pass

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ── Todo + Heartbeat endpoints ────────────────────────────────────────
from direct_todo import (
    add_todo, update_todo as update_direct_todo, delete_todo,
    get_todos, get_pending_todos, get_todo, set_todo_review,
    get_heartbeat, save_heartbeat, record_heartbeat_run,
)


@app.get("/api/direct/todos/{project_dir}")
async def api_get_todos(project_dir: str):
    return {"todos": get_todos(project_dir)}


@app.post("/api/direct/todos/{project_dir}")
async def api_add_todo(project_dir: str, request: Request):
    data = await request.json()
    return {"ok": True, "todo": add_todo(project_dir, data.get("task", ""), data.get("category", "feature"))}


@app.put("/api/direct/todos/{project_dir}/{todo_id}")
async def api_update_todo(project_dir: str, todo_id: str, request: Request):
    data = await request.json()
    item = update_direct_todo(project_dir, todo_id, data.get("status", "done"), data.get("result", ""))
    return {"ok": bool(item), "todo": item}


@app.get("/api/direct/todos/{project_dir}/{todo_id}")
async def api_get_todo(project_dir: str, todo_id: str):
    todo = get_todo(project_dir, todo_id)
    if not todo:
        return {"ok": False, "error": "Todo not found"}

    # Enrich with schedule info for pending/attempted items
    schedule = {}
    if todo["status"] in ("pending", "attempted"):
        hb = get_heartbeat(project_dir)
        schedule["heartbeat_enabled"] = hb.get("enabled", False)
        schedule["heartbeat_interval"] = hb.get("interval_minutes", 30)
        pending = get_pending_todos(project_dir)
        # Find position in queue
        for i, p in enumerate(pending):
            if p["id"] == todo_id:
                schedule["queue_position"] = i + 1
                break
        # Estimate next run for this item
        if hb.get("enabled") and not hb.get("running"):
            from datetime import datetime, timezone, timedelta
            try:
                last = hb.get("last_run")
                interval = hb.get("interval_minutes", 30)
                if last:
                    last_dt = datetime.fromisoformat(last)
                    base_next = last_dt + timedelta(minutes=interval)
                else:
                    base_next = datetime.now(timezone.utc)
                # Add interval for each item ahead in queue
                pos = schedule.get("queue_position", 1) - 1
                est = base_next + timedelta(minutes=interval * pos)
                remaining = (est - datetime.now(timezone.utc)).total_seconds()
                schedule["est_run_secs"] = max(0, int(remaining))
                schedule["est_run_at"] = est.isoformat()[:19]
            except Exception:
                pass

    return {"ok": True, "todo": todo, "schedule": schedule}


@app.delete("/api/direct/todos/{project_dir}/{todo_id}")
async def api_delete_todo(project_dir: str, todo_id: str):
    return {"ok": delete_todo(project_dir, todo_id)}


@app.get("/api/direct/heartbeat/{project_dir}")
async def api_get_heartbeat(project_dir: str):
    hb = get_heartbeat(project_dir)
    # Add next_run estimate
    if hb.get("enabled") and hb.get("last_run") and not hb.get("running"):
        from datetime import datetime, timezone, timedelta
        try:
            last = datetime.fromisoformat(hb["last_run"])
            next_run = last + timedelta(minutes=hb.get("interval_minutes", 30))
            hb["next_run_est"] = next_run.isoformat()[:19]
            remaining = (next_run - datetime.now(timezone.utc)).total_seconds()
            hb["next_run_secs"] = max(0, int(remaining))
        except Exception:
            pass
    # Add pending todo count + currently running todo
    pending = get_pending_todos(project_dir)
    hb["pending_count"] = len(pending)
    if pending:
        hb["next_todo"] = pending[0].get("task", "")[:80]
    return hb


@app.post("/api/direct/heartbeat/{project_dir}")
async def api_set_heartbeat(project_dir: str, request: Request):
    data = await request.json()
    hb = get_heartbeat(project_dir)
    if "enabled" in data:
        hb["enabled"] = bool(data["enabled"])
    if "interval_minutes" in data:
        hb["interval_minutes"] = max(1, int(data["interval_minutes"]))
    save_heartbeat(project_dir, hb)
    return {"ok": True, "heartbeat": hb}


@app.post("/api/direct/heartbeat/{project_dir}/run")
async def api_run_heartbeat_now(project_dir: str):
    """Run next pending todo via the chat pipeline — same as clicking Run in the UI."""
    from tools import PROJECTS_ROOT
    project_path = PROJECTS_ROOT / project_dir
    if not project_path.exists():
        return {"error": "Project not found"}
    prov = _get_provider()
    if not prov["api_key"]:
        return {"error": "No API key configured"}
    pending = get_pending_todos(project_dir)
    if not pending:
        return {"ok": True, "message": "No pending todos"}

    todo_item = pending[0]
    hb = get_heartbeat(project_dir)
    hb["running"] = True
    save_heartbeat(project_dir, hb)

    try:
        await _execute_todo_via_chat(project_dir, todo_item)
        return {"ok": True, "todo_id": todo_item["id"]}
    finally:
        from datetime import datetime, timezone
        hb = get_heartbeat(project_dir)
        hb["running"] = False
        hb["last_run"] = datetime.now(timezone.utc).isoformat()[:19]
        save_heartbeat(project_dir, hb)


@app.get("/api/direct/history/{project_dir}")
async def get_direct_history(project_dir: str):
    conv_dir = _DIRECT_CONVERSATIONS_DIR / project_dir
    if not conv_dir.exists():
        return {"conversations": []}
    conv_files = sorted(conv_dir.glob("*.json"), key=lambda p: p.name)
    conversations = []
    for f in conv_files[-50:]:
        try:
            conv = json.loads(f.read_text())
            msgs = conv.get("messages") or []
            assistant_parts = []
            tool_names = []
            for m in msgs:
                if m.get("role") == "assistant" and m.get("content"):
                    assistant_parts.append(m["content"])
                if m.get("role") == "assistant" and m.get("tools"):
                    tool_names.extend(m["tools"])
            conversations.append({
                "timestamp": conv.get("timestamp", f.stem),
                "user_message": conv.get("user_message", ""),
                "response": "\n".join(assistant_parts) if assistant_parts else "",
                "tools_used": tool_names,
            })
        except (json.JSONDecodeError, OSError):
            continue
    return {"conversations": conversations}


# ── Heartbeat scheduler ───────────────────────────────────────────────
async def _execute_todo_via_chat(project_dir: str, todo_item: dict):
    """Execute a todo by calling the chat endpoints internally — same pipeline the browser uses."""
    import logging
    import httpx
    _log = logging.getLogger("uvicorn")
    from datetime import datetime, timezone

    todo_id = todo_item["id"]
    task = todo_item["task"]
    base_url = "http://127.0.0.1:10100"

    _heartbeat_progress.update({
        "active": True, "project": project_dir,
        "todo_id": todo_id, "task": task[:100],
        "step": "starting", "turn": 0, "max_turns": 80, "total_steps": 0,
        "started_at": datetime.now(timezone.utc).isoformat()[:19],
        "finished_at": "", "result_status": "", "result_message": "",
    })

    update_direct_todo(project_dir, todo_id, "attempted")
    result_text = ""
    total_steps = 0
    _captured_test_evidence = []

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(600.0)) as client:
            # Step 1: POST /api/direct/start (same as browser sendMessage)
            start_resp = await client.post(f"{base_url}/api/direct/start", json={
                "message": task,
                "project_dir": project_dir,
            })
            start_data = start_resp.json()
            if start_data.get("error"):
                raise Exception(start_data["error"])

            stream_url = start_data["stream_url"]
            # Enable auto-test so the agent loop verifies its own work
            sep = "&" if "?" in stream_url else "?"
            stream_url = f"{stream_url}{sep}auto_test=true"

            # Step 2: Consume SSE stream (same as browser EventSource)
            async with client.stream("GET", f"{base_url}{stream_url}") as stream:
                buffer = ""
                async for chunk in stream.aiter_text():
                    buffer += chunk
                    while "\n\n" in buffer:
                        event_text, buffer = buffer.split("\n\n", 1)
                        # Parse SSE event
                        event_type = ""
                        event_data = ""
                        for line in event_text.strip().split("\n"):
                            if line.startswith("event: "):
                                event_type = line[7:]
                            elif line.startswith("data: "):
                                event_data = line[6:]

                        if not event_type or not event_data:
                            continue

                        try:
                            d = json.loads(event_data)
                        except json.JSONDecodeError:
                            continue

                        if event_type == "turn":
                            _heartbeat_progress.update({
                                "turn": d.get("action_turns", 0),
                                "max_turns": d.get("max", 80),
                            })
                        elif event_type == "tool_call":
                            total_steps += 1
                            name = d.get("name", "")
                            args = d.get("args", {})
                            arg_preview = args.get("path", args.get("pattern", args.get("command", "")))
                            step = f"{name}({arg_preview})" if arg_preview else name
                            _heartbeat_progress.update({"step": step, "total_steps": total_steps})
                        elif event_type == "tool_result":
                            name = d.get("name", "")
                            result_preview = (d.get("result", "") or "").strip().split('\n')[0][:60]
                            _heartbeat_progress.update({"step": f"{name} → {result_preview}"})
                        elif event_type == "response":
                            content = d.get("content", "")
                            if content:
                                result_text = content
                            _heartbeat_progress.update({"step": "completing"})
                        elif event_type == "thinking":
                            preview = (d.get("content", "") or "").strip()[:80]
                            _heartbeat_progress.update({"step": f"planning: {preview}" if preview else "thinking"})
                        elif event_type == "test_phase":
                            status = d.get("status", "")
                            iteration = d.get("iteration", 0)
                            if status == "planning":
                                _heartbeat_progress.update({"step": f"test: planning (iter {iteration})"})
                            elif status == "running":
                                tc = d.get("test_count", 0)
                                _heartbeat_progress.update({"step": f"test: running {tc} tests (iter {iteration})"})
                            elif status == "all_passed":
                                p = d.get("passed", 0)
                                _heartbeat_progress.update({"step": f"test: {p} tests passed"})
                            elif status == "error":
                                _heartbeat_progress.update({"step": f"test: error — {d.get('error', '')[:60]}"})
                        elif event_type == "test_feedback":
                            failed = d.get("failed", 0)
                            iteration = d.get("iteration", 0)
                            _heartbeat_progress.update({
                                "step": f"test: {failed} failures, fixing (iter {iteration})",
                                "turn": 0,  # Turns reset for fix attempt
                            })
                        elif event_type == "done":
                            _captured_test_evidence = d.get("test_evidence") or []
                            break
                        elif event_type == "error":
                            raise Exception(d.get("message", "Stream error"))

        # Success
        from direct_todo import _classify_result
        rs = _classify_result(result_text)
        _heartbeat_progress.update({
            "active": False, "step": "done", "result_status": rs,
            "result_message": result_text[:200],
            "finished_at": datetime.now(timezone.utc).isoformat()[:19],
        })
        update_direct_todo(project_dir, todo_id, "done", result_text)
        record_heartbeat_run(project_dir, todo_id, task, result_text)
        # TD review + docs regen in parallel (conversation already saved by the stream)
        # Include test evidence so TD can assess actual verification quality
        asyncio.create_task(_run_td_review_for_todo(
            project_dir, todo_id, task, result_text, _captured_test_evidence
        ))
        asyncio.create_task(_regenerate_docs())
        _log.info(f"[heartbeat] {project_dir}: todo {todo_id} completed ({rs})")

    except Exception as e:
        _log.error(f"[heartbeat] {project_dir}: todo {todo_id} failed: {e}")
        _heartbeat_progress.update({
            "active": False, "step": "error", "result_status": "failure",
            "result_message": str(e)[:200],
            "finished_at": datetime.now(timezone.utc).isoformat()[:19],
        })
        update_direct_todo(project_dir, todo_id, "attempted", str(e))
        record_heartbeat_run(project_dir, todo_id, task, f"ERROR: {e}")


async def _heartbeat_scheduler():
    from tools import PROJECTS_ROOT
    import logging
    _log = logging.getLogger("uvicorn")
    _log.info("[heartbeat] Scheduler started")
    while True:
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            _log.info("[heartbeat] Scheduler cancelled")
            return
        except Exception as e:
            _log.error(f"[heartbeat] Sleep error: {e}")
            continue
        try:
            from direct_todo import HEARTBEAT_DIR
            if not HEARTBEAT_DIR.exists():
                continue
            for hb_file in HEARTBEAT_DIR.glob("*.json"):
                try:
                    hb = json.loads(hb_file.read_text())
                    if not hb.get("enabled") or hb.get("running"):
                        continue
                    interval = hb.get("interval_minutes", 1)
                    last_run = hb.get("last_run")
                    if last_run:
                        from datetime import datetime, timezone
                        last_dt = datetime.fromisoformat(last_run)
                        if last_dt.tzinfo is None:
                            last_dt = last_dt.replace(tzinfo=timezone.utc)
                        if (datetime.now(timezone.utc) - last_dt).total_seconds() < interval * 60:
                            continue
                    project_dir = hb_file.stem
                    project_path = PROJECTS_ROOT / project_dir
                    if not project_path.exists():
                        continue
                    pending = get_pending_todos(project_dir)
                    if not pending:
                        continue
                    prov = _get_provider()
                    if not prov["api_key"]:
                        continue
                    _log.info(f"[heartbeat] {project_dir}: EXECUTING todo '{pending[0]['task'][:50]}'")
                    hb["running"] = True
                    save_heartbeat(project_dir, hb)

                    try:
                        await _execute_todo_via_chat(project_dir, pending[0])
                    finally:
                        from datetime import datetime, timezone
                        hb = get_heartbeat(project_dir)
                        hb["running"] = False
                        hb["last_run"] = datetime.now(timezone.utc).isoformat()[:19]
                        save_heartbeat(project_dir, hb)

                except Exception:
                    try:
                        hb = get_heartbeat(hb_file.stem)
                        hb["running"] = False
                        save_heartbeat(hb_file.stem, hb)
                    except Exception:
                        pass
        except Exception as e:
            _log.error(f"[heartbeat] Outer error: {e}")


@app.on_event("startup")
async def _startup():
    import logging
    _log = logging.getLogger("uvicorn")
    _log.info("Starting heartbeat scheduler...")
    # Clear any stuck running flags from previous server process
    from direct_todo import HEARTBEAT_DIR
    if HEARTBEAT_DIR.exists():
        for hb_file in HEARTBEAT_DIR.glob("*.json"):
            try:
                hb = json.loads(hb_file.read_text())
                if hb.get("running"):
                    hb["running"] = False
                    hb_file.write_text(json.dumps(hb, indent=2))
                    _log.info(f"[startup] Cleared stuck running flag for {hb_file.stem}")
            except Exception:
                pass
    asyncio.create_task(_heartbeat_scheduler())


# ── Per-todo TD Review ─────────────────────────────────────────────────
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


def _parse_td_verdict(review_text: str) -> str:
    """Parse the STATUS: line from TD review. Returns success/partial/failure/incomplete."""
    import re
    match = re.search(r"STATUS:\s*(PASS|PARTIAL|FAIL|INCOMPLETE)", review_text, re.IGNORECASE)
    if not match:
        return ""
    verdict = match.group(1).upper()
    return {"PASS": "success", "PARTIAL": "partial", "FAIL": "failure", "INCOMPLETE": "incomplete"}.get(verdict, "")


async def _run_td_review_for_todo(project_dir: str, todo_id: str, task: str, result: str, test_evidence: list = None):
    """Run a TD review for a single todo execution (background task).
    The TD verdict becomes the authoritative result_status for the todo.
    If test_evidence is provided, it's included so TD can assess actual verification."""
    import logging
    _log = logging.getLogger("uvicorn")
    prov = _get_provider()
    if not prov["api_key"]:
        return
    try:
        selected = config["selected"]

        # Build review input with test evidence when available
        review_input = f"Task: {task}\n\nAgent Result:\n{result[:8000]}"
        if test_evidence:
            review_input += "\n\n## Automated Test Results\n"
            for te in test_evidence:
                review_input += (
                    f"\n### Test Iteration {te.get('iteration', '?')}\n"
                    f"Plan: {te.get('plan_summary', 'N/A')}\n"
                    f"Total: {te.get('total', 0)}, Passed: {te.get('passed', 0)}, "
                    f"Failed: {te.get('failed', 0)}\n"
                )
                for d in te.get("details", []):
                    status = d.get("status", "?")
                    name = d.get("name", "unnamed")
                    review_input += f"- [{status.upper()}] {d.get('id', '?')}: {name}\n"
                    if status != "pass":
                        for det in d.get("details", []):
                            if det.get("assertion_failed"):
                                review_input += f"    FAIL: {det['assertion_failed'][:200]}\n"
            review_input = review_input[:12000]  # Keep within token budget

        review_result = await asyncio.to_thread(
            call_llm, selected, prov["api_key"], prov["base_url"], prov["model"],
            [
                {"role": "system", "content": TODO_TD_REVIEW_PROMPT},
                {"role": "user", "content": review_input},
            ],
            None, 0.3,
        )
        parsed = extract_response(review_result)
        review_text = parsed["content"]
        # Parse verdict and update todo with both review and authoritative status
        td_status = _parse_td_verdict(review_text)
        set_todo_review(project_dir, todo_id, review_text, td_status)
        _log.info(f"[td-review] Completed review for todo {todo_id}: {td_status or 'no verdict parsed'}")
    except Exception as e:
        _log.error(f"[td-review] Failed for {todo_id}: {e}")


# ── Auto-regenerate Context Map & Data Flow ───────────────────────────
_CONTEXT_MAP_PROMPT = (
    "You are a documentation generator for a software project.\n\n"
    "Given the source code below, produce a CONTEXT_MAP.md that maps:\n"
    "1. File structure with purpose of each file\n"
    "2. All API endpoints (method, path, handler function, line number)\n"
    "3. All tools/functions available to the LLM agent\n"
    "4. Data directories and their formats\n"
    "5. Frontend components and key JS functions\n"
    "6. Key constants, config, and state variables\n\n"
    "Use tables and code blocks. Be specific with line numbers. "
    "Format as markdown. Start with '# aelidirect -- Context Map'."
)

_DATA_FLOW_PROMPT = (
    "You are a documentation generator for a software project.\n\n"
    "Given the source code below, produce a DATA_FLOW.md that traces:\n"
    "1. Main chat flow (user message → SSE stream → agent loop → response)\n"
    "2. Tool call loop (LLM response → tool execution → result → next LLM call)\n"
    "3. Memory system (long-term save/load, short-term conversation history)\n"
    "4. Heartbeat/todo execution flow\n"
    "5. Deployment flow (pod management)\n"
    "6. Config and state management\n"
    "7. Branch/prod sync flow\n\n"
    "Trace data step by step with file names, function names, and line numbers. "
    "Format as markdown. Start with '# aelidirect -- Data Flow'."
)


_SPEC_PROMPT = (
    "You are a documentation generator for a software project.\n\n"
    "Given the source code below, produce a SPEC.md that covers:\n"
    "1. What the project is (1-2 paragraph overview in plain English)\n"
    "2. How it works (the big picture — message flow, agent loop, tool execution)\n"
    "3. Features — organized by category (core agent, file tools, system tools, memory, "
    "project management, testing, deployment, frontend, TD review)\n"
    "4. Tech stack table\n"
    "5. How to run it\n\n"
    "Write for someone who has never seen the project. Be specific about what each feature does. "
    "Include the test agent (test_agent.py) — explain the two-phase test system (plan then run), "
    "the test-fix loop (failures feed back to coder with context preserved), and how TD review "
    "incorporates test evidence.\n\n"
    "Format as markdown. Start with '# aelidirect -- Project Specification'."
)


async def _regenerate_docs():
    """Regenerate SPEC.md, CONTEXT_MAP.md and DATA_FLOW.md in parallel."""
    import logging
    _log = logging.getLogger("uvicorn")
    prov = _get_provider()
    if not prov["api_key"]:
        return

    # Read all source files in parallel
    source_files = [
        _PROD_ROOT / "backend/main.py",
        _PROD_ROOT / "backend/tools.py",
        _PROD_ROOT / "backend/direct_todo.py",
        _PROD_ROOT / "backend/llm_client.py",
        _PROD_ROOT / "backend/pod.py",
        _PROD_ROOT / "backend/test_agent.py",
        _PROD_ROOT / "frontend/index.html",
    ]

    import concurrent.futures
    def _read_file(p):
        if p.exists():
            content = p.read_text()
            # Truncate large files to keep within LLM context
            if len(content) > 30000:
                content = content[:15000] + "\n\n... [TRUNCATED] ...\n\n" + content[-15000:]
            return f"\n### {p.relative_to(_PROD_ROOT)}\n```\n{content}\n```\n"
        return ""

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        futures = [pool.submit(_read_file, f) for f in source_files]
        file_contents = [fut.result() for fut in futures]

    all_source = "\n".join(file_contents)
    selected = config["selected"]

    # Run both LLM calls in parallel
    async def _gen_context_map():
        try:
            result = await asyncio.to_thread(
                call_llm, selected, prov["api_key"], prov["base_url"], prov["model"],
                [
                    {"role": "system", "content": _CONTEXT_MAP_PROMPT},
                    {"role": "user", "content": all_source},
                ],
                None, 0.3,
            )
            parsed = extract_response(result)
            (_PROD_ROOT / "CONTEXT_MAP.md").write_text(parsed["content"])
            _log.info("[docs] CONTEXT_MAP.md regenerated")
        except Exception as e:
            _log.error(f"[docs] Failed to regenerate CONTEXT_MAP.md: {e}")

    async def _gen_data_flow():
        try:
            result = await asyncio.to_thread(
                call_llm, selected, prov["api_key"], prov["base_url"], prov["model"],
                [
                    {"role": "system", "content": _DATA_FLOW_PROMPT},
                    {"role": "user", "content": all_source},
                ],
                None, 0.3,
            )
            parsed = extract_response(result)
            (_PROD_ROOT / "DATA_FLOW.md").write_text(parsed["content"])
            _log.info("[docs] DATA_FLOW.md regenerated")
        except Exception as e:
            _log.error(f"[docs] Failed to regenerate DATA_FLOW.md: {e}")

    async def _gen_spec():
        try:
            result = await asyncio.to_thread(
                call_llm, selected, prov["api_key"], prov["base_url"], prov["model"],
                [
                    {"role": "system", "content": _SPEC_PROMPT},
                    {"role": "user", "content": all_source},
                ],
                None, 0.3,
            )
            parsed = extract_response(result)
            (_PROD_ROOT / "SPEC.md").write_text(parsed["content"])
            _log.info("[docs] SPEC.md regenerated")
        except Exception as e:
            _log.error(f"[docs] Failed to regenerate SPEC.md: {e}")

    # Run all three in parallel
    await asyncio.gather(_gen_spec(), _gen_context_map(), _gen_data_flow())
    _log.info("[docs] Documentation regeneration complete")


# ── TD Analysis ───────────────────────────────────────────────────────
_TD_REPORTS_DIR = Path(__file__).parent / ".td_reports"
_TD_REPORTS_DIR.mkdir(exist_ok=True)

TD_ANALYSIS_PROMPT = (
    "You are a Technical Director reviewing an AI agent's work across multiple conversations and projects.\n\n"
    "Analyze the conversation history below and produce a comprehensive report:\n\n"
    "1. SUMMARY — What projects were worked on, how many conversations, overall health\n"
    "2. BUGS FOUND — Every bug discovered across all sessions (with root cause)\n"
    "3. BUGS FIXED — Every fix applied (what changed, which file, was it verified)\n"
    "4. BUGS MISSED — Anything the agent should have caught but didn't\n"
    "5. FEATURES BUILT — What was created, deployed, tested\n"
    "6. AGENT BEHAVIOR — How the agent approached tasks:\n"
    "   - Did it read code before acting?\n"
    "   - Did it verify fixes specifically or just check HTTP 200?\n"
    "   - Did it rationalize things as 'intentional' without evidence?\n"
    "   - Did it stop too early or keep investigating?\n"
    "7. PATTERNS — Recurring issues, common failures, things that work well\n"
    "8. RECOMMENDATIONS — Specific, actionable improvements for the agent's prompt, tools, or workflow\n\n"
    "Be thorough and specific. Name files, functions, line numbers. "
    "Don't sugarcoat — if the agent failed, say so and explain why.\n"
    "Format as markdown."
)


@app.post("/api/td-analysis")
async def run_td_analysis():
    """Run TD analysis across all projects and conversations."""
    prov = _get_provider()
    if not prov["api_key"]:
        return {"error": "No API key configured"}

    # Gather all conversations across all projects
    parts = []
    total_convs = 0

    if _DIRECT_CONVERSATIONS_DIR.exists():
        for proj_dir in sorted(_DIRECT_CONVERSATIONS_DIR.iterdir()):
            if not proj_dir.is_dir():
                continue
            conv_files = sorted(proj_dir.glob("*.json"), key=lambda p: p.name)
            if not conv_files:
                continue

            parts.append(f"\n## Project: {proj_dir.name} ({len(conv_files)} conversations)\n")

            for f in conv_files[-30:]:  # last 30 per project
                try:
                    conv = json.loads(f.read_text())
                    total_convs += 1
                    parts.append(f"### [{conv.get('timestamp', f.stem)}] User: {conv.get('user_message', '?')}")

                    for m in (conv.get("messages") or []):
                        if m.get("role") == "assistant" and m.get("content"):
                            parts.append(f"  Agent: {m['content'][:600]}")
                        elif m.get("role") == "assistant" and m.get("tools"):
                            parts.append(f"  Tools: {', '.join(m['tools'][:8])}")
                        elif m.get("role") == "tool" and m.get("result"):
                            parts.append(f"  Result ({m.get('name', '?')}): {m['result'][:200]}")
                    parts.append("")
                except (json.JSONDecodeError, OSError):
                    continue

    if total_convs == 0:
        return {"error": "No conversations to analyze"}

    context = "\n".join(parts)

    # Truncate if too large for the LLM
    if len(context) > 400_000:
        context = context[:400_000] + "\n\n... (truncated)"

    try:
        selected = config["selected"]
        result = await asyncio.to_thread(
            call_llm, selected, prov["api_key"], prov["base_url"], prov["model"],
            [
                {"role": "system", "content": TD_ANALYSIS_PROMPT},
                {"role": "user", "content": f"Analyze these {total_convs} conversations:\n\n{context}"},
            ],
            None, 0.3,
        )
        parsed = extract_response(result)
        report = parsed["content"]

        # Save report
        from datetime import datetime, timezone
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
        (_TD_REPORTS_DIR / f"{ts}.md").write_text(report)

        return {"report": report, "timestamp": ts, "conversations_analyzed": total_convs}
    except Exception as e:
        return {"error": f"Analysis failed: {e}"}


@app.get("/api/td-analysis")
async def get_latest_td_analysis():
    """Get the most recent TD analysis report."""
    if not _TD_REPORTS_DIR.exists():
        return {"report": None}
    files = sorted(_TD_REPORTS_DIR.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        return {"report": None}
    return {"report": files[0].read_text(), "timestamp": files[0].stem}


@app.get("/api/td-reports")
async def list_td_reports():
    """List all TD analysis reports."""
    reports = []
    if _TD_REPORTS_DIR.exists():
        for f in sorted(_TD_REPORTS_DIR.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True):
            content = f.read_text()
            reports.append({"timestamp": f.stem, "preview": content[:300].replace("\n", " ")})
    return {"reports": reports}


@app.get("/api/td-reports/{timestamp}")
async def get_td_report(timestamp: str):
    """Get a specific TD report by timestamp."""
    report_path = _TD_REPORTS_DIR / f"{timestamp}.md"
    if report_path.exists():
        return {"report": report_path.read_text(), "timestamp": timestamp}
    return {"report": None, "timestamp": timestamp}


# ── Serve frontend ────────────────────────────────────────────────────
FRONTEND_DIR = Path(__file__).parent.parent / "frontend"


@app.get("/")
async def serve_index():
    return HTMLResponse((FRONTEND_DIR / "index.html").read_text())


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=10100)
