<think>
The user wants me to generate a SITE_MAP.md file from the provided source code. Let me analyze all the files and create a compact file tree with descriptions for every function/class.

Let me go through each file:

**backend/app.py** - Main FastAPI app
**backend/state.py** - State management
**backend/pipeline.py** - Main chat pipeline
**backend/heartbeat.py** - Heartbeat scheduler and todo API routes
**backend/platform_routes.py** - Branch/prod management routes
**backend/history.py** - Conversation persistence
**backend/td.py** - TD review and analysis
**backend/docs.py** - Auto-documentation regeneration


**backend/tools.py** - LLM tools (file operations)
**backend/direct_todo.py** - Todo list and heartbeat
**backend/llm_client.py** - LLM API client
**backend/pod.py** - Pod/container management
**backend/test_agent.py** - Two-phase test agent
**backend/constants.py** - All shared constants
**frontend/index.html** - Full SPA frontend

Now I'll create the SITE_MAP.md with all functions and classes from each file.
</think>

# Site Map

## backend/

### app.py — FastAPI main entry point
  - lifespan() — context manager for startup/shutdown
  - root() — GET / health check
  - router — includes all route submodules

### state.py — Global config and provider state
  - config dict — merged config from all sources
  - _get_provider() — returns active LLM provider
  - load_config() — loads .config.json with env var overrides

### pipeline.py — Core chat pipeline with SSE streaming
  - sse_event() — create SSE-formatted event string
  - _trim_messages() — trim stale messages to save context window
  - _save_conversation() — persist conversation to disk
  - _load_conversation_history() — load recent convos for system prompt
  - _summarize_old_conversations() — batch LLM summarization
  - _regenerate_docs() — trigger async doc regeneration
  - event_generator() — async generator yielding SSE events
  - GET /api/direct/stream — main streaming endpoint
    - event phases: planning → coding → test → post_test
  - POST /api/direct/start — init session, allocate port

### heartbeat.py — Scheduled todo executor and todo API routes
  - _execute_todo_via_chat() — run todo through chat pipeline internally
  - _heartbeat_scheduler() — async loop checking schedule every 30s
  - GET /api/direct/todos/{project_dir} — list all todos
  - POST /api/direct/todos/{project_dir} — add todo
  - PUT /api/direct/todos/{project_dir}/{todo_id} — update status
  - GET /api/direct/todos/{project_dir}/{todo_id} — get single todo + schedule
  - DELETE /api/direct/todos/{project_dir}/{todo_id} — delete todo
  - GET /api/direct/heartbeat/{project_dir} — get heartbeat config
  - POST /api/direct/heartbeat/{project_dir} — set interval/enable
  - POST /api/direct/heartbeat/{project_dir}/run — trigger immediate run
  - GET /api/platform/heartbeat-progress — live progress polling

### platform_routes.py — Branch/prod sync and deployment
  - GET /api/platform/branch-status — compare branch vs prod files
  - POST /api/platform/branch-wipe — reset branch from prod
  - POST /api/platform/branch-deploy — push branch to prod

### history.py — Conversation history and summarization
  - _save_conversation() — write conv to .direct_conversations/
  - _load_conversation_history() — load last 5 convos as text
  - _summarize_old_conversations() — LLM summarization batch
  - GET /api/direct/history/{project_dir} — list conversations
  - DELETE /api/direct/history/{project_dir} — erase all history

### td.py — Technical Director review and analysis
  - _parse_td_verdict() — extract STATUS: line from TD review
  - POST /api/td-analysis — run TD analysis across all projects
  - GET /api/td-analysis — get most recent TD report
  - GET /api/td-reports — list all TD reports
  - GET /api/td-reports/{timestamp} — get specific report

### docs.py — Auto-generate SPEC, CONTEXT_MAP, DATA_FLOW, SITE_MAP
  - _gen_context_map() — regenerate CONTEXT_MAP.md
  - _gen_data_flow() — regenerate DATA_FLOW.md
  - _gen_spec() — regenerate SPEC.md
  - _gen_site_map() — regenerate SITE_MAP.md
  - _regenerate_docs() — parallel async doc regeneration

