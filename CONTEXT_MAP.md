<think>
The user wants me to generate a CONTEXT_MAP.md for the aelidirect project based on the provided source code. Let me analyze all the files and create a comprehensive mapping.

Let me go through each file:

### backend/main.py
- FastAPI application (aelidirect)
- API endpoints:
  - GET `/` - serve_index (frontend)
  - POST `/api/chat` - chat endpoint (streaming)
  - GET `/api/projects` - list projects
  - POST `/api/projects` - create project
  - GET `/api/projects/{project}` - get project info
  - DELETE `/api/projects/{project}` - delete project
  - POST `/api/projects/{project}/heartbeat` - heartbeat config
  - GET `/api/platform/heartbeat-progress` - heartbeat progress
  - POST `/api/platform/restart` - restart platform
  - POST `/api/platform/branch-wipe` - wipe branch
  - POST `/api/platform/branch-deploy` - deploy branch to prod
  - GET `/api/platform/branch-status` - branch status
  - POST `/api/td-analysis` - run TD analysis
  - GET `/api/td-analysis` - get latest TD analysis
  - GET `/api/td-reports` - list TD reports
  - GET `/api/td-reports/{timestamp}` - get specific TD report

- Config:
  - providers: openrouter, minimax
  - selected provider
  - pod_host

- State:
  - _direct_state
  - _heartbeat_progress

- Directories:
  - _DIRECT_MEMORY_DIR
  - _DIRECT_CONVERSATIONS_DIR

- Key functions:
  - sse_event()
  - _is_readonly_tool_call()
  - _save_config(), _get_provider(), _pod_url()
  - _save_conversation(), _load_conversation_history()
  - _summarize_old_conversations()
  - _execute_direct_agent()
  - _build_messages()
  - _regenerate_docs()
  - _heartbeat_scheduler()
  - _run_td_review_for_todo()

### backend/tools.py
The tools module provides file system operations for the LLM agent. It includes definitions like list_files, read_file, edit_file, patch_file, read_file_tail, read_lines, and grep_code. The module manages project directories through PROJECTS_ROOT and _SAFE_ROOTS, and maintains file caches to track changes across different branches.

### backend/direct_todo.py
This module handles todo list operations and scheduled execution. It stores todos in TODO_DIR and heartbeats in HEARTBEAT_DIR, providing functions like add_todo, update_todo, delete_todo, get_todos, get_pending_todos, get_heartbeat, save_heartbeat, record_heartbeat_run, and set_todo_review.

### backend/llm_client.py
A minimal HTTP client supporting both OpenRouter and MiniMax providers, with call_llm handling requests and extract_response parsing results.

### backend/pod.py
Container management for building, running, and health-checking pods, with port allocation in the 11001-11099 range.

### frontend/index.html
A single-page application providing a chat interface, project management sidebar, todo list panel, heartbeat panel, and configuration view.

Now I'm organizing this into a comprehensive context map.
</think>

# aelidirect -- Context Map

## 1. File Structure

```
aelidirect/
├── backend/
│   ├── main.py          # FastAPI app, all HTTP endpoints, agent loop, SSE streaming, heartbeat scheduler, TD review
│   ├── tools.py         # Tool definitions + executors (file ops, bash, git, memory, deploy)
│   ├── direct_todo.py   # Todo CRUD + heartbeat state persistence
│   ├── llm_client.py    # HTTP client for OpenRouter/MiniMax, response parsing, JSON repair
│   └── pod.py           # Podman pod lifecycle (build, create, health-check, destroy), port allocation
├── frontend/
│   └── index.html       # Full SPA: chat UI, sidebar, todo panel, heartbeat panel, config view
├── projects/           # Generated project directories (auto-created)
├── .config.json         # Persisted API keys + provider selection
├── .direct_memory/      # Long-term memory JSON files (key-value)
├── .direct_conversations/  # Per-project conversation JSON files
├── .direct_todos/       # Per-project todo JSON files
├── .direct_heartbeats/  # Per-project heartbeat config JSON files
├── .td_reports/        # Technical Director analysis reports
└── .ports.json         # Port allocation map (project_name → port)
```

---

## 2. API Endpoints

All in `backend/main.py` unless noted.

