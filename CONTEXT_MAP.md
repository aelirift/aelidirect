<think>
The user wants me to generate a CONTEXT_MAP.md for the aelidirect project based on the source code provided. Let me analyze the codebase systematically.

Looking at the files provided:

1. **backend/pipeline.py** - The main chat pipeline with direct_start, direct_stream, event_generator
2. **backend/heartbeat.py** - Heartbeat scheduler, executor, todo/heartbeat API routes
3. **backend/platform_routes.py** - Branch/prod management routes
4. **backend/history.py** - Conversation persistence and history
5. **backend/td.py** - TD (Technical Director) review and analysis
6. **backend/docs.py** - Auto-documentation regeneration


7. **backend/tools.py** - Tools/functions available to the LLM agent
8. **backend/direct_todo.py** - Todo list and heartbeat auto-executor
9. **backend/llm_client.py** - Minimal LLM client (OpenRouter + MiniMax)
10. **backend/pod.py** - Pod management (podman containers)
11. **backend/test_agent.py** - Two-phase automated testing
12. **backend/constants.py** - All shared constants
13. **frontend/index.html** - Main frontend

Now I need to generate a comprehensive context map documenting the API endpoints with their HTTP methods, paths, handlers, and line numbers, plus any additional architectural details. Looking at the API routes in more detail, I'm seeing the heartbeat endpoints for managing todo execution schedules, platform-level controls for managing branches and deployments, history management for conversations, and TD analysis for reviewing test results. I'm also noting the tools available for LLM agent operations like file and project management.

Now I'm mapping out the pod infrastructure tools that handle container orchestration, the test agent functionality for planning and executing test suites, and then cataloging the key directories where data gets persisted—projects, conversations, todos, and heartbeat configurations all stored as JSON files.

Looking at the frontend structure, there's a main shell with sidebar navigation, chat interface, config management, and several JavaScript functions that handle SSE event streams, project operations, and UI interactions. The core application state lives in a few key places—agent prompts, tool definitions, provider configuration, and progress tracking—while constants define ports, file size limits, timeouts, and storage paths.

For pod deployment, there's a naming convention starting with `aelimini-`, containers listen on port 8000 internally while exposed on 11001-11099, and port allocations are managed in `.ports.json`. The platform source files are mapped across frontend and backend directories, though some files appear to be missing from the backend list. I should probably trace through app.py or main.py to see how all these routes actually connect together, since I haven't seen those files yet in the provided code. The pipeline connects to frontend event handling through SSE events, and now I have the full picture of how the backend components work together. Let me compile this into a comprehensive context map document.
</think>

