<think>
Let me analyze the source code provided and create a comprehensive CONTEXT_MAP.md document.

Let me go through each file and extract the key information:

1. **File structure and purposes**
2. **API endpoints** (method, path, handler, line number)
3. **Tools/functions available to the LLM agent**
4. **Data directories and their formats**
5. **Frontend components and key JS functions**
6. **Key constants, config, and state variables**

Let me start by mapping out what I know from the source code:

### File Structure
- `backend/app.py` - Main FastAPI app entry point (imported from constants, referenced throughout)


- `backend/state.py` - State management (imported from state, referenced throughout)
- `backend/pipeline.py` - Chat pipeline for direct_start, direct_stream, and event_generator
- `backend/heartbeat.py` - Heartbeat scheduler, executor, and todo/heartbeat API routes
- `backend/platform_routes.py` - Branch/prod management routes
- `backend/history.py` - Conversation persistence and history endpoint
- `backend/td.py` - TD (Technical Director) review and analysis endpoints
- `backend/docs.py` - Auto-documentation regeneration
- `backend/tools.py` - Tools that the LLM can use
- `backend/direct_todo.py` - Todo list and heartbeat auto-executor
- `backend/llm_client.py` - LLM client (OpenRouter and MiniMax)
- `backend/pod.py` - Pod management (build, run, health-check containers)
- `backend/test_agent.py` - Test Agent for two-phase automated testing
- `backend/constants.py` - All shared constants
- `frontend/index.html` - Frontend SPA

### API Endpoints from the source code:

Now I'm mapping out the pipeline routes for direct project creation and streaming, along with todo management endpoints for CRUD operations.

Looking at the platform and heartbeat routes, I see endpoints for managing branch deployments and system health checks, plus core configuration and provider settings.

Now I'm examining the tools module, which defines the file operations the agent can use—listing, reading, editing, patching, and searching through project files.

Looking at the pod tools next, which handle project file management and pod lifecycle operations like checking status, retrieving logs, and managing pod resources.

Now I'm cataloging the test agent tools and their capabilities—planning tests, running them with different phases, executing the full test-and-fix cycle, and running individual test cases.

Moving into the data layer, I'm identifying the storage directories where the system persists configuration, project data, conversation logs, and task lists across the backend infrastructure. Now I'm looking at the frontend structure, which has a sidebar for navigation with brand display and project management, a main chat interface with message display and input controls, plus a right panel for task management and configuration. The JavaScript layer handles project operations, messaging, and configuration updates through various fetch and SSE stream functions.

I'm also tracking the key constants that control system behavior—port assignments for production and branch environments, port ranges for pod deployments, and iteration limits for test retries. Now I'm mapping out the API endpoints across the backend, organized by file—there's the pipeline module handling direct interactions, heartbeat and todo management, platform operations like branch control, and more routes being tracked here.

I'm continuing through the remaining endpoints from the history, technical debt, and platform management modules, then noting the LLM provider configuration system. For the tool definitions, I'm starting to catalog what the agent can actually execute.

Looking at the function definitions now, I see the read and write operations the agent can perform—listing files, reading them with various constraints, editing and patching them, plus some additional tool capabilities I'm still organizing. I need to double-check the exact handler function names for the SSE events in the pipeline code to make sure I'm attributing them correctly. Let me review the event types more carefully to identify which functions actually send SSE events versus which ones just yield data. I'm realizing there's some redundancy here with both a `response` event and a `done` event, but I should just map out what actually appears in the code rather than overthinking the structure. Let me trace through the pipeline to get a complete picture of all the SSE event types being used.
</think>

# aelidirect -- Context Map

aelidirect is a standalone AI coding agent platform that lets users create projects, edit code via an LLM agent with file/terminal tools, run automated tests, and deploy to containers. It features a branch/prod dual-server workflow for safe self-editing.

---

## 1. File Structure

### Root

