<think>
The user wants me to generate a SITE_MAP.md file based on the provided source code. Let me analyze all the files and create a comprehensive site map.

Let me go through each file:

### backend/app.py
FastAPI application with routes for the platform.

### backend/state.py
State management module.

### backend/pipeline.py
The single chat pipeline — direct_start, direct_stream, and event_generator.

### backend/heartbeat.py
Heartbeat scheduler, executor, and todo/heartbeat API routes.

### backend/platform_routes.py
Branch/prod management routes — branch status, wipe, deploy.

### backend/history.py
Conversation persistence and history endpoint.


Now I'm documenting the remaining backend modules: a TD review and analysis endpoint, auto-documentation regeneration that generates spec files, the tools module with LLM-callable functions and a dual file cache, a direct mode todo list with heartbeat auto-execution, and an LLM client that handles OpenRouter and MiniMax requests.

Continuing through the backend, there's pod management for building and running containers with health checks, a test agent with two-phase automated testing capabilities, and constants spread across both backend and frontend with state management and UI logic. Now I'm reviewing the remaining utility functions like git operations, memory management, and test handling, along with the heartbeat scheduler that manages todo execution through chat endpoints and exposes progress tracking. The platform routes handle branch management operations, and there's a history module that persists conversations with truncation and summarization capabilities.

Moving into the TD analysis and documentation generation side, I'm seeing how the system analyzes conversation patterns to generate specs and context maps, then generating tools with dual cache support for platform projects.

For the todo and heartbeat management, there's task creation with categorization, status tracking, result classification, and queue processing with scheduling logic.

The LLM client handles calls to OpenRouter and MiniMax with retry logic, extracting responses and parsing JSON arguments. Pod management covers port allocation, app type detection, container setup, and health checks with diagnostic tools.

Now I'm looking at the test agent implementation with its two-phase approach for planning and execution.

Continuing through the frontend components, there's the main application interface with sidebar navigation, chat functionality, project management, todo tracking, heartbeat visualization, configuration management, and branch testing features, plus various UI elements like message rendering, modals, and markdown processing.

I'm also noting the key constants that define project roots, ports, storage limits, and agent configuration parameters.
</think>

# Site Map

## backend/
### app.py — FastAPI server with all API route registration
  - app (FastAPI instance) — root ASGI app
  - lifespan() — startup/shutdown event handler
  - add_routes() — registers all route modules to the app

### state.py — Global config, provider, and SSE state management
  - config — global config dict (selected provider, API keys)
  - _get_provider() — returns current provider dict (api_key, base_url, model)
  - _pod_url() — returns pod URL string
  - sse_event() — creates SSE-formatted event dict (event, data)
  - _is_readonly_tool_call() — checks if a tool is read-only
  - _direct_state — per-request pipeline state (project_dir, project_name, port)
  - DIRECT_AGENT_PROMPT — system prompt string for direct agent
  - DIRECT_TOOL_DEFS — tool definitions list sent to LLM
  - TODO_TD_REVIEW_PROMPT — TD review prompt for post-task analysis

### pipeline.py — Single chat pipeline: planning → coding → testing → TD review
  - _trim_messages() — trims stale/redundant content from message history
  - create_or_select_project() [/api/direct/start] — creates or resumes a project, returns stream URL
  - run_chat_pipeline() [/api/direct/stream] — SSE streaming endpoint for full agent loop
  - event_generator() — async generator: planning turn, coding loop, test phase, TD review, done

### heartbeat.py — Todo scheduler, executor via internal HTTP, and heartbeat API routes
  - _execute_todo_via_chat() — executes a todo via internal SSE stream calls
  - _heartbeat_scheduler() — background loop that checks schedules and triggers todos
  - api_get_todos() [/api/direct/todos/{project_dir}] — list all todos
  - api_add_todo() [/api/direct/todos/{project_dir}] — create a new todo
  - api_update_todo() [/api/direct/todos/{project_dir}/{todo_id}] — update todo status/result
  - api_get_todo() [/api/direct/todos/{project_dir}/{todo_id}] — get single todo with schedule info
  - api_delete_todo() [/api/direct/todos/{project_dir}/{todo_id}] — delete a todo
  - api_get_heartbeat() [/api/direct/heartbeat/{project_dir}] — get heartbeat config and progress
  - update_heartbeat_config() [/api/direct/heartbeat/{project_dir}] — enable/disable/configure heartbeat
  - trigger_heartbeat_now() [/api/direct/heartbeat/{project_dir}/run] — run next pending todo immediately
  - get_heartbeat_progress() [/api/platform/heartbeat-progress] — get live execution progress