| Method | Path | Handler | File | Line |
|--------|------|---------|------|------|
| GET | `/` | `serve_index` | main.py | ~480 |
| POST | `/api/chat` | `chat` (StreamingResponse, SSE) | main.py | ~170 |
| GET | `/api/projects` | `list_projects` | main.py | ~240 |
| POST | `/api/projects` | `create_project` | main.py | ~247 |
| GET | `/api/projects/{project}` | `get_project` | main.py | ~262 |
| DELETE | `/api/projects/{project}` | `delete_project` | main.py | ~270 |
| POST | `/api/projects/{project}/heartbeat` | `configure_heartbeat` | main.py | ~295 |
| GET | `/api/platform/heartbeat-progress` | `get_heartbeat_progress` | main.py | ~310 |
| POST | `/api/platform/restart` | `restart_platform` | main.py | ~320 |
| POST | `/api/platform/branch-wipe` | `wipe_branch` | main.py | ~350 |
| POST | `/api/platform/branch-deploy` | `deploy_branch_to_prod` | main.py | ~400 |
| GET | `/api/platform/branch-status` | `get_branch_status` | main.py | ~430 |
| POST | `/api/td-analysis` | `run_td_analysis` | main.py | ~550 |
| GET | `/api/td-analysis` | `get_latest_td_analysis` | main.py | ~570 |
| GET | `/api/td-reports` | `list_td_reports` | main.py | ~582 |
| GET | `/api/td-reports/{timestamp}` | `get_td_report` | main.py | ~592 |

---

## 3. Tools Available to the LLM Agent

Defined in `backend/tools.py`, lines **140–265** (definitions) and **268–430** (executors).

### Tool Definitions (JSON schemas sent to LLM)

| Tool Name | Description | Parameters |
|-----------|-------------|------------|
| `list_files` | List all files in project directory | `path` (string, optional, default ".") |
| `read_file` | Read file contents | `path` (string, required) |
| `edit_file` | Create new file or fully rewrite | `path`, `content` (string) |
| `patch_file` | Targeted edit: find `old_text`, replace with `new_text` | `path`, `old_text`, `new_text` |
| `read_file_tail` | Read last N lines of a file | `path`, `lines` (integer, default 50) |
| `read_lines` | Read specific line range (1-indexed) | `path`, `start`, `end` |
| `grep_code` | Case-insensitive search across all project files | `pattern` (string) |
| `read_project` | Read ALL source files in one call; returns listing if too large | (none) |

### Tool Executor

**`execute_tool(name, arguments, project_dir)`** — `tools.py` line **268**

Routes by name to individual implementations (`_tool_list_files` through `_tool_read_project`), lines **273–430**.

### Additional Tools (defined in `main.py` system prompt, not as JSON schemas)

These are described in `DIRECT_AGENT_PROMPT` (main.py lines ~60–130) and handled by `execute_tool` in the agent loop:

| Tool | Implementation |
|------|----------------|
| `bash(command)` | Via `_run_bash()` in main.py (~140) |
| `deploy_pod()` | Via `spin_up_pod()` in pod.py |
| `http_check(path)` | Via `http_get()` in pod.py |
| `git_status()`, `git_diff()`, `git_log(n)`, `git_commit(msg)` | Via `_run_bash()` calling git commands |
| `memory_save(key, content)`, `memory_load(key)`, `memory_list()` | Via `_load_memory()`, `save_memory()` in main.py |
| `restart_platform()` | Via `restart_platform()` endpoint |

### Read-Only Tool Detection

`tools.py` lines **42–56**:
- `READ_ONLY_TOOLS` frozenset: `list_files`, `read_file`, `read_lines`, `read_file_tail`, `grep_code`, `read_project`, `memory_load`, `memory_list`
- `_BASH_READONLY_PREFIXES` tuple: `ls`, `cat`, `head`, `tail`, `grep`, `rg`, `find`, `git status/log/diff/show`, `curl -s`, `python3 -m py_compile`, etc.
- `_is_readonly_tool_call(tc)` — `tools.py` line **58**

### File Caching System

`tools.py` lines **17–82**:
- Dual cache: `_file_cache_main` (prod) + `_file_cache_branch` (branch edits for platform project)
- `_is_platform_project()` — detects `aelidirect_platform` or `/home/aeli/projects/aelidirect_branch`
- `file_cache_set()` / `file_cache_get()` — auto-selects branch vs main cache
- `file_cache_wipe_branch()` — copies main → branch (on branch wipe)
- `file_cache_deploy_to_main()` — copies branch → main (on deploy)
- Cache invalidation by disk mtime tracking in `_file_cache_mtime`