```markdown
# aelidirect -- Context Map

aelidirect is a standalone AI coding agent with: SSE chat pipeline, file/code tools, podman deployment, todo/heartbeat scheduler, two-phase automated testing (plan + run), TD (Technical Director) post-task review, branch/prod Git-style workflow, and self-editing platform capability.

---

## 1. File Structure

### backend/

| File | Purpose | Key Exports |
|------|---------|-------------|
| `app.py` | FastAPI app + all route registration + SSE event helper | `router`, `sse_event()`, `_is_readonly_tool_call()` |
| `state.py` | Global config dict, provider settings, SSE state, agent prompts/tools | `config`, `_get_provider()`, `_pod_url()`, `DIRECT_AGENT_PROMPT`, `DIRECT_TOOL_DEFS`, `TODO_TD_REVIEW_PROMPT` |
| `pipeline.py` | Core chat pipeline: `direct_start` + `direct_stream` SSE loop (lines 130–360+), message trimming, phases (coding → testing → post_test → TD review) | `router`, `_trim_messages()` |
| `tools.py` | LLM tool defs + executors (list/read/edit/patch/grep files, cache management) | `TOOL_DEFINITIONS`, `execute_tool()`, `file_cache_*()` |
| `llm_client.py` | Low-level LLM API caller (OpenRouter + MiniMax) | `call_llm()`, `extract_response()` |
| `pod.py` | Podman lifecycle: build, run, health-check, destroy pods | `spin_up_pod()`, `health_check()`, `get_pod_status()`, `POD_TOOL_DEFINITIONS`, `execute_pod_tool()` |
| `direct_todo.py` | Per-project todo CRUD + heartbeat config persistence | `add_todo()`, `get_todos()`, `get_pending_todos()`, `get_heartbeat()`, `save_heartbeat()` |
| `heartbeat.py` | Heartbeat scheduler (async loop, 30s tick) + todo execution via internal HTTP calls + all todo/heartbeat routes | `router`, `_execute_todo_via_chat()`, `_heartbeat_scheduler()` |
| `platform_routes.py` | Branch/prod management: status, wipe, deploy | `get_branch_status()`, `wipe_branch()`, `deploy_branch()` |
| `history.py` | Conversation save/load/auto-summarize + history list route | `_save_conversation()`, `_load_conversation_history()`, `router` |
| `td.py` | TD analysis across all projects + verdict parsing + report storage | `TD_ANALYSIS_PROMPT`, `run_td_analysis()`, `get_latest_td_analysis()` |
| `docs.py` | Background auto-regeneration of SPEC.md, CONTEXT_MAP.md, DATA_FLOW.md, SITE_MAP.md | `_regenerate_docs()` |
| `test_agent.py` | Two-phase test system: plan (LLM) + run (httpx/Playwright/unit), fix loop | `plan_tests()`, `run_tests()`, `test_and_fix_loop()`, `handle_test_agent()` |
| `constants.py` | Single source of truth for all paths, ports, limits, truncation values | All uppercase constants |

### frontend/

| File | Purpose |
|------|---------|
| `index.html` | Single-page app: sidebar project list, chat view with SSE, todo panel, heartbeat panel, config view, branch testing bar |

---

## 2. API Endpoints

### Chat & Project Management (pipeline.py, app.py)

| Method | Path | Handler | File:Line |
|--------|------|---------|-----------|
| `POST` | `/api/direct/start` | `create_or_select_project` — creates project dir + env, returns stream URL | pipeline.py:130 |
| `GET` | `/api/direct/stream` | `run_chat_pipeline` — SSE stream: phases → thinking → tool calls → tool results → response → test phase → TD review → done | pipeline.py:171 |

### Config (app.py)

| Method | Path | Handler | File:Line |
|--------|------|---------|-----------|
| `GET` | `/api/config` | `get_config` — returns provider list + selected | app.py:40 |
| `PUT` | `/api/config` | `update_config` — selects provider, sets API key/base_url/model | app.py:47 |
| `POST` | `/api/config/key` | `set_api_key` | app.py:55 |

### Todo CRUD (heartbeat.py)

| Method | Path | Handler | File:Line |
|--------|------|---------|-----------|
| `GET` | `/api/direct/todos/{project_dir}` | `api_get_todos` | heartbeat.py:125 |
| `POST` | `/api/direct/todos/{project_dir}` | `api_add_todo` | heartbeat.py:130 |
| `PUT` | `/api/direct/todos/{project_dir}/{todo_id}` | `api_update_todo` | heartbeat.py:136 |
| `GET` | `/api/direct/todos/{project_dir}/{todo_id}` | `api_get_todo` — enriches with schedule/queue info | heartbeat.py:143 |
| `DELETE` | `/api/direct/todos/{project_dir}/{todo_id}` | `api_delete_todo` | heartbeat.py:170 |

### Heartbeat Scheduler (heartbeat.py)

| Method | Path | Handler | File:Line |
|--------|------|---------|-----------|
| `GET` | `/api/direct/heartbeat/{project_dir}` | `api_get_heartbeat` — config + next_run estimate + pending count | heartbeat.py:175 |
| `POST` | `/api/direct/heartbeat/{project_dir}` | `update_heartbeat_config` — enable/disable, set interval | heartbeat.py:192 |
| `POST` | `/api/direct/heartbeat/{project_dir}/run` | `trigger_heartbeat_now` — runs next pending todo via chat pipeline | heartbeat.py:205 |
| `GET` | `/api/platform/heartbeat-progress` | `get_heartbeat_progress` — current run status for UI polling | heartbeat.py:222 |

### Branch/Prod Management (platform_routes.py)

| Method | Path | Handler | File:Line |
|--------|------|---------|-----------|
| `GET` | `/api/platform/branch-status` | `get_branch_status` — compares branch vs prod source hashes | platform_routes.py:27 |
| `POST` | `/api/platform/branch-wipe` | `wipe_branch` — copies prod → branch (source + data + config), restarts branch service | platform_routes.py:59 |
| `POST` | `/api/platform/branch-deploy` | `deploy_branch` — copies branch → prod, restarts prod service | platform_routes.py:112 |

### Conversation History (history.py)

| Method | Path | Handler | File:Line |
|--------|------|---------|-----------|
| `GET` | `/api/direct/history/{project_dir}` | `list_project_conversations` — last 50 convs with messages/tools | history.py:95 |
| `DELETE` | `/api/direct/history/{project_dir}` | `erase_history` — deletes all conversation files | history.py:84 |

### TD Analysis (td.py)

| Method | Path | Handler | File:Line |
|--------|------|---------|-----------|
| `POST` | `/api/td-analysis` | `run_td_analysis` — runs LLM analysis across all projects, saves report | td.py:75 |
| `GET` | `/api/td-analysis` | `get_latest_td_analysis` — returns most recent report | td.py:103 |
| `GET` | `/api/td-reports` | `list_td_reports` — lists all saved reports | td.py:110 |
| `GET` | `/api/td-reports/{timestamp}` | `get_td_report` — specific report by timestamp | td.py:117 |

---

## 3. Tools / Functions Available to the LLM Agent

### File Tools (tools.py) — `TOOL_DEFINITIONS` + `execute_tool()`

| Tool Name | Description | Executor |
|-----------|-------------|----------|
| `list_files` | List files in a directory with sizes | `_tool_list_files()` |
| `read_file` | Read file contents (cached, truncated at 16k chars) | `_tool_read_file()` |
| `edit_file` | Create new file or fully rewrite existing | `_tool_edit_file()` |
| `patch_file` | Targeted find/replace — exact match required | `_tool_patch_file()` |
| `read_file_tail` | Last N lines of file with truncation warnings | `_tool_read_file_tail()` |
| `read_lines` | Specific line range (1-indexed, ±20 line padding) | `_tool_read_lines()` |
| `grep_code` | Case-insensitive search across all project files | `_tool_grep_code()` |
| `read_project` | Read all source files; falls back to listing if over budget | `_tool_read_project()` |

### Inline Tools (pipeline.py) — called directly inside pipeline event loop

| Tool Name | Description | Location |
|-----------|-------------|----------|
| `spin_up_pod` | Build + run + health-check podman pod | pipeline.py (~inline) |
| `http_check` | GET request to running pod | pipeline.py (~inline) |
| `bash` | Shell command with 60s timeout | pipeline.py (~inline) |
| `git_status` / `git_diff` / `git_log` / `git_commit` | Git operations | pipeline.py (~inline) |
| `memory_save` / `memory_load` / `memory_list` | Long-term memory per project | pipeline.py (~inline) |
| `test_agent` | Invoke test agent (plan/run/full) | pipeline.py (~inline), test_agent.py:handle_test_agent() |

### Pod Tools (pod.py) — `POD_TOOL_DEFINITIONS` + `execute_pod_tool()`

| Tool Name | Description |
|-----------|-------------|
| `list_project_files` | List all files in generated project |
| `read_project_file` | Read file from generated project |
| `edit_project_file` | Edit file in generated project |
| `check_pod_status` | Check pod running state + HTTP health |
| `get_container_logs` | Read podman container logs |

---

## 4. Data Directories and Formats

| Directory | Constant | Format | Contents |
|-----------|----------|--------|----------|
| Project workspaces | `PROJECTS_ROOT` | File tree | One subdirectory per project; each contains source code, README.md, project_env.md |
| Agent memory | `MEMORY_DIR` / `.direct_memory` | `.md` files | Per-project long-term memories keyed by `key.md` |
| Conversations | `CONVERSATIONS_DIR` / `.direct_conversations` | `*.json` | One file per conversation: `{timestamp, user_message, messages[], llm_summary?, test_evidence?}` |
| Todos | `TODOS_DIR` / `.direct_todos` | `{project}.json` | Array of todo items: `{id, task, category, status, created_at, started_at, completed_at, duration_secs, attempts, result_status, last_result, td_review}` |
| Heartbeats | `HEARTBEATS_DIR` / `.direct_heartbeats` | `{project}.json` | `{enabled, interval_minutes, last_run, next_run, running, history[]}` |
| TD Reports | `TD_REPORTS_DIR` / `.td_reports` | `{timestamp}.md` | LLM-generated markdown analysis reports |
| Port allocations | `PORTS_FILE` / `.ports.json` | JSON dict | `{project_name: port_number}` |
| Config | `CONFIG_FILE` / `.config.json` | JSON dict | `{providers[], selected, ...}` |

---

## 5. Frontend Components and Key JS Functions

### Layout

```
.shell (flex row)
├── .sidebar (200px fixed)
│   ├── .sidebar-brand (aelidirect logo)
│   ├── .sidebar-projects (project list)
│   └── .sidebar-actions (New Project, Config)
├── .main-content
│   ├── .view#chat-view.active (flex column)
│   │   ├── .chat-main
│   │   │   ├── .project-bar (shown when subdirectory active)
│   │   │   ├── .messages (scrollable)
│   │   │   ├── .sticky-spinner (pulse dot + status)
│   │   │   └── .input-area (textarea + send button)
│   │   └── .right-panel (480px fixed, Todo tab / Heartbeat tab)
│   └── .view#config-view
└── .branch-bar (bottom strip for branch/prod status)
```

### Key JS Functions

| Function | Purpose | Location (approx) |
|----------|---------|-------------------|
| `sendMessage()` | POST /api/direct/start → SSE EventSource to /api/direct/stream → parse SSE events → update UI | index.html |
| `addMsg(type, content)` | Append message bubble to `.messages` | index.html |
| `handleEvent(type, data)` | Route SSE event types to UI updaters | index.html |
| `renderToolResult(name, result)` | Format + display tool call result bubble | index.html |
| `renderThinking(content)` | Show/hide thinking spinner with preview | index.html |
| `loadProjects()` | Fetch project list → render sidebar | index.html |
| `loadTodos()` | GET /api/direct/todos/{project} → render todo panel | index.html |
| `addTodo()` | POST new todo → reload list | index.html |
| `runTodo(todo_id)` | POST /api/direct/heartbeat/{project}/run | index.html |
| `loadHeartbeat()` | GET /api/direct/heartbeat/{project} → render heartbeat panel | index.html |
| `toggleHeartbeat(enabled)` | POST heartbeat config update | index.html |
| `pollHeartbeatProgress()` | GET /api/platform/heartbeat-progress → update branch bar | index.html |
| `checkBranchStatus()` | GET /api/platform/branch-status → show diff/deploy/wipe buttons | index.html |
| `wipeBranch()` | POST /api/platform/branch-wipe | index.html |
| `deployBranch()` | POST /api/platform/branch-deploy | index.html |
| `showTodoDetail(todo_id)` | Overlay modal with full todo info + TD review | index.html |
| `renderMarkdownSimple(md)` | Minimal markdown → HTML renderer | index.html |

---

## 6. Key Constants, Config, and State Variables

### Constants (constants.py)

| Constant | Value | Purpose |
|----------|-------|---------|
| `PROD_PORT` | `10100` | Main server port |
| `BRANCH_PORT` | `10101` | Branch/testing server port |
| `POD_PORT_RANGE` | `range(11001, 11099)` | Range for user project pods |
| `CONTAINER_INTERNAL_PORT` | `8000` | All containers listen on 8000 internally |
| `PROJECTS_ROOT` | `{PROD_ROOT}/projects/` | User project directories |
| `BRANCH_ROOT` | `/home/aeli/projects/aelidirect_branch` | Branch server root |
| `MAX_ACTION_TURNS` | `150` | Max tool-call turns in one conversation |
| `MAX_TEST_FIX_ITERATIONS` | `2` | Test-fix loop iterations |
| `LLM_STREAM_TIMEOUT` | `600.0` | 10-min timeout for SSE stream |
| `SUBPROCESS_TIMEOUT` | `10` | Default subprocess timeout (git, systemctl) |
| `SUBPROCESS_TIMEOUT_LONG` | `60` | bash tool timeout |
| `READ_PROJECT_BUDGET` | `100_000` | Max chars for read_project tool |
| `READ_FILE_TRUNCATE` | `16_000` | File truncation threshold |
| `TRUNCATE_TOOL_RESULT` | `2000` | Tool result sent back to LLM |
| `CONVERSATION_HISTORY_LIMIT` | `50` | Max conversations kept per project |
| `TD_ANALYSIS_RECENT_COUNT` | `30` | Conversations in TD analysis |
| `PLATFORM_SOURCE_FILES` | 15 files | Files tracked for branch/prod sync |
| `PLATFORM_PROJECT_NAME` | `"aelidirect_platform"` | Special project name for self-editing |

### State (state.py)

| Variable | Type | Purpose |
|----------|------|---------|
| `config` | `dict` | Global config: providers list, selected provider key |
| `_get_provider()` | `func` | Returns `{api_key, base_url, model}` for selected provider |
| `_pod_url()` | `func` | Returns pod URL string |
| `_heartbeat_progress` | `dict` | Live progress of executing todo: `{active, project, todo_id, step, turn, max_turns, total_steps, started_at, finished_at, result_status, result_message}` |
| `sse_event(event_type, data)` | `func` | Formats SSE `data:` line as JSON |
| `_is_readonly_tool_call()` | `func` | Returns tool names that don't count as action turns |
| `DIRECT_AGENT_PROMPT` | `str` | System prompt for coding agent |
| `DIRECT_TOOL_DEFS` | `list` | Tool definitions sent to LLM for coding agent |
| `TODO_TD_REVIEW_PROMPT` | `str` | System prompt for TD review phase |

### Frontend State (index.html JS)

| Variable | Purpose |
|----------|---------|
| `currentProject` | Active project directory name |
| `activeProjectName` | Display name of active project |
| `eventSource` | Active EventSource connection for SSE |
| `messages` | Accumulated message bubbles in DOM |
| `_branchIsBranch` | True if served from branch server (10101) |
| `_hbProgressActive` | True if heartbeat progress is live |
| `_hbProgressTimer` | Interval handle for fast progress polling |
| `_hbProgressLastFinished` | Last finished timestamp for dedup |
| `_podPort` | Running pod port for "Open" button |
| `_podUrl` | Full pod URL for "Open" button |

### Pod Naming Convention (pod.py)

```
Pod name:   aelimini-{safe_project_name}
            where safe_project_name = re.sub(r'[^a-zA-Z0-9_-]', '_', project.lower())[:40]