### platform_routes.py — Branch/prod sync management routes
  - get_branch_status() [/api/platform/branch-status] — compare branch vs prod source files
  - wipe_branch() [/api/platform/branch-wipe] — copy prod → branch and restart branch server
  - deploy_branch() [/api/platform/branch-deploy] — copy branch → prod and restart prod server

### history.py — Conversation persistence, summarization, and history listing
  - _save_conversation() — save a completed conversation to disk as JSON
  - _load_conversation_history() — load recent conversations as formatted text
  - _summarize_old_conversations() — LLM summarization of old conversations
  - erase_history() [DELETE /api/direct/history/{project_dir}] — delete all history for a project
  - list_project_conversations() [GET /api/direct/history/{project_dir}] — list recent conversations

### td.py — Technical Director review and cross-project analysis
  - _parse_td_verdict() — parses STATUS: line from TD review text
  - run_td_analysis() [POST /api/td-analysis] — run full TD analysis across all projects
  - get_latest_td_analysis() [GET /api/td-analysis] — fetch most recent TD report
  - list_td_reports() [GET /api/td-reports] — list all saved TD reports
  - get_td_report() [GET /api/td-reports/{timestamp}] — fetch specific TD report

### docs.py — Auto-documentation regeneration after each chat completion
  - _regenerate_docs() — parallel LLM generation of SPEC.md, CONTEXT_MAP.md, DATA_FLOW.md, SITE_MAP.md
  - _gen_context_map() — generates CONTEXT_MAP.md (file structure, endpoints, tools)
  - _gen_data_flow() — generates DATA_FLOW.md (message flow, tool loop, memory, heartbeat)
  - _gen_spec() — generates SPEC.md (project overview, features, tech stack)
  - _gen_site_map() — generates SITE_MAP.md (compact file tree)

### tools.py — File tools for the LLM + dual-cache for platform editing
  - set_active_project() — set current active project directory
  - get_active_project() — get current active project directory
  - init_project_dir() — create project dir with starter files and project_env.md
  - write_project_env() — write project_env.md metadata file
  - read_project_env() — parse project_env.md metadata
  - rename_project() — update project name in project_env.md
  - file_cache_get() — get cached file content (branch-aware for platform project)
  - file_cache_set() — set cached file content
  - file_cache_set_main() — directly set main cache (used during init/wipe)
  - file_cache_wipe_branch() — sync main cache → branch cache (on branch wipe)
  - file_cache_deploy_to_main() — sync branch cache → main cache (on deploy)
  - file_cache_clear() — clear cache for a project or all
  - execute_tool() — dispatches tool calls to executor functions
  - _tool_list_files() — list files in project directory
  - _tool_read_file() — read file with cache (cache-first, truncate large files)
  - _tool_edit_file() — create or overwrite file
  - _tool_patch_file() — targeted find-and-replace edit (exact match)
  - _tool_read_file_tail() — read last N lines with truncation detection
  - _tool_grep_code() — case-insensitive search across all project files
  - _tool_read_lines() — read a specific line range with ±20-line padding
  - _tool_read_project() — read all source files or return listing if over budget

### direct_todo.py — Todo list per project + heartbeat auto-execution config
  - add_todo() — create a todo item (feature, debug, question, refactor)
  - _classify_result() — classify result as success, partial, or failure
  - update_todo() — update todo status (pending, attempted, done) and record result
  - delete_todo() — delete a todo by ID
  - get_todos() — get all todos for a project
  - get_pending_todos() — get pending/attempted todos (heartbeat queue)
  - get_todo() — get single todo by ID
  - get_heartbeat() — get heartbeat config for a project
  - save_heartbeat() — persist heartbeat config to disk
  - record_heartbeat_run() — log a heartbeat execution to history
  - set_todo_review() — attach TD review and authoritative status to a completed todo

### llm_client.py — Minimal LLM client for OpenRouter and MiniMax
  - call_llm() — single API call with retry logic (429, 502, 503, 504)
  - extract_response() — parse LLM response into type + content + tool_calls