---

## 4. Data Directories and Formats

| Directory | File | Purpose | Format |
|-----------|------|---------|--------|
| Backend root | `.config.json` | API keys, selected provider, pod_host | JSON: `{providers: {openrouter: {...}, minimax: {...}}, selected: "minimax", pod_host: "..."}` |
| Backend root | `.ports.json` | Port allocation map | JSON: `{"project_name": port}` |
| `backend/` | `.direct_memory/` | Long-term memory files | One JSON file per key: `{key: "...", content: "...", updated_at: "..."}` |
| `backend/` | `.direct_conversations/{project}/` | Conversation history | One JSON per conversation: `{timestamp, user_message, messages: [...], llm_summary}` |
| `backend/` | `.direct_todos/` | Todo lists per project | One JSON per project: array of todo objects |
| `backend/` | `.direct_heartbeats/` | Heartbeat config per project | One JSON per project: `{enabled, interval_minutes, last_run, next_run, running, history: [...]}` |
| `backend/` | `.td_reports/` | TD analysis reports | One `.md` file per report |
| Project root | `project_env.md` | Project metadata | Markdown table: `\| Property \| Value \|` |

### Todo Object Schema

```json
{
  "id": "abc12345",
  "task": "Add user auth",
  "category": "feature",
  "status": "pending | attempted | done",
  "created_at": "2025-01-15T10:30:00",
  "started_at": "2025-01-15T10:35:00 | null",
  "completed_at": "2025-01-15T10:45:00 | null",
  "duration_secs": 600 | null,
  "attempts": 1,
  "result_status": "success | failure | partial | incomplete | null",
  "last_result": "...",
  "td_review": "..."
}
```

### Heartbeat Object Schema

```json
{
  "enabled": true,
  "interval_minutes": 30,
  "last_run": "2025-01-15T10:30:00 | null",
  "next_run": "2025-01-15T11:00:00 | null",
  "running": false,
  "history": [
    {"timestamp": "...", "todo_id": "...", "task": "...", "result": "..."}
  ]
}
```

---

## 5. Frontend Components and Key JS Functions

All in `frontend/index.html` (single-file SPA).

### Layout Structure

```
.shell (flex row)
├── .sidebar (width: 200px)
│   ├── .sidebar-brand (logo: "aelidirect")
│   ├── .sidebar-section-label "PROJECTS"
│   ├── .sidebar-projects (project list buttons)
│   └── .sidebar-actions (New Project, Config buttons)
└── .main-content (flex: 1)
    ├── .chat-view (flex column)
    │   ├── .project-bar (shown when project active)
    │   ├── .messages (scrollable message list)
    │   ├── .sticky-spinner (pulsing dot + label + elapsed timer)
    │   └── .input-area (textarea + Send button + pod bar)
    ├── .config-view (hidden by default)
    └── .right-panel (width: 480px)
        ├── .right-panel-tabs (Todo | Heartbeat)
        ├── .todo-panel
        └── .heartbeat-panel
```

### Key JavaScript Functions

| Function | Location (line approx) | Purpose |
|----------|------------------------|---------|
| `addMsg(type, text)` | ~700 | Append a message bubble to `.messages` |
| `sendMessage()` | ~730 | POST to `/api/chat`, handle SSE stream |
| `loadProjects()` | ~780 | Fetch `/api/projects`, render sidebar |
| `selectProject(name, dir)` | ~820 | Switch active project, load todos/hearbeat |
| `createProject()` | ~850 | POST to `/api/projects` |
| `deleteProject(name)` | ~870 | DELETE project |
| `loadTodos()` | ~900 | Fetch todos for active project, render todo panel |
| `addTodo()` | ~950 | Add todo item |
| `deleteTodo(id)` | ~970 | Delete todo item |
| `runTodo(id)` | ~990 | Execute single todo via chat endpoint |
| `loadHeartbeat()` | ~1030 | Fetch heartbeat state, render panel |
| `saveHeartbeat()` | ~1070 | POST heartbeat config |
| `checkBranchStatus()` | ~1100 | Poll `/api/platform/branch-status` |
| `wipeBranch()` | ~1120 | POST `/api/platform/branch-wipe` |
| `deployBranch()` | ~1140 | POST `/api/platform/branch-deploy` |
| `pollHeartbeatProgress()` | ~1150 | Poll `/api/platform/heartbeat-progress`, update bar |
| `renderTodoDetailModal()` | ~1200 | Render todo detail overlay |
| `renderMarkdownSimple(md)` | ~1270 | Basic markdown → HTML renderer |

