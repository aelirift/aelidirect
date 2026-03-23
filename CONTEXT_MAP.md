<think>
The user wants me to create a CONTEXT_MAP.md document that maps out the entire codebase structure for the aelidirect project. Let me analyze the provided source files carefully:

1. **backend/tools.py** - Tools for LLM agent, file operations, caching
2. **backend/direct_todo.py** - Todo list and heartbeat auto-executor
3. **backend/llm_client.py** - Minimal LLM client for OpenRouter and MiniMax
4. **backend/pod.py** - Pod management, build/run containers
5. **backend/test_agent.py** - Two-phase automated testing
6. **backend/constants.py** - All shared constants
7. **frontend/index.html** - Standalone agent UI

I need to map:
1. File structure with purpose
2. API endpoints (method, path, handler, line number) - but I don't see main.py in the provided files... Let me note this
3. Tools/functions available to LLM
4. Data directories and formats
5. Frontend components and key JS functions
6. Key constants and config

Let me create a comprehensive context map.
</think>

# aelidirect -- Context Map

## 1. File Structure

| File | Purpose | Key Exports |
|------|---------|-------------|
| `backend/constants.py` | Single source of truth for all shared constants (paths, ports, timeouts, limits) | All module-level constants |
| `backend/tools.py` | LLM tool definitions and executors (file ops, caching, project management) | `TOOL_DEFINITIONS`, `execute_tool()` |
| `backend/llm_client.py` | Minimal LLM client (OpenRouter + MiniMax), HTTP with retry | `call_llm()`, `extract_response()`, `LLMError` |
| `backend/direct_todo.py` | Todo list CRUD + heartbeat auto-executor, JSON file storage | `add_todo()`, `update_todo()`, `get_todos()`, `get_heartbeat()` |
| `backend/pod.py` | Podman container lifecycle (build, run, health-check, destroy) | `spin_up_pod()`, `POD_TOOL_DEFINITIONS`, `execute_pod_tool()` |
| `backend/test_agent.py` | Two-phase test agent (plan + run), supports API/browser/unit tests | `plan_tests()`, `run_tests()`, `test_and_fix_loop()`, `handle_test_agent()` |
| `frontend/index.html` | Standalone agent UI (chat, todo panel, heartbeat panel, config, branch testing) | All inline JS at bottom of file |

**Notable absence:** `backend/main.py` is not provided but referenced in constants (`PLATFORM_SOURCE_FILES`). All API routes are defined there.

---

## 2. Available LLM Tools (from `tools.py`)

All tools are defined as JSON schemas in `TOOL_DEFINITIONS` (lines 156–273) and executed by `execute_tool()` (line 290).

| Tool Name | Description | Parameters | Line |
|-----------|-------------|------------|------|
| `list_files` | List all files in project directory | `path` (string) | 158 |
| `read_file` | Read file contents (truncates at 16k chars) | `path` (string) | 169 |
| `edit_file` | Create or fully rewrite a file | `path`, `content` | 186 |
| `patch_file` | Targeted edit: find `old_text`, replace with `new_text` | `path`, `old_text`, `new_text` | 202 |
| `read_file_tail` | Read last N lines of a file | `path`, `lines` (int, default 50) | 218 |
| `read_lines` | Read specific line range (1-indexed, padded ±20) | `path`, `start`, `end` | 236 |
| `grep_code` | Case-insensitive search across all project files | `pattern` (string) | 250 |
| `read_project` | Read ALL source files at once (budget: 100k chars) | none | 264 |

### Pod/Diagnostics Tools (from `pod.py`)

| Tool Name | Description | Line |
|-----------|-------------|------|
| `list_project_files` | List files in generated project | 363 |
| `read_project_file` | Read file from generated project | 372 |
| `edit_project_file` | Write file to generated project | 385 |
| `check_pod_status` | Check if pod is running + HTTP health | 395 |
| `get_container_logs` | Read container stdout/stderr | 408 |

---

## 3. Data Directories and Formats

All data dirs are defined in `constants.py` (lines 10–20) and auto-created on import.

| Directory | Constant | Format | Purpose |
|-----------|----------|--------|---------|
| `backend/.direct_todos/` | `TODOS_DIR` | JSON (one file per project) | Todo list persistence |
| `backend/.direct_heartbeats/` | `HEARTBEATS_DIR` | JSON (one file per project) | Heartbeat config + history |
| `backend/.direct_memory/` | `MEMORY_DIR` | — | Memory/conversation context |
| `backend/.direct_conversations/` | `CONVERSATIONS_DIR` | — | Conversation history |
| `backend/.td_reports/` | `TD_REPORTS_DIR` | — | Test-driven review reports |
| `backend/.ports.json` | `PORTS_FILE` | JSON dict | Port allocation per project |
| `backend/.config.json` | `CONFIG_FILE` | JSON | LLM provider config |
| `projects/` | `PROJECTS_ROOT` | dir per project | Generated code projects |
| `aelidirect_branch/` | `BRANCH_ROOT` | — | Branch copy for testing edits |

