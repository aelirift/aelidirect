<think>
The user wants me to generate a CONTEXT_MAP.md file that maps the entire aelidirect project. This is a fairly complex FastAPI-based AI agent platform. Let me analyze the source code carefully and produce a comprehensive context map.

Let me organize what I know from the code:

1. **File Structure** - The project has:
   - backend/ directory with Python files
   - frontend/index.html
   - Various documentation files

2. **API Endpoints** - I can see them in the code

3. **Tools/Functions available to LLM** - From tools.py

4. **Data directories** - From constants.py
   - PROJECTS_ROOT
   - MEMORY_DIR
   - CONVERSATIONS_DIR
   - TODOS_DIR
   - HEARTBEATS_DIR
   - TD_REPORTS_DIR

5. **Frontend components** - From index.html

6. **Constants and state** - From constants.py and state.py

Let me go through the code systematically to extract all the information.

From the code I've seen, here's what I can document:

### backend/ files:
1. `app.py` - Main FastAPI app, routing
2. `state.py` - State management
3. `pipeline.py` - Main chat pipeline (SSE streaming, agent loop)
4. `heartbeat.py` - Heartbeat scheduler, todo/heartbeat API routes
5. `platform_routes.py` - Branch/prod management routes
6. `history.py` - Conversation persistence
7. `td.py` - TD (Technical Director) review endpoints
8. `docs.py` - Auto-documentation regeneration
9. `tools.py` - Tool definitions and executors for the LLM
10. `direct_todo.py` - Todo list and heartbeat management


11. `llm_client.py` - LLM client (OpenRouter, MiniMax)
12. `pod.py` - Pod management (containerized deployment)
13. `test_agent.py` - Two-phase test agent
14. `constants.py` - All shared constants

### API Endpoints:
From app.py:
- GET /api/direct/projects - List projects
- GET /api/direct/projects/{project_dir} - Get project details
- POST /api/direct/chat/start - Start a chat session
- GET /api/direct/chat/stream/{session_id} - SSE stream for chat
- POST /api/direct/chat/{session_id}/message - Send message
- GET /api/direct/todos/{project_dir} - Get todos
- POST /api/direct/todos/{project_dir} - Create todo
- GET /api/direct/heartbeat/{project_dir} - Get heartbeat status
- POST /api/direct/heartbeat/{project_dir} - Configure heartbeat
- GET /api/platform/branch-status - Branch status
- POST /api/platform/branch-wipe - Wipe branch
- POST /api/platform/branch-deploy - Deploy branch
- GET /api/platform/heartbeat-progress - Heartbeat progress
- DELETE /api/direct/history/{project_dir} - Erase history
- GET /api/direct/history/{project_dir} - Get history
- POST /api/td-analysis - Run TD analysis
- GET /api/td-analysis - Get latest TD analysis
- GET /api/td-reports - List TD reports
- GET /api/td-reports/{timestamp} - Get specific report
- POST /api/config - Set config
- GET /api/config - Get config
- GET /api/config/providers - Get providers
- POST /api/platform/config-verify - Verify API key
- GET /api/health - Health check

The LLM has access to several file manipulation tools: reading and listing files, patching or creating files, viewing file tails and specific line ranges, and grepping through code. I can also query the project's entire codebase at once, and there's a tool for checking pod status.

Beyond the file tools, there are utilities for managing deployments (spinning up containers, checking status, viewing logs), running commands via bash, interacting with git repositories, persisting and retrieving memories, and executing test scenarios. The heartbeat endpoint is also available for coordination.

The system manages several data directories for storing projects, conversation histories, todos, and heartbeat state across different instances. Key configuration points include the production port at 10100, a branch environment at 10101, and a range of pod ports available for deployments. The platform can handle up to 150 action turns per interaction with a maximum of 2 test-fix iterations per cycle.

On the frontend, the UI provides a sidebar for project navigation, chat messaging through SSE connections, a todo panel for task management, and heartbeat controls. Users can monitor deployment status, adjust configuration settings, and access a branch testing bar with deploy capabilities.
</think>

# aelidirect -- Context Map

## File Structure