### tools.py — LLM tool definitions and executors
  - TOOL_DEFINITIONS — JSON schemas sent to LLM (list_files, read_file, patch_file, etc.)
  - file_cache_get/set/clear/wipe_branch/deploy_to_main() — dual cache (main + branch)
  - set_active_project() / get_active_project() — active project state
  - init_project_dir() — create project scaffold
  - write_project_env() / read_project_env() — project metadata
  - rename_project() — update project name
  - _is_safe_path() — path safety check
  - execute_tool() — dispatch tool by name
  - _tool_list_files() — list directory
  - _tool_read_file() — read file (cache-aware)
  - _tool_edit_file() — create/overwrite file
  - _tool_patch_file() — targeted edit (find/replace)
  - _tool_read_file_tail() — read last N lines
  - _tool_grep_code() — search all files
  - _tool_read_lines() — read line range with padding
  - _tool_read_project() — batch read all source files

### direct_todo.py — Todo CRUD and heartbeat config
  - add_todo() — create new todo item
  - update_todo() — update status/result
  - delete_todo() — remove todo
  - get_todos() / get_pending_todos() / get_todo() — query todos
  - set_todo_review() — attach TD review to todo
  - _classify_result() — classify as success/failure/partial
  - get_heartbeat() / save_heartbeat() — heartbeat config
  - record_heartbeat_run() — log run to history

### llm_client.py — Minimal LLM HTTP client
  - call_llm() — single LLM API call with retry
  - extract_response() — parse tool_calls or text from response

### pod.py — Container lifecycle management
  - get_available_port() — find free port in range
  - release_port() — free port allocation
  - detect_app_type() — detect fastapi/flask/static/python
  - generate_containerfile() — build Containerfile for app type
  - build_image() — podman build
  - spin_up_pod() — full lifecycle: destroy → build → create → health check
  - health_check() — poll until HTTP 200
  - destroy_pod() / get_pod_status() / list_pods() — pod queries
  - get_pod_logs() — read container stdout/stderr
  - http_get() — HTTP GET helper
  - POD_TOOL_DEFINITIONS — diagnostics agent tools
  - execute_pod_tool() — dispatch pod tool by name

### test_agent.py — Two-phase automated testing
  - load_source_batch() — concat all source for LLM context
  - _discover_project_files() — find code files in project
  - plan_tests() — Phase 1: LLM generates JSON test plan
  - run_tests() — Phase 2: execute test plan
  - _run_setup_steps() — run preconditions before test
  - _run_api_test() — HTTP-based API test
  - _run_browser_test() — Playwright browser automation
  - _run_unit_test() — direct Python import test
  - format_failures_as_message() — format failures for fix loop
  - send_to_chat_pipeline() — feed failures back to chat agent
  - test_and_fix_loop() — full plan → run → fix → re-run loop
  - handle_test_agent() — tool interface entry point

### constants.py — All shared constants
  - BACKEND_DIR / PROD_ROOT / BRANCH_ROOT / PROJECTS_ROOT — path constants
  - PROD_PORT / BRANCH_PORT / POD_PORT_RANGE — port constants
  - PLATFORM_SOURCE_FILES / PLATFORM_DATA_DIRS / PLATFORM_DATA_FILES — platform file lists
  - MAX_ACTION_TURNS / MAX_TEST_FIX_ITERATIONS — loop limits
  - LLM_* / HEALTH_CHECK_* / TRUNCATE_* — timeouts and limits

## frontend/

### index.html — Full SPA: chat, todos, heartbeat, config, branch deploy
  - init() — bootstrap app, load projects, start polling
  - loadProjects() — fetch project list from API
  - switchProject() — switch active project
  - showView() — toggle chat/config view
  - addMsg() — append message bubble to chat
  - addThinking() — stream thinking content
  - handleEvent() — route SSE events to handlers
  - sendMessage() — POST /api/direct/start, open EventSource
  - renderConfig() — build provider config form
  - saveConfig() — POST provider config
  - loadTodos() / renderTodoList() — todo panel
  - addTodo() / deleteTodo() / runTodo() — todo CRUD
  - loadHeartbeat() / renderHeartbeat() / updateHeartbeatUI() — heartbeat panel
  - toggleHeartbeat() / setHeartbeatInterval() — heartbeat controls
  - renderTodoDetailModal() — modal with timeline, schedule, TD review
  - checkBranchStatus() / wipeBranch() / deployBranch() — branch testing bar
  - pollHeartbeatProgress() — live progress during heartbeat run
  - _showBranchIdle() / _fmtDuration() / _fmtTs() — UI helpers
  - renderMarkdownSimple() — basic markdown → HTML

## Root docs/
  - SPEC.md — project overview, features, tech stack, how to run
  - CONTEXT_MAP.md — file/endpoint/function reference
  - DATA_FLOW.md — trace of message/tool/test/deploy flows
  - SITE_MAP.md — compact file tree (this file)