### Todo JSON Schema (per file in TODOS_DIR)
```json
{
  "id": "string (8 chars)",
  "task": "string",
  "category": "feature|debug|question|refactor",
  "status": "pending|attempted|done",
  "created_at": "ISO datetime",
  "started_at": "ISO datetime|null",
  "completed_at": "ISO datetime|null",
  "duration_secs": "int|null",
  "attempts": "int",
  "result_status": "success|failure|partial|null",
  "last_result": "string|null",
  "td_review": "string|null"
}
```

### Heartbeat JSON Schema (per file in HEARTBEATS_DIR)
```json
{
  "enabled": "bool",
  "interval_minutes": "int",
  "last_run": "ISO datetime|null",
  "next_run": "ISO datetime|null",
  "running": "bool",
  "history": [{"timestamp","todo_id","task","result"}, ...] // last 50
}
```

---

## 4. Key Constants (from `constants.py`)

### Paths
```python
PROD_ROOT = backend/..         # aelidirect/ root
BRANCH_ROOT = /home/aeli/projects/aelidirect_branch
PROJECTS_ROOT = PROD_ROOT / "projects"
```

### Ports
```python
PROD_PORT = 10100
BRANCH_PORT = 10101
POD_PORT_RANGE = range(11001, 11099)
CONTAINER_INTERNAL_PORT = 8000
```

### Limits
```python
MAX_ACTION_TURNS = 150
MAX_TEST_FIX_ITERATIONS = 3
CONVERSATION_HISTORY_LIMIT = 50
CONVERSATION_TOKEN_BUDGET = 50_000
```

### File Reading
```python
READ_PROJECT_BUDGET = 100_000   # chars for read_project tool
READ_FILE_TRUNCATE = 16_000    # truncate at 16k
FILE_TAIL_LINES = 20
```

### LLM
```python
LLM_TIMEOUT = 180.0
LLM_RETRYABLE_CODES = {429, 502, 503, 504}
LLM_MAX_RETRIES = 3
LLM_MAX_TOKENS = 16_000
```

### Code Extensions
```python
CODE_EXTENSIONS = {".py", ".html", ".js", ".ts", ".css", ".yaml", ".json", ...}
SKIP_DIRS = {"venv", "node_modules", "__pycache__", ".git", ...}
```

---

## 5. Frontend Components and Key JS Functions

All frontend code is in `frontend/index.html` as inline `<script>` at the bottom.

### Layout Structure
- **Shell** (`class="shell"`) → Sidebar (200px) + Main Content
- **Sidebar** → Brand, Project List, New/Config buttons
- **Main Content** → Chat View or Config View (toggled via `class="view active"`)
- **Chat View** → Chat Main + Right Panel (Todo + Heartbeat)
- **Right Panel** → Tabs: Todo Panel / Heartbeat Panel

### Core JS Functions

| Function | Purpose | Line (approx) |
|----------|---------|--------------|
| `loadProjects()` | Fetch `/api/platform/projects`, render sidebar list | ~1800 |
| `switchProject(name)` | Switch active project, update UI | ~1830 |
| `openConfig()` / `closeConfig()` | Toggle config view visibility | ~1845/1855 |
| `startChat()` | Begin SSE chat session via `/api/direct/start` | ~1870 |
| `addMsg(type, content)` | Append message bubble to `.messages` | ~1900 |
| `pollStream(url)` | Consume SSE events, handle response/done/error | ~1920 |
| `loadTodos()` | Fetch `/api/direct/todos`, render todo panel | ~1980 |
| `addTodo()` | POST to `/api/direct/todo/add`, reload | ~2000 |
| `attemptTodo(id)` | POST to `/api/direct/todo/attempt/{id}` | ~2010 |
| `deleteTodo(id)` | DELETE to `/api/direct/todo/{id}` | ~2020 |
| `renderTodoItem(t)` | Build HTML for a single todo row | ~2030 |
| `renderTodoDetailModal(modal, t, schedule)` | Build full detail view modal | ~2080 |
| `loadHeartbeat()` | Fetch `/api/platform/heartbeat`, render queue | ~2200 |
| `saveHeartbeat(enabled, interval)` | POST to `/api/platform/heartbeat` | ~2240 |
| `checkBranchStatus()` | Fetch `/api/platform/branch-status` | ~2280 |
| `pollHeartbeatProgress()` | Poll `/api/platform/heartbeat-progress` | ~2350 |
| `wipeBranch()` | POST `/api/platform/branch-wipe` | ~2270 |
| `deployBranch()` | POST `/api/platform/branch-deploy` | ~2280 |
| `renderMarkdownSimple(md)` | Convert markdown to HTML | ~2130 |
| `escHtml(s)` | Escape HTML entities | ~1700 |
| `_fmtTs(ts)` / `_fmtDuration(secs)` | Format timestamps and durations | ~1740/1760 |

### Frontend State Variables
```javascript
_currentProject = ""           // active project name
_projectData = {}            // {name: {todos, heartbeat, ...}}
_sse = null                   // active EventSource
_streamUrl = ""               // SSE stream URL
_branchIsBranch = false        // true if running on branch server
_hbProgressActive = false     // heartbeat progress polling active
_hbProgressTimer = null       // interval ID for fast polling
_hbProgressLastFinished = ""  // last finished timestamp
```