```
aelidirect/
├── frontend/
│   └── index.html                  # Single-page application (SPA) — chat UI, todo panel, config, branch management
├── backend/
│   ├── app.py                      # FastAPI app entry point, CORS, static files, all router registration
│   ├── pipeline.py                 # Core SSE streaming pipeline: planning → coding → test → TD review phases
│   ├── tools.py                    # Tool definitions (JSON schemas) + executors for LLM agent
│   ├── state.py                    # Global config state, provider selection, port management
│   ├── constants.py                # Single source of truth: all paths, ports, limits, timeouts
│   ├── heartbeat.py                # Todo scheduler executor + heartbeat/todo CRUD API routes
│   ├── direct_todo.py              # Todo list + heartbeat JSON persistence layer
│   ├── history.py                  # Conversation persistence + history API routes
│   ├── td.py                       # TD (Technical Director) analysis + report API routes
│   ├── docs.py                     # Auto-regeneration of SPEC.md, CONTEXT_MAP.md, DATA_FLOW.md, SITE_MAP.md
│   ├── llm_client.py               # HTTP LLM client (OpenRouter/MiniMax), retry logic, response parser
│   ├── pod.py                      # Podman container management: build, run, health check, destroy
│   └── test_agent.py              # Two-phase test agent: plan (LLM) → run (httpx/Playwright/unit)
├── projects/                       # Generated project directories (one per user project)
├── .direct_conversations/          # JSON conversation archives (one dir per project)
├── .direct_todos/                  # JSON todo lists (one per project)
├── .direct_heartbeats/             # JSON heartbeat configs (one per project)
├── .direct_memory/                 # Markdown memories (one dir per project)
├── .td_reports/                   # TD analysis markdown reports
└── .config.json                    # Platform configuration (API keys, selected provider)
```

---

## API Endpoints

### Direct Chat (`pipeline.py`, `app.py`)

| Method | Path | Handler | Description | Line |
|--------|------|---------|-------------|------|
| POST | `/api/direct/start` | `direct_start` | Initialize project/create conversation, return stream URL | `pipeline.py:~280` |
| GET | `/api/direct/stream` | `direct_stream` | SSE event stream: planning → coding → test → TD review | `pipeline.py:~320` |

**SSE Events emitted** by `/api/direct/stream`:
| Event | Payload | Phase |
|-------|---------|-------|
| `phase` | `{"phase": "planning\|coding\|testing\|post_test"}` | All |
| `turn` | `{"turn": N, "action_turns": N, "max": N}` | All |
| `thinking` | `{"content": "..."}` | Planning/Coding |
| `tool_call` | `{"name": "...", "args": {...}}` | Coding |
| `tool_result` | `{"name": "...", "result": "..."}` | Coding |
| `response` | `{"content": "..."}` | Coding/Post |
| `test_phase` | `{"status": "planning\|running\|all_passed\|error", ...}` | Testing |
| `test_feedback` | `{"failed": N, "iteration": N, ...}` | Testing |
| `td_review` | `{"status": "running\|complete\|error", "review": "..."}` | Post-test |
| `pod_url` | `{"url": "..."}` | Post-test |
| `done` | `{"turns", "action_turns", "test_evidence", "td_review"}` | Final |
| `error` | `{"message": "...", "traceback": "..."}` | Any |

### Todo Routes (`heartbeat.py`)

| Method | Path | Handler | Description | Line |
|--------|------|---------|-------------|------|
| GET | `/api/direct/todos/{project_dir}` | `api_get_todos` | List all todos | `heartbeat.py:~155` |
| POST | `/api/direct/todos/{project_dir}` | `api_add_todo` | Add a todo | `heartbeat.py:~160` |
| PUT | `/api/direct/todos/{project_dir}/{todo_id}` | `api_update_todo` | Update todo status/result | `heartbeat.py:~166` |
| GET | `/api/direct/todos/{project_dir}/{todo_id}` | `api_get_todo` | Get single todo (enriched with schedule info) | `heartbeat.py:~174` |
| DELETE | `/api/direct/todos/{project_dir}/{todo_id}` | `api_delete_todo` | Delete a todo | `heartbeat.py:~216` |

### Heartbeat Routes (`heartbeat.py`)

| Method | Path | Handler | Description | Line |
|--------|------|---------|-------------|------|
| GET | `/api/direct/heartbeat/{project_dir}` | `api_get_heartbeat` | Get heartbeat config + pending count | `heartbeat.py:~222` |
| POST | `/api/direct/heartbeat/{project_dir}` | `api_set_heartbeat` | Enable/disable/configure heartbeat | `heartbeat.py:~244` |
| POST | `/api/direct/heartbeat/{project_dir}/run` | `api_run_heartbeat_now` | Execute next pending todo via chat pipeline | `heartbeat.py:~257` |
| GET | `/api/platform/heartbeat-progress` | `get_heartbeat_progress` | Poll active todo execution progress | `heartbeat.py:~300` |