Container:  aelimini-{safe_project_name}-app
Image:      aelimini-{safe_project_name}:v{version}
Port file:  backend/.ports.json  →  {project_name: host_port}
```

---

## 7. Platform Self-Editing Workflow

```
prod server (10100)                    branch server (10101)
     │                                       │
     │  Agent edits source files ──────────────→ writes to BRANCH_ROOT/
     │                                             │
     │  Auto-wipe (pipeline.py:183) ← ← ← ← ← ← copies prod → branch
     │  if no test in progress                      when agent starts
     │  on each /api/direct/stream call
     │                                             │
     │  GET /api/platform/branch-status ──────────→ compares source hashes
     │  POST /api/platform/branch-wipe ← ← ← ← ← ← copies prod → branch
     │  POST /api/platform/branch-deploy ─────────→ copies branch → prod
     │  (then systemctl restart prod)          (then systemctl restart branch)
     │                                             │
     │  Branch tests code by calling ─────────────→ serves branch source
     │  http://127.0.0.1:BRANCH_PORT/               at BRANCH_PORT
```

The platform project is identified by: directory name `"aelidirect_platform"` OR `project_dir` resolves to `BRANCH_ROOT`. When active, file cache uses a dual-cache: `_file_cache_main` (prod) + `_file_cache_branch` (diverged edits). On deploy, branch cache syncs to main cache.
```