---

## 6. Test Agent Functions (from `test_agent.py`)

### Test Plan/Run Flow
```python
load_source_batch(scope)       # Load platform files as single string (line 80)
plan_tests(scope, context)    # Phase 1: LLM generates JSON test plan (line 155)
run_tests(plan)               # Phase 2: Execute each test case (line 215)
test_and_fix_loop(...)        # Full loop: plan → run → fix → repeat (line 380)
handle_test_agent(args)       # Tool interface entry point (line 435)
```

### Test Execution Functions
| Function | Test Type | Line |
|----------|-----------|------|
| `_run_api_test(tc, base_url)` | HTTP via `httpx.AsyncClient` | 265 |
| `_run_browser_test(tc, base_url)` | Playwright browser automation | 320 |
| `_run_unit_test(tc)` | Direct Python import/function call | 450 |
| `_run_setup_steps(setup, base_url)` | Precondition creation via API | 230 |

### Plan Format
```json
{
  "summary": "string",
  "test_cases": [
    {
      "id": "T1",
      "name": "string",
      "type": "api|browser|unit",
      "setup": [{"action": "...", "details": {"method": "POST", "path": "...", "body": {}}}],
      "steps": [{"action": "...", "details": {"method": "...", "path": "...", ...}}],
      "expected": "string",
      "assertions": ["string"]
    }
  ]
}
```

---

## 7. Pod Lifecycle Functions (from `pod.py`)

| Function | Purpose | Line |
|----------|---------|------|
| `spin_up_pod(project_dir, project_name, host_port, version)` | Full lifecycle: destroy → build → start → health check | 185 |
| `build_image(project_dir, image_name)` | Podman build from project dir | 115 |
| `_create_pod(pod_name, image_name, host_port)` | Podman pod + container run | 155 |
| `health_check(port, path, retries, delay)` | Poll until HTTP 200 | 170 |
| `_force_destroy_pod(pod_name)` | Immediate pod removal | 145 |
| `detect_app_type(project_dir)` | Detect FastAPI/Flask/static | 60 |
| `generate_containerfile(project_dir, app_type, port)` | Generate `Containerfile` content | 75 |
| `get_available_port(project_name)` | Allocate from `POD_PORT_RANGE` | 40 |
| `list_pods()` | List all aelimini-* pods | 265 |
| `http_get(port, path)` | HTTP GET for health/status checks | 295 |

---

## 8. Dual Cache System (from `tools.py`)

Platform editing uses two parallel caches for branch/prod divergence:

| Function | Purpose | Line |
|----------|---------|------|
| `file_cache_get(project, path)` | Read from branch cache (platform) or main cache | 45 |
| `file_cache_set(project, path, content)` | Write to branch cache (platform) or main cache | 55 |
| `file_cache_set_main(project, path, content)` | Direct main cache write (init/wipe) | 62 |
| `file_cache_wipe_branch()` | Copy main → branch (branch wipe) | 68 |
| `file_cache_deploy_to_main()` | Copy branch → main (successful deploy) | 75 |
| `file_cache_clear(project)` | Clear caches for project | 82 |

Cache keys: `tuple(str(project.resolve()), path)`

---

## 9. LLM Client (from `llm_client.py`)

| Function | Purpose | Line |
|---------|---------|------|
| `call_llm(provider, api_key, base_url, model, messages, tools, temperature)` | Single LLM API call with retry | 35 |
| `extract_response(raw)` | Parse response into `{type, content, tool_calls, raw}` | 75 |
| `LLMError` | Exception class with status_code and response_body | 22 |

**Provider detection:** If `"minimax"` in provider → `/text/chatcompletion_v2`, otherwise → `/chat/completions`

---

## 10. Project Environment Files

| Function | Purpose | Line |
|----------|---------|------|
| `init_project_dir(project_dir)` | Create starter files + project_env.md | 110 |
| `write_project_env(project_dir, name, tech_stack, extra)` | Write project_env.md table format | 125 |
| `read_project_env(project_dir)` | Parse project_env.md → dict | 145 |
| `rename_project(project_dir, new_name)` | Update project name in project_env.md | 160 |

---

## 11. API Routes (NOT PROVIDED — defined in `backend/main.py`)

The following routes are referenced but `main.py` was not provided:

- `GET /api/platform/projects` — list projects
- `GET /api/platform/branch-status` — check branch diff status
- `POST /api/platform/branch-wipe` — sync prod → branch
- `POST /api/platform/branch-deploy` — deploy branch → prod
- `GET /api/platform/heartbeat` — get heartbeat config + queue
- `POST /api/platform/heartbeat` — save heartbeat config
- `GET /api/platform/heartbeat-progress` — poll active execution
- `POST /api/direct/start` — start chat session (returns SSE stream_url)
- `GET /api/direct/todos` — list todos for project
- `POST /api/direct/todo/add` — add todo
- `POST /api/direct/todo/attempt/{id}` — attempt/start todo
- `DELETE /api/direct/todo/{id}` — delete todo

**TODO:** Document `backend/main.py` endpoints when available.