### History Routes (`history.py`)

| Method | Path | Handler | Description | Line |
|--------|------|---------|-------------|------|
| GET | `/api/direct/history/{project_dir}` | `get_direct_history` | List recent conversations | `history.py:~110` |
| DELETE | `/api/direct/history/{project_dir}` | `erase_history` | Erase all conversation history | `history.py:~95` |

### Platform/Branch Routes (`platform_routes.py`)

| Method | Path | Handler | Description | Line |
|--------|------|---------|-------------|------|
| GET | `/api/platform/branch-status` | `get_branch_status` | Compare branch vs prod source files | `platform_routes.py:~28` |
| POST | `/api/platform/branch-wipe` | `wipe_branch` | Reset branch to match prod (source + data + config) | `platform_routes.py:~55` |
| POST | `/api/platform/branch-deploy` | `deploy_branch` | Deploy branch to prod (copy source, sync cache, restart) | `platform_routes.py:~95` |

### TD Analysis Routes (`td.py`)

| Method | Path | Handler | Description | Line |
|--------|------|---------|-------------|------|
| GET | `/api/td-analysis` | `get_latest_td_analysis` | Get most recent TD report | `td.py:~95` |
| POST | `/api/td-analysis` | `run_td_analysis` | Run TD analysis across all projects/conversations | `td.py:~50` |
| GET | `/api/td-reports` | `list_td_reports` | List all TD reports | `td.py:~102` |
| GET | `/api/td-reports/{timestamp}` | `get_td_report` | Get specific TD report | `td.py:~111` |

### Config Routes (`state.py` / `app.py`)

| Method | Path | Handler | Description | Line |
|--------|------|---------|-------------|------|
| GET | `/api/config` | `get_config` | Get full config | `state.py:~75` |
| POST | `/api/config` | `set_config` | Update config (selected provider, api keys) | `state.py:~90` |
| GET | `/api/config/providers` | `get_providers` | List available LLM providers | `state.py:~70` |
| POST | `/api/platform/config-verify` | `verify_config` | Verify API key works | `state.py:~110` |
| GET | `/api/health` | `health_check` | Health check | `app.py:~55` |

---

## LLM Agent Tools

### Tool Definitions (sent to LLM as JSON schemas)

From `tools.py` lines 1–350:

| Tool Name | Description | Parameters |
|-----------|-------------|------------|
| `list_files` | List files in a directory | `path: string` |
| `read_file` | Read a file (cached, truncated at 16k chars) | `path: string` |
| `edit_file` | Create or fully rewrite a file | `path: string, content: string` |
| `patch_file` | Targeted edit: replace exact `old_text` with `new_text` | `path, old_text, new_text` |
| `read_file_tail` | Read last N lines (default 50) | `path: string, lines?: integer` |
| `read_lines` | Read specific line range (1-indexed, ±20 line padding) | `path: string, start: integer, end: integer` |
| `grep_code` | Case-insensitive search across all project files | `pattern: string` |
| `read_project` | Read all source files at once (budget cap at 100k chars) | none |

### Built-in Pipeline Tools (executed in `pipeline.py` lines 680–850)

| Tool Name | Description | Line |
|-----------|-------------|------|
| `deploy_pod` | Build + run + health-check container, return pod URL | `~700` |
| `check_pod` | GET request to pod endpoint, return status + body | `~720` |
| `restart_platform` | `systemctl restart aelidirect-branch` on port 10101 | `~725` |
| `http_check` | HTTP GET to active pod | `~740` |
| `bash` | Run shell command (60s timeout) | `~745` |
| `git_status` / `git_diff` / `git_log` / `git_commit` | Git operations | `~755–780` |
| `memory_save` / `memory_load` / `memory_list` | Long-term memory CRUD | `~785–800` |
| `test_agent` | Invoke two-phase test agent (plan → run → fix loop) | `~805` |

### Pod Management Tools (`pod.py`)

| Tool Name | Description | Parameters |
|-----------|-------------|------------|
| `list_project_files` | List generated project files | none |
| `read_project_file` | Read file from generated project | `path: string` |
| `edit_project_file` | Create/overwrite file in generated project | `path: string, content: string` |
| `check_pod_status` | Podman pod status + HTTP health check | none |
| `get_container_logs` | Podman logs (default 80 lines) | `tail?: integer` |

---

## Data Directories and Formats

From `constants.py` lines 1–50:

| Directory | Constant | Format |
|-----------|----------|--------|
| Projects | `PROJECTS_ROOT` | One subdirectory per project; contains `main.py`, `project_env.md`, generated files |
| Conversations | `CONVERSATIONS_DIR` | One JSON file per conversation: `{timestamp, user_message, messages[], llm_summary, test_evidence}` | `backend/.direct_conversations/` |
| Todos | `TODOS_DIR` | One JSON file per project: `[{id, task, category, status, created_at, started_at, completed_at, duration_secs, attempts, result_status, last_result, td_review}]` |
| Heartbeats | `HEARTBEATS_DIR` | One JSON file per project: `{enabled, interval_minutes, last_run, next_run, running, history[]}` |
| Memories | `MEMORY_DIR` | One `.md` file per memory key; content is raw markdown | `backend/.direct_memory/{project}/` |
| TD Reports | `TD_REPORTS_DIR` | One `.md` file per analysis run | `backend/.td_reports/{timestamp}.md` |
| Config | `CONFIG_FILE` | JSON: `{selected, providers: {openrouter: {api_key, base_url, model}, minimax: {...}}}` | `backend/.config.json` |
| Ports | `PORTS_FILE` | JSON: `{project_name: port}` | `backend/.ports.json` |

---

## Frontend Components and Key JS Functions

From `frontend/index.html`:

### Layout Structure

```
body
├── .shell
│   ├── .sidebar (width: 200px, sticky)
│   │   ├── .sidebar-brand (aelidirect logo)
│   │   ├── .sidebar-section-label + .sidebar-projects
│   │   │   └── .sidebar-project-item (clickable project buttons)
│   │   └── .sidebar-actions (New Project, Config)
│   └── .main-content
│       └── .view#chat-view / .view#config-view (toggle)
│           ├── .chat-main
│           │   ├── .project-bar (project name, dir, deploy button)
│           │   ├── .messages (chat bubbles)
│           │   ├── .sticky-spinner (pulse dot + step label)
│           │   ├── .input-area (.pod-bar + textarea + send button)
│           │   └── .branch-bar (branch status / heartbeat progress)
│           └── .right-panel (Todo + Heartbeat tabs)
```

### Key JavaScript Functions

| Function | Description | Line (approx) |
|----------|-------------|---------------|
| `loadProjects()` | Fetch project list, populate sidebar | ~400 |
| `selectProject(name, dir)` | Switch active project, load todos/heartbeat | ~500 |
| `sendMessage()` | POST to `/api/direct/start`, then SSE via EventSource | ~600 |
| `handleSSE(event)` | Route SSE events to appropriate render functions | ~700 |
| `addMsg(role, content)` | Append message bubble to `.messages` | ~800 |
| `renderToolCall(name, args)` | Format tool call display | ~820 |
| `renderToolResult(name, result)` | Format tool result display | ~830 |
| `renderDone(data)` | Show final result, pod URL, deploy button | ~900 |
| `loadTodos()` | Fetch todos for current project, render panel | ~950 |
| `renderTodoPanel(todos)` | Render todo list with status icons, Run/Delete buttons | ~1000 |
| `addTodo(task)` | POST new todo | ~1050 |
| `runTodo(todoId)` | POST `/api/direct/heartbeat/{project}/run` with specific todo | ~1070 |
| `loadHeartbeat()` | Fetch/configure heartbeat, render panel | ~1100 |
| `renderHeartbeatPanel(hb)` | Render controls, queue, history | ~1150 |
| `checkBranchStatus()` | GET `/api/platform/branch-status` | ~1250 |
| `wipeBranch()` / `deployBranch()` | POST to branch management endpoints | ~1270–1290 |
| `pollHeartbeatProgress()` | Poll `/api/platform/heartbeat-progress` every 5s | ~1310 |
| `renderTodoDetailModal(modal, t, schedule)` | Full-screen todo detail overlay | ~1400 |
| `renderMarkdownSimple(md)` | Convert markdown to HTML | ~1500 |

### CSS Classes (styling categories)

| Pattern | Purpose |
|---------|---------|
| `.msg.user/assistant/system/tool/error/success` | Chat message bubbles |
| `.sticky-spinner`, `.pulse-dot` | Activity indicator |
| `.pod-bar`, `.pod-open-btn` | Deployment status bar |
| `.branch-bar`, `.branch-btn` | Branch test/deploy controls |
| `.hb-toggle` (`.on`/`.off`) | Heartbeat toggle switch |
| `.todo-detail-*` | Full-screen todo detail modal |
| `.right-panel-tabs button.active` | Active tab highlight |