| File/Dir | Purpose |
|---|---|
| `backend/` | All Python server-side code (FastAPI) |
| `frontend/index.html` | Single-page application (SPA) |
| `SPEC.md` | Auto-generated project specification |
| `CONTEXT_MAP.md` | Auto-generated this file |
| `DATA_FLOW.md` | Auto-generated data flow diagram |
| `SITE_MAP.md` | Auto-generated compact file tree |

### backend/

| File | Purpose | Key Exports |
|---|---|---|
| `app.py` | FastAPI app factory, CORS, router aggregation, lifespan | `create_app()` |
| `constants.py` | All shared constants — paths, ports, limits, truncation values | 30+ `Path`, `int`, `set` constants |
| `state.py` | Global config dict, provider resolution, SSE helper, readonly tool detection | `config`, `_get_provider()`, `sse_event()` |
| `pipeline.py` | Direct chat pipeline — planning turn, coding loop, test phase, TD review, SSE stream | `router` with `/api/direct/start`, `/api/direct/stream` |
| `heartbeat.py` | Todo heartbeat scheduler, `_execute_todo_via_chat()`, todo/heartbeat routes | `_heartbeat_scheduler()`, `_execute_todo_via_chat()` |
| `platform_routes.py` | Branch vs prod comparison, wipe, deploy routes | `/api/platform/branch-*` |
| `tools.py` | LLM tool definitions (schema) + executors for file I/O | `TOOL_DEFINITIONS`, `execute_tool()`, `_file_cache_*()` |
| `direct_todo.py` | Todo CRUD, heartbeat config read/write | `add_todo()`, `update_todo()`, `get_heartbeat()` |
| `llm_client.py` | Low-level LLM HTTP client for OpenRouter/MiniMax | `call_llm()`, `extract_response()`, `LLMError` |
| `pod.py` | Podman container lifecycle — build, run, health-check | `spin_up_pod()`, `health_check()`, `http_get()` |
| `test_agent.py` | Two-phase automated testing — plan (LLM) then run (httpx/Playwright/unit) | `plan_tests()`, `run_tests()`, `test_and_fix_loop()` |
| `history.py` | Conversation persistence, history listing, LLM summarization | `_save_conversation()`, `_load_conversation_history()` |
| `td.py` | TD (Technical Director) review and cross-project analysis | `run_td_analysis()`, `get_latest_td_analysis()` |
| `docs.py` | Auto-regenerate SPEC.md, CONTEXT_MAP.md, DATA_FLOW.md, SITE_MAP.md | `_regenerate_docs()` |

---

## 2. All API Endpoints

### backend/pipeline.py — `router`

| Method | Path | Handler | Line |
|---|---|---|---|
| `POST` | `/api/direct/start` | `create_or_select_project()` | ~line 130 |
| `GET` | `/api/direct/stream` | `run_chat_pipeline()` | ~line 163 |

### backend/heartbeat.py — `router`

| Method | Path | Handler | Line |
|---|---|---|---|
| `GET` | `/api/direct/todos/{project_dir}` | `api_get_todos()` | ~line 95 |
| `POST` | `/api/direct/todos/{project_dir}` | `api_add_todo()` | ~line 100 |
| `PUT` | `/api/direct/todos/{project_dir}/{todo_id}` | `api_update_todo()` | ~line 106 |
| `GET` | `/api/direct/todos/{project_dir}/{todo_id}` | `api_get_todo()` | ~line 113 |
| `DELETE` | `/api/direct/todos/{project_dir}/{todo_id}` | `api_delete_todo()` | ~line 147 |
| `GET` | `/api/direct/heartbeat/{project_dir}` | `api_get_heartbeat()` | ~line 151 |
| `POST` | `/api/direct/heartbeat/{project_dir}` | `update_heartbeat_config()` | ~line 169 |
| `POST` | `/api/direct/heartbeat/{project_dir}/run` | `trigger_heartbeat_now()` | ~line 186 |
| `GET` | `/api/platform/heartbeat-progress` | `get_heartbeat_progress()` | ~line 213 |