### SSE Event Types (consumed by frontend)

| Event | Data Shape | Handler |
|-------|-----------|---------|
| `phase` | `{phase: "..."}` | Updates spinner label |
| `progress` | `{done, total, message}` | Updates spinner progress |
| `tool_call` | `{tool: "...", args: {...}}` | Adds `.msg.tool` bubble |
| `tool_result` | `{result: "..."}` | Adds `.msg.tool` bubble |
| `message` | `{content: "..."}` | Adds `.msg.assistant` bubble |
| `done` | `{status: "success|failure|..."}` | Adds `.msg.success/.msg.error`, stops spinner |
| `heartbeat_start` | `{todo_id, task}` | Shows heartbeat progress bar |
| `heartbeat_end` | `{todo_id, result}` | Hides bar, reloads todos |

---

## 6. Key Constants, Config, and State Variables

### Config Object (main.py, ~20)

```python
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
```

Persisted to `.config.json` via `_save_config()` (line ~37).

### Agent Prompt Constants (main.py)

| Constant | Line | Value |
|----------|------|-------|
| `DIRECT_AGENT_PROMPT` | ~70 | System prompt for the direct agent (tools, approach guidelines, port info) |
| `TODO_TD_REVIEW_PROMPT` | ~380 | TD review prompt for single-todo execution |
| `_CONTEXT_MAP_PROMPT` | ~435 | LLM prompt for auto-generating CONTEXT_MAP.md |
| `_DATA_FLOW_PROMPT` | ~455 | LLM prompt for auto-generating DATA_FLOW.md |
| `TD_ANALYSIS_PROMPT` | ~515 | TD analysis prompt for cross-project analysis |

### State Variables (main.py)

| Variable | Line | Type | Purpose |
|----------|------|------|---------|
| `_direct_state` | ~150 | `{"project_dir": None, "project_name": "", "port": 0}` | Active project state |
| `_heartbeat_progress` | ~150 | dict | Live heartbeat execution progress (SSE) |
| `_CONVERSATION_HISTORY_LIMIT` | ~155 | `50` | Max conversation files per project |
| `_CONVERSATION_TOKEN_BUDGET` | ~156 | `50_000` | Max tokens before summarization |
| `_PROD_ROOT` | ~300 | `Path` | Production platform root `/home/aeli/projects/aelidirect_prod` |

### Port Constants (pod.py)

| Constant | Line | Value |
|----------|------|-------|
| `PORT_RANGE` | ~15 | `range(11001, 11099)` — project pod range |
| `INTERNAL_PORT` | ~16 | `8000` — all containers listen on 8000 internally |

### Read-Only Tool Detection Constants (main.py)

| Constant | Line | Purpose |
|----------|------|---------|
| `READ_ONLY_TOOLS` | ~43 | Frozenset of read-only tool names |
| `_BASH_READONLY_PREFIXES` | ~46 | Shell command prefixes considered read-only |
| `_is_readonly_tool_call()` | ~58 | Detection function |

### File Extension Filters (tools.py)

| Constant | Line | Value |
|----------|------|-------|
| `_CODE_EXTENSIONS` | ~97 | Set of code file extensions to include in `read_project` |
| `_SKIP_DIRS` | ~102 | Directories to always skip |
| `READ_PROJECT_BUDGET` | ~94 | Max chars for full project read (~100k) |

### Platform Project Branch Paths (tools.py)

| Constant | Line | Value |
|----------|------|-------|
| `_BRANCH_ROOT` | ~25 | `/home/aeli/projects/aelidirect_branch` |
| `_PLATFORM_PROJECT_NAME` | ~25 | `"aelidirect_platform"` |

### LLM Client Constants (llm_client.py)

| Constant | Line | Value |
|----------|------|-------|
| `TIMEOUT` | ~10 | `180.0` seconds |
| `RETRYABLE_CODES` | ~11 | `{429, 502, 503, 504}` |
| `MAX_RETRIES` | ~12 | `3` |
| `RETRY_DELAY` | ~13 | `3.0` seconds |

### Pod Version Tracking (pod.py)

- Pod versions tracked via `version` parameter in `spin_up_pod()` (pod.py line ~130)
- Increment handled by calling code (not in pod.py itself)