### pod.py — Container lifecycle: build, run, health-check, logs, diagnostics
  - _load_ports() — load port allocations from .ports.json
  - _save_ports() — persist port allocations to .ports.json
  - _is_port_free() — OS-level port availability check
  - _safe_pod_name() — sanitize project name to valid podman pod name
  - get_available_port() — find unused port (checks JSON, podman, and OS)
  - release_port() — free a port allocation
  - detect_app_type() — detect fastapi, flask, static, or python-http
  - generate_containerfile() — generate Containerfile for detected app type
  - build_image() — podman build with Containerfile
  - _force_destroy_pod() — immediate podman pod removal
  - _create_pod() — podman pod create + container run
  - health_check() — poll HTTP endpoint until 200 or max retries
  - spin_up_pod() — full lifecycle: destroy old → build → create → health check
  - _kill_pod_on_port() — find and destroy pod using a specific port
  - _get_logs() — read container stdout/stderr
  - destroy_pod() — stop and remove pod (legacy by session ID)
  - get_pod_status() — get pod status by session ID
  - get_pod_status_by_name() — get pod status by pod name
  - list_pods() — list all aelimini pods
  - get_pod_logs() — get container logs by session ID
  - get_pod_logs_by_name() — get container logs by pod name
  - http_get() — HTTP GET with status and body
  - set_agent_state() — set state for Diagnostics agent tool executors
  - get_agent_port() — get current agent port
  - execute_pod_tool() — dispatch pod tool calls to executor functions
  - _pt_list_files() — list files in generated project
  - _pt_read_file() — read file in generated project
  - _pt_edit_file() — write file in generated project

### test_agent.py — Two-phase automated testing: plan then run, with fix loop
  - load_source_batch() — load all source files as concatenated string for LLM
  - _discover_project_files() — find all source files in a project directory
  - plan_tests() — Phase 1: LLM generates structured JSON test plan
  - _run_setup_steps() — execute API setup/precondition steps before each test
  - run_tests() — Phase 2: execute all test cases (api, browser, unit)
  - _run_api_test() — execute API test case with status/field assertions
  - _run_browser_test() — execute Playwright browser test case
  - _run_unit_test() — execute Python unit test via direct import
  - format_failures_as_message() — format test failures as message for chat pipeline
  - send_to_chat_pipeline() — send message through SSE stream internally
  - test_and_fix_loop() — full loop: plan → run → if fail send to chat → re-run
  - handle_test_agent() — tool entry point called from chat agent

### constants.py — Single source of truth for all shared constants
  - All paths, ports, timeouts, budgets, truncation limits, platform file lists

### main.py — (referenced in PLATFORM_SOURCE_FILES) — app router entry point

## frontend/
### index.html — Full standalone agent UI with chat, todos, heartbeat, config, branch testing
  - init() — app initialization, loads projects and checks branch status
  - loadProjects() — fetch and render sidebar project list
  - loadChat() — load messages for selected project
  - loadTodos() — fetch and render todo list for active project
  - loadHeartbeat() — fetch and render heartbeat config and history
  - addMsg() — append message bubble to chat
  - sendMessage() — POST to /api/direct/start and open EventSource stream
  - onEvent() — handle all SSE event types (phase, thinking, tool_call, tool_result, response, test_phase, test_feedback, td_review, done, error)
  - showTodoDetail() — render todo detail modal overlay
  - saveTodo() — POST to create a new todo
  - deleteTodo() — DELETE a todo
  - runTodo() — trigger heartbeat run for a specific todo
  - toggleHeartbeat() — enable/disable heartbeat via POST
  - runHeartbeatNow() — POST to trigger immediate heartbeat execution
  - switchView() — toggle between chat and config views
  - showConfig() — render config provider form
  - saveConfig() — POST updated provider config
  - selectProject() — switch active project in sidebar
  - newProject() — create new project directory
  - loadCtxMap() — fetch CONTEXT_MAP.md and render in modal
  - openPod() — open generated app URL in new tab
  - renderMarkdownSimple() — basic markdown to HTML renderer
  - renderTodoDetailModal() — build todo detail modal HTML
  - checkBranchStatus() — fetch branch status and update branch bar
  - wipeBranch() — POST to /api/platform/branch-wipe
  - deployBranch() — POST to /api/platform/branch-deploy
  - pollHeartbeatProgress() — poll heartbeat progress and update branch bar live

## Root docs/
  - SPEC.md — project specification (auto-generated)
  - CONTEXT_MAP.md — file structure, endpoints, tools, data formats (auto-generated)
  - DATA_FLOW.md — message flow, tool loop, memory, heartbeat, deploy traces (auto-generated)
  - SITE_MAP.md — this file — compact file tree (auto-generated)