---

## Key Constants and Config

From `backend/constants.py`:

### Ports
```python
PROD_PORT = 10100        # Production server
BRANCH_PORT = 10101     # Branch (testing) server
POD_PORT_RANGE = range(11001, 11099)   # Generated project containers
CONTAINER_INTERNAL_PORT = 8000          # All containers listen internally on 8000
```

### Limits
```python
MAX_ACTION_TURNS = 150                    # Max tool-call turns per conversation
MAX_TEST_FIX_ITERATIONS = 2              # Max coder→test→fix cycles
CONVERSATION_HISTORY_LIMIT = 50           # Max archived conversations per project
SUMMARIZE_BATCH_SIZE = 10                 # Conversations summarized at once
TD_ANALYSIS_RECENT_COUNT = 30             # Conversations in TD analysis
```

### Timeouts (seconds)
```python
SUBPROCESS_TIMEOUT = 10                   # git, systemctl
SUBPROCESS_TIMEOUT_LONG = 60             # bash tool
CONTAINER_BUILD_TIMEOUT = 120            # Podman build
LLM_STREAM_TIMEOUT = 600.0              # 10 min SSE stream
LLM_TIMEOUT = 180.0                     # LLM API call
```

### File Limits
```python
READ_PROJECT_BUDGET = 100_000            # Max chars for read_project tool
READ_FILE_TRUNCATE = 16_000             # Truncate single files
FILE_TAIL_LINES = 20                    # Lines shown at end of truncated files
TRUNCATE_TOOL_RESULT = 2_000            # Tool result back to LLM
TRUNCATE_TD_INPUT = 12_000              # Input to TD review LLM
```

### Platform Self-Editing
```python
PLATFORM_PROJECT_NAME = "aelidirect_platform"
BRANCH_ROOT = Path("/home/aeli/projects/aelidirect_branch")
PLATFORM_SOURCE_FILES = [
    "frontend/index.html",
    "backend/app.py", "backend/state.py", "backend/pipeline.py",
    "backend/heartbeat.py", "backend/platform_routes.py", "backend/history.py",
    "backend/td.py", "backend/docs.py", "backend/tools.py",
    "backend/direct_todo.py", "backend/llm_client.py", "backend/pod.py",
    "backend/test_agent.py", "backend/constants.py",
]
```

---

## Global State (`backend/state.py`)

```python
config = {
    "selected": "openrouter",                    # Active provider key
    "providers": {
        "openrouter": {
            "api_key": "...",                    # Set via UI
            "base_url": "https://openrouter.ai/api/v1",
            "model": "anthropic/claude-3.5-sonnet"
        },
        "minimax": {
            "api_key": "...",                    # Set via UI
            "base_url": "https://api.minimax.chat",
            "model": "MiniMax-Text-01"
        }
    }
}

_direct_state = {
    "project_dir": Path,                          # Current project path
    "project_name": str,                          # Human-readable name
    "port": int,                                  # Assigned pod port
}

_heartbeat_progress = {
    "active": bool,
    "project": str,
    "todo_id": str,
    "task": str,
    "step": str,                                  # Current operation
    "turn": int,                                  # Coding turns used
    "max_turns": int,
    "total_steps": int,
    "started_at": str,                            # ISO timestamp
    "finished_at": str,
    "result_status": str,                         # success/failure/partial
    "result_message": str,
}
```

---

## Agent Prompts

| Prompt | Source | Purpose |
|--------|--------|---------|
| `DIRECT_AGENT_PROMPT` | `pipeline.py` | Core system prompt for the coding agent — instructions, rules, tool usage guidelines |
| `PLAN_SYSTEM_PROMPT` | `test_agent.py` | Test planning prompt — instructs LLM to generate structured JSON test plans with setup/steps/assertions |
| `TD_ANALYSIS_PROMPT` | `td.py` | TD review prompt — analyze conversations for bugs, fixes, patterns, recommendations |
| `TODO_TD_REVIEW_PROMPT` | `pipeline.py` | Per-conversation TD review — verdict on a single task's success/failure |
| `_CONTEXT_MAP_PROMPT` | `docs.py` | Auto-generate CONTEXT_MAP.md |
| `_DATA_FLOW_PROMPT` | `docs.py` | Auto-generate DATA_FLOW.md |
| `_SPEC_PROMPT` | `docs.py` | Auto-generate SPEC.md |
| Site Map prompt | `docs.py` | Auto-generate SITE_MAP.md |