### backend/platform_routes.py — `router`

| Method | Path | Handler | Line |
|---|---|---|---|
| `GET` | `/api/platform/branch-status` | `get_branch_status()` | ~line 19 |
| `POST` | `/api/platform/branch-wipe` | `wipe_branch()` | ~line 50 |
| `POST` | `/api/platform/branch-deploy` | `deploy_branch()` | ~line 88 |

### backend/history.py — `router`

| Method | Path | Handler | Line |
|---|---|---|---|
| `DELETE` | `/api/direct/history/{project_dir}` | `erase_history()` | ~line 100 |
| `GET` | `/api/direct/history/{project_dir}` | `list_project_conversations()` | ~line 109 |

### backend/td.py — `router`

| Method | Path | Handler | Line |
|---|---|---|---|
| `POST` | `/api/td-analysis` | `run_td_analysis()` | ~line 64 |
| `GET` | `/api/td-analysis` | `get_latest_td_analysis()` | ~line 104 |
| `GET` | `/api/td-reports` | `list_td_reports()` | ~line 112 |
| `GET` | `/api/td-reports/{timestamp}` | `get_td_report()` | ~line 120 |

### backend/app.py — `router` (assumed from imports)

| Method | Path | Handler | Line |
|---|---|---|---|
| `GET` | `/api/config` | `get_config()` | (in `app.py`) |
| `POST` | `/api/config` | `set_config()` | (in `app.py`) |
| `GET` | `/api/providers` | `list_providers()` | (in `app.py`) |

### SSE Events Emitted by `run_chat_pipeline()` (pipeline.py)

| Event | Payload | Emitted When |
|---|---|---|
| `phase` | `{"phase": "planning\|coding\|testing\|post_test"}` | Phase transitions |
| `turn` | `{"turn": n, "action_turns": n, "max": n}` | Each LLM call turn |
| `thinking` | `{"content": "..."}` | Planning turn text response |
| `tool_call` | `{"name": "...", "args": {...}}` | LLM requests a tool |
| `tool_result` | `{"name": "...", "result": "..."}` | Tool execution result |
| `response` | `{"content": "..."}` | LLM text response |
| `test_phase` | `{"status": "planning\|running\|all_passed\|error", ...}` | Test phase events |
| `test_feedback` | `{"iteration": n, "failed": n}` | After each test run |
| `td_review` | `{"status": "running\|complete\|error", "review": "..."}` | TD review events |
| `done` | `{"turns": n, "action_turns": n, ...}` | Pipeline complete |
| `error` | `{"message": "...", "traceback": "..."}` | Fatal error |

---

## 3. Tools / Functions Available to the LLM Agent

### From backend/tools.py — `TOOL_DEFINITIONS` (sent to LLM as JSON schema)

| Tool Name | Description | Parameters |
|---|---|---|
| `list_files` | List all files in project directory | `path: string` |
| `read_file` | Read file contents (cached, truncated at 16k chars) | `path: string` |
| `edit_file` | Create new file or fully rewrite existing | `path: string`, `content: string` |
| `patch_file` | Targeted edit — find `old_text`, replace with `new_text` | `path`, `old_text`, `new_text` |
| `read_file_tail` | Read last N lines (default 50), detects truncation | `path: string`, `lines?: int` |
| `read_lines` | Read specific line range with ±20 padding | `path: string`, `start: int`, `end: int` |
| `grep_code` | Case-insensitive search across all project files | `pattern: string` |
| `read_project` | Read all source files at once (falls back to listing if over budget) | _(none)_ |

### From backend/tools.py — Direct executors (not sent to LLM)

These are called internally by `execute_tool()`:

| Executor | Purpose |
|---|---|
| `_tool_list_files()` | List directory contents with sizes |
| `_tool_read_file()` | Read with cache check + mtime invalidation |
| `_tool_edit_file()` | Write file + update cache |
| `_tool_patch_file()` | Find/replace with error handling for missing/multiple matches |
| `_tool_read_file_tail()` | Read end of file + truncation warnings |
| `_tool_read_lines()` | Range read with padding |
| `_tool_grep_code()` | Grep with file:line:content output |
| `_tool_read_project()` | Batch read or size listing |

### From backend/pipeline.py — Inline tool handlers

These are executed inline in the SSE event loop, NOT via `execute_tool()`:

| Tool Name | Purpose | Source |
|---|---|---|
| `deploy_project` | Build & run pod, update project_env | pipeline.py inline |
| `http_check` | GET request to pod | pipeline.py inline |
| `bash` | Run shell command | pipeline.py inline |
| `git_status` / `git_diff` / `git_log` / `git_commit` | Git operations | pipeline.py inline |
| `memory_save` / `memory_load` / `memory_list` | Long-term memory per project | pipeline.py inline |
| `test_agent` | Invoke test_agent tool | pipeline.py inline |

### From backend/pod.py — `POD_TOOL_DEFINITIONS`

| Tool Name | Description |
|---|---|
| `list_project_files` | List generated project files with sizes |
| `read_project_file` | Read a file in the generated project |
| `edit_project_file` | Create or overwrite a file in the project |
| `check_pod_status` | Check if pod is running and healthy |
| `get_container_logs` | Read container stdout/stderr |

### From backend/test_agent.py — Tool interface

| Function | Purpose |
|---|---|
| `handle_test_agent(args)` | Entry point called from pipeline. Phases: `plan`, `run`, `full` |
| `plan_tests()` | Phase 1: LLM generates JSON test plan from source + scope |
| `run_tests()` | Phase 2: Execute plan — API (httpx), browser (Playwright), unit (importlib) |
| `test_and_fix_loop()` | Full loop: plan → run → feed failures to chat pipeline → re-test |

---

## 4. Data Directories and Their Formats

### All Storage Directories

| Directory | Constant | Format | Content |
|---|---|---|---|
| Backend root | `BACKEND_DIR` | — | Contains `.config.json`, `.ports.json` |
| Projects | `PROJECTS_ROOT` | — | One subdirectory per project |
| Memory | `MEMORY_DIR` | — | Per-project `.md` files |
| Conversations | `CONVERSATIONS_DIR` | — | Per-project `.json` files |
| Todos | `TODOS_DIR` | — | Per-project `.json` files |
| Heartbeats | `HEARTBEATS_DIR` | — | Per-project `.json` files |
| TD Reports | `TD_REPORTS_DIR` | — | `.md` files with timestamps |
| Branch root | `BRANCH_ROOT` | — | `/home/aeli/projects/aelidirect_branch` |

### File Format Details

**`.config.json`** — Global config (JSON)

```json
{
  "providers": {
    "openrouter": { "api_key": "...", "base_url": "...", "model": "..." },
    "minimax": { ... }
  },
  "selected": "openrouter"
}
```

**`PROJECTS_ROOT/{project}/project_env.md`** — Project metadata (markdown table)

```markdown
| Property | Value |
|----------|-------|
| Project Name | My App |
| Project Dir | my_app |
| Tech Stack | fastapi |
| OS | Linux ... |
| Python | 3.13.x |
```

**`CONVERSATIONS_DIR/{project}/{timestamp}.json`** — Saved conversation

```json
{
  "timestamp": "2025-01-15T10-30-00",
  "user_message": "Build a counter app",
  "messages": [
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "...", "tools": ["read_file(main.py)"]},
    {"role": "tool", "name": "read_file", "result": "..."}
  ],
  "llm_summary": "...",
  "test_evidence": [...]
}
```

**`TODOS_DIR/{project}.json`** — Todo list (JSON array)

```json
[
  {
    "id": "a1b2c3d4",
    "task": "Add user auth",
    "category": "feature",
    "status": "done",
    "created_at": "2025-01-15T10:00:00",
    "started_at": "2025-01-15T10:05:00",
    "completed_at": "2025-01-15T10:12:00",
    "duration_secs": 420,
    "attempts": 1,
    "result_status": "success",
    "last_result": "Auth added...",
    "td_review": "..."
  }
]
```

**`HEARTBEATS_DIR/{project}.json`** — Heartbeat config

```json
{
  "enabled": true,
  "interval_minutes": 30,
  "last_run": "2025-01-15T10:30:00",
  "running": false,
  "history": [
    {"timestamp": "...", "todo_id": "...", "task": "...", "result": "..."}
  ]
}
```

**`MEMORY_DIR/{project}/{key}.md`** — Long-term memory (plain markdown, one file per key)

**`TD_REPORTS_DIR/{timestamp}.md`** — TD analysis report (markdown)

**`.ports.json`** — Port allocations (JSON)

```json
{"my_project": 11002, "another": 11003}
```

---

## 5. Frontend Components and Key JS Functions

### Layout Structure (index.html)

```
.sidebar (200px)
  ├── .sidebar-brand (logo: "aelidirect")
  ├── Project list (.sidebar-projects)
  └── Action buttons (.sidebar-actions)
.main-content
  ├── #chat-view.view.active
  │   ├── .chat-main
  │   │   ├── .project-bar (hidden until project selected)
  │   │   ├── .messages (scrollable)
  │   │   ├── .sticky-spinner
  │   │   └── .input-area
  │   └── .right-panel (480px)
  │       ├── .right-panel-tabs [Chat | Todo | Heartbeat]
  │       ├── .todo-panel
  │       └── .heartbeat-panel
  └── #config-view.view
      └── Provider config forms
```

### Key JavaScript Functions

| Function | Line | Purpose |
|---|---|---|
| `sendMessage()` | — | POST to `/api/direct/start`, then connect EventSource to `/api/direct/stream` |
| `addMsg(type, html)` | — | Append message bubble to `.messages` |
| `renderToolCall()` | — | Display tool call with name + args |
| `renderToolResult()` | — | Display tool result with expandable details |
| `renderThinking()` | — | Show thinking/planning content |
| `renderDone()` | — | Show completion summary |
| `renderTdReview()` | — | Display TD review markdown |
| `loadProjects()` | — | Fetch `/api/config`, populate sidebar project list |
| `selectProject()` | — | Set active project, show project bar, reload todos |
| `createProject()` | — | POST to `/api/direct/start` with name |
| `loadTodos()` | — | Fetch + render todo list |
| `addTodo()` | — | POST new todo |
| `deleteTodo()` | — | DELETE todo |
| `runTodo()` | — | POST to `/api/direct/heartbeat/{project}/run` |
| `renderTodoDetailModal()` | — | Full-page todo detail with timeline, schedule, TD review |
| `loadHeartbeat()` | — | Fetch + render heartbeat config + queue + history |
| `updateHeartbeatConfig()` | — | POST updated heartbeat settings |
| `checkBranchStatus()` | — | Fetch `/api/platform/branch-status` |
| `pollHeartbeatProgress()` | — | Poll `/api/platform/heartbeat-progress` every 5s |
| `wipeBranch()` | — | POST `/api/platform/branch-wipe` |
| `deployBranch()` | — | POST `/api/platform/branch-deploy` |
| `renderMarkdownSimple()` | — | Convert markdown to HTML for display |
| `escHtml()` | — | HTML escape utility |
| `_fmtTs()` / `_fmtDuration()` | — | Date/time formatting |
| `_extractIssues()` | — | Extract error lines from todo results |

### Event Flow: User Sends a Message

1. `sendMessage()` → `POST /api/direct/start` → receive `stream_url`
2. `EventSource` connects to `/api/direct/stream?message=...&project_dir=...`
3. Server streams SSE events: `phase` → `turn` → `tool_call` → `tool_result` → `response` → `td_review` → `done`
4. Frontend renders each event: `addMsg('assistant', html)`, `renderToolCall()`, `renderToolResult()`, etc.
5. `done` event hides spinner, shows summary

---

## 6. Key Constants, Config, and State Variables

### From backend/constants.py

| Constant | Value | Purpose |
|---|---|---|
| `PROD_ROOT` | `BACKEND_DIR.parent` | `/home/aeli/projects/aelidirect` |
| `BRANCH_ROOT` | `/home/aeli/projects/aelidirect_branch` | Branch server's working copy |
| `PROJECTS_ROOT` | `PROD_ROOT / "projects"` | All generated project directories |
| `PROD_PORT` | `10100` | Main/prod server port |
| `BRANCH_PORT` | `10101` | Branch testing server port |
| `POD_PORT_RANGE` | `range(11001, 11099)` | Container host ports |
| `CONTAINER_INTERNAL_PORT` | `8000` | Container internal listen port |
| `PLATFORM_PROJECT_NAME` | `"aelidirect_platform"` | Self-editing project name |
| `MAX_ACTION_TURNS` | `150` | Max tool-call turns per conversation |
| `MAX_TEST_FIX_ITERATIONS` | `2` | Max coder→tester fix loops |
| `LLM_STREAM_TIMEOUT` | `600.0` | 10-minute timeout for SSE streaming |
| `LLM_TIMEOUT` | `180.0` | LLM API call timeout |
| `LLM_MAX_TOKENS` | `16000` | Max tokens per LLM response |
| `READ_FILE_TRUNCATE` | `16000` | Truncate single-file reads |
| `READ_PROJECT_BUDGET` | `100000` | Budget for `read_project` tool |
| `TRUNCATE_TOOL_RESULT` | `2000` | Tool result sent back to LLM |
| `TRUNCATE_STDOUT` | `3000` | bash stdout truncation |
| `SUBPROCESS_TIMEOUT_LONG` | `60` | bash tool timeout |

### From backend/state.py

| Variable | Type | Purpose |
|---|---|---|
| `config` | `dict` | Global config — providers, selected provider, active project |
| `_get_provider()` | `func` | Returns `{api_key, base_url, model}` for selected provider |
| `_pod_url` | `dict` | Active pod URL for current project |
| `_direct_state` | `dict` | Current project context: `project_dir`, `project_name`, `port` |
| `_is_readonly_tool_call()` | `func` | Returns True for tools that don't modify files |
| `sse_event()` | `func` | Format dict as SSE `data:` line |
| `DIRECT_AGENT_PROMPT` | `str` | System prompt for the coding agent |
| `DIRECT_TOOL_DEFS` | `list` | Tool definitions for `call_llm()` |
| `TODO_TD_REVIEW_PROMPT` | `str` | System prompt for TD review |
| `_heartbeat_progress` | `dict` | Live progress of executing heartbeat todo |

### Platform Self-Editing Paths (constants.py)

**`PLATFORM_SOURCE_FILES`** (15 files):
```
frontend/index.html, backend/app.py, backend/state.py, backend/pipeline.py,
backend/heartbeat.py, backend/platform_routes.py, backend/history.py,
backend/td.py, backend/docs.py, backend/tools.py, backend/direct_todo.py,
backend/llm_client.py, backend/pod.py, backend/test_agent.py, backend/constants.py
```

**`PLATFORM_DATA_DIRS`** (6 dirs):
```
backend/.direct_conversations, backend/.direct_heartbeats, backend/.direct_todos,
backend/.direct_memory, backend/.td_reports, projects/
```

**`PLATFORM_DATA_FILES`** (5 files):
```
backend/.config.json, backend/.ports.json, SPEC.md, CONTEXT_MAP.md, DATA_FLOW.md
```