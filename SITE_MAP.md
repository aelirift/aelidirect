# Site Map

## backend/

### app.py — FastAPI app, router registration, config/project/docs endpoints
  - get_config() — GET /api/config — return masked provider config
  - save_config_endpoint() — POST /api/config — save provider/key/model/pod_host
  - save_provider() — POST /api/config/provider — add/update provider
  - delete_provider() — DELETE /api/config/provider/{provider_id} — remove provider
  - list_projects() — GET /api/projects — list all projects with file counts
  - get_project_docs() — GET /api/projects/{dir_name}/docs — get SPEC/CONTEXT_MAP/DATA_FLOW
  - get_platform_docs() — GET /api/platform/docs — get platform own docs
  - serve_index() — GET / — serve frontend index.html
  - _startup() — startup event — clear stuck heartbeats, start scheduler

### state.py — Shared mutable config, prompts, tool defs, state helpers
  - config — mutable provider config dict (api_key, model, base_url, selected)
  - _save_config() — persist config to .config.json
  - _get_provider() — return current provider dict
  - _pod_url(port) — build pod HTTP URL from pod_host + port
  - sse_event(event_type, data) — format SSE event string
  - _is_readonly_tool_call(tc) — check if tool/bash is read-only
  - _heartbeat_progress — shared heartbeat progress dict
  - DIRECT_AGENT_PROMPT — system prompt string for direct mode agent
  - DIRECT_TOOL_DEFS — filtered tool defs + custom tools (deploy_pod, restart_platform, http_check, bash, git_*, memory_*, test_agent)
  - TODO_TD_REVIEW_PROMPT — TD review scoring rubric
  - _direct_state — per-conversation project_dir/name/port
  - _estimate_tokens(text) — rough token estimate

### pipeline.py — Chat pipeline — direct_start, direct_stream, event_generator
  - direct_start(request) — POST /api/direct/start — init project, return stream_url
  - direct_stream(message, project_dir) — GET /api/direct/stream — SSE stream, agent loop, test phase, TD review

### heartbeat.py — Todo CRUD, heartbeat scheduler, progress tracking
  - _execute_todo_via_chat(project_dir, todo_item) — internal executor via HTTP
  - _heartbeat_scheduler() — background loop, polls HEARTBEAT_DIR every 30s
  - api_get_todos(project_dir) — GET /api/direct/todos/{project_dir}
  - api_add_todo(project_dir, request) — POST /api/direct/todos/{project_dir}
  - api_update_todo(project_dir, todo_id, request) — PUT /api/direct/todos/{project_dir}/{todo_id}
  - api_get_todo(project_dir, todo_id) — GET /api/direct/todos/{project_dir}/{todo_id}
  - api_delete_todo(project_dir, todo_id) — DELETE /api/direct/todos/{project_dir}/{todo_id}
  - api_get_heartbeat(project_dir) — GET /api/direct/heartbeat/{project_dir}
  - api_set_heartbeat(project_dir, request) — POST /api/direct/heartbeat/{project_dir}
  - api_run_heartbeat_now(project_dir) — POST /api/direct/heartbeat/{project_dir}/run — trigger now
  - get_heartbeat_progress() — GET /api/platform/heartbeat-progress

### platform_routes.py — Branch/prod sync, deploy to prod
  - get_branch_status() — GET /api/platform/branch-status — compare branch vs prod hashes
  - wipe_branch() — POST /api/platform/branch-wipe — copy prod → branch, restart branch
  - deploy_branch() — POST /api/platform/branch-deploy — copy branch → prod, restart prod

### history.py — Conversation persistence, history retrieval
  - _save_conversation(project_name, user_message, messages, test_evidence) — write conv to disk
  - _load_conversation_history(project_name, prov, selected) — load recent convs for LLM context
  - _summarize_old_conversations(conversations, prov, selected) — LLM summarization batch
  - get_direct_history(project_dir) — GET /api/direct/history/{project_dir}

### td.py — Technical Director analysis, reports
  - _parse_td_verdict(review_text) — extract STATUS: line (PASS/PARTIAL/FAIL/INCOMPLETE)
  - run_td_analysis() — POST /api/td-analysis — run TD analysis across all projects
  - get_latest_td_analysis() — GET /api/td-analysis — fetch most recent report
  - list_td_reports() — GET /api/td-reports — list all saved reports
  - get_td_report(timestamp) — GET /api/td-reports/{timestamp}

### docs.py — Auto-regenerate SPEC.md, CONTEXT_MAP.md, DATA_FLOW.md, SITE_MAP.md
  - _regenerate_docs() — parallel regenerate all four docs
  - _gen_context_map() — generate CONTEXT_MAP.md
  - _gen_data_flow() — generate DATA_FLOW.md
  - _gen_spec() — generate SPEC.md
  - _gen_site_map() — generate SITE_MAP.md

### tools.py — File tool executors (read_file, patch_file, edit_file, grep_code, etc.)
  - file_cache_get(project, path) — dual-cache read (main + branch)
  - file_cache_set(project, path, content) — dual-cache write
  - file_cache_set_main(project, path, content) — direct main cache write
  - file_cache_wipe_branch() — copy main → branch (branch wipe)
  - file_cache_deploy_to_main() — copy branch → main (deploy)
  - file_cache_clear(project) — clear cache for project
  - _is_safe_path(target, project) — check path is within project/safe roots
  - set_active_project(project_dir) — set global active project
  - get_active_project() — get global active project
  - init_project_dir(project_dir) — create project dir + starter files
  - write_project_env(project_dir, project_name, tech_stack, extra) — write project_env.md
  - read_project_env(project_dir) — read project_env.md
  - rename_project(project_dir, new_name) — update project name
  - execute_tool(name, arguments, project_dir) — dispatch tool to executor
  - _tool_list_files(project, path) — list files in directory
  - _tool_read_file(project, path) — read file with cache
  - _tool_edit_file(project, path, content) — create/overwrite file
  - _tool_patch_file(project, path, old_text, new_text) — targeted patch
  - _tool_read_file_tail(project, path, lines) — read last N lines
  - _tool_grep_code(project, pattern) — case-insensitive grep
  - _tool_read_lines(project, path, start, end) — read line range with padding
  - _tool_read_project(project) — read all source files or return file listing
  - TOOL_DEFINITIONS — list_files, read_file, edit_file, patch_file, read_file_tail, read_lines, grep_code, read_project

### direct_todo.py — Todo list and heartbeat config per project
  - _now() — current UTC timestamp string
  - _todo_path(project_name) — .direct_todos/{safe}.json path
  - _load_todos(project_name) — load todos from JSON
  - _save_todos(project_name, todos) — write todos to JSON
  - add_todo(project_name, task, category) — create pending todo
  - _classify_result(result) — classify as success/failure/partial
  - update_todo(project_name, todo_id, status, result) — update status + result
  - delete_todo(project_name, todo_id) — remove todo
  - get_todos(project_name) — get all todos
  - get_pending_todos(project_name) — get pending/attempted todos
  - get_heartbeat(project_name) — load heartbeat config
  - save_heartbeat(project_name, hb) — persist heartbeat config
  - record_heartbeat_run(project_name, todo_id, task, result) — append to history
  - set_todo_review(project_name, todo_id, td_review, td_status) — attach TD review
  - get_todo(project_name, todo_id) — get single todo by ID

### llm_client.py — HTTP LLM client (OpenRouter, MiniMax)
  - call_llm(provider, api_key, base_url, model, messages, tools, temperature) — single LLM call with retry
  - extract_response(raw) — parse API response into type + content + tool_calls
  - LLMError — exception with status_code and response_body

### pod.py — Podman pod lifecycle (build, run, health check)
  - _load_ports() — load .ports.json
  - _save_ports(data) — write .ports.json
  - _is_port_free(port) — OS-level port check
  - _safe_pod_name(project_name) — convert to safe podman name
  - get_available_port(project_name) — find free port in range
  - release_port(project_name) — release port allocation
  - detect_app_type(project_dir) — detect fastapi/flask/static/python-http
  - generate_containerfile(project_dir, app_type, port) — generate Containerfile
  - build_image(project_dir, image_name) — podman build
  - _force_destroy_pod(pod_name) — podman pod rm -f
  - _create_pod(pod_name, image_name, host_port) — pod create + run
  - health_check(port, path, retries, delay) — poll HTTP 200
  - spin_up_pod(project_dir, project_name, host_port, version) — full destroy/build/start/health cycle
  - _kill_pod_on_port(port) — find and kill pod using port
  - _get_logs(pod_name, tail) — podman logs
  - destroy_pod(session_id) — legacy destroy by session_id
  - get_pod_status(session_id) — legacy status by session_id
  - get_pod_status_by_name(pod_name) — podman pod inspect
  - list_pods() — list all aelimini-* pods
  - get_pod_logs(session_id, tail) — legacy logs
  - get_pod_logs_by_name(pod_name, tail) — logs by pod name
  - http_get(port, path) — HTTP GET to pod
  - set_agent_state(project_dir, session_id, host_port, project_name) — set agent tool state
  - get_agent_port() — return stored host_port
  - execute_pod_tool(name, arguments) — dispatch pod tool
  - _pt_list_files(project_dir) — list project files
  - _pt_read_file(project_dir, path) — read project file
  - _pt_edit_file(project_dir, path, content) — edit project file
  - POD_TOOL_DEFINITIONS — list_project_files, read_project_file, edit_project_file, check_pod_status, get_container_logs

### test_agent.py — Two-phase automated testing (plan then run with fix loop)
  - _now() — current UTC timestamp
  - load_source_batch(scope) — concat all source files for LLM
  - _discover_project_files(project_name) — find source files in project dir
  - plan_tests(scope, context, source_batch, target_port) — Phase 1: generate JSON test plan
  - _run_setup_steps(setup_steps, base_url) — execute precondition API calls
  - run_tests(plan, target_port) — Phase 2: execute all test cases
  - _run_api_test(tc, base_url) — httpx API test
  - _run_browser_test(tc, base_url) — Playwright browser test
  - _run_unit_test(tc) — direct Python import test
  - format_failures_as_message(results, plan) — format failures as chat message
  - send_to_chat_pipeline(message, project_dir) — feed failures to chat
  - test_and_fix_loop(scope, context, project_dir, max_iterations) — full plan/run/fix/repeat loop
  - handle_test_agent(args) — tool interface for LLM

### constants.py — All shared constants (paths, ports, limits, timeouts)
  - BACKEND_DIR, PROD_ROOT, BRANCH_ROOT, PROJECTS_ROOT — path constants
  - CONFIG_FILE, PORTS_FILE, MEMORY_DIR, CONVERSATIONS_DIR, TODOS_DIR, HEARTBEATS_DIR, TD_REPORTS_DIR — storage dirs
  - PROD_PORT (10100), BRANCH_PORT (10101), POD_PORT_RANGE (11001-11099) — port constants
  - PLATFORM_SOURCE_FILES, PLATFORM_DATA_DIRS, PLATFORM_DATA_FILES — platform file lists
  - MAX_ACTION_TURNS (150), MAX_TEST_FIX_ITERATIONS (3) — agent limits
  - CONTAINER_BASE_IMAGE (python:3.13-slim) — container image
  - LLM_TIMEOUT (180s), LLM_MAX_RETRIES (3), LLM_MAX_TOKENS (16000) — LLM config
  - READ_PROJECT_BUDGET (100k chars), READ_FILE_TRUNCATE (16k chars) — file limits
  - CODE_EXTENSIONS, SKIP_DIRS — file discovery config

## frontend/

### index.html — Single-page app: chat, todos, heartbeat, branch deploy bar
  - init() — app initialization
  - loadConfig() — fetch /api/config
  - loadProjects() — fetch /api/projects, render sidebar
  - selectProject(name, dir) — switch active project, load todos/heartbeat
  - newProject() — create new project
  - sendMessage() — POST /api/direct/start, connect SSE stream
  - handleSSE(event) — route SSE events (turn, tool_call, tool_result, response, phase, done, error, td_review, etc.)
  - addMsg(type, content) — append message to chat
  - showSpinner(label) / hideSpinner() — sticky spinner bar
  - renderThinking(content) — show agent reasoning
  - renderToolCall(name, args) / renderToolResult(name, result) — tool bubbles
  - switchView(name) — toggle chat/config view
  - loadHistory() — fetch /api/direct/history/{project_dir}
  - renderHistory(conversations) — render history modal
  - loadTodos() / renderTodos(todos) — todo list CRUD
  - addTodo() / updateTodo(id, status) / deleteTodo(id) / runTodo(id) — todo actions
  - showTodoDetail(id) / renderTodoDetailModal(modal, t, schedule) — todo detail modal
  - loadHeartbeat() / renderHeartbeat(hb) — heartbeat panel
  - toggleHeartbeat(enabled) / setHeartbeatInterval(minutes) / runHeartbeatNow() — heartbeat controls
  - checkBranchStatus() — GET /api/platform/branch-status
  - wipeBranch() — POST /api/platform/branch-wipe
  - deployBranch() — POST /api/platform/branch-deploy
  - pollHeartbeatProgress() — GET /api/platform/heartbeat-progress, update branch bar
  - showCtxMapModal() / showDataFlowModal() / showSpecModal() / showDocsModal(type) — doc modals
  - renderMarkdownSimple(md) — basic markdown to HTML
  - _fmtTs(ts) / _fmtDuration(secs) / _fmtTimeAgo(ts) — formatting utilities
  - escHtml(s) / $(id) — DOM utilities
  - _extractIssues(result) — pull error lines from result text
  - setInterval polling — checkBranchStatus (30s), pollHeartbeatProgress (5s)

## Root docs

  - SPEC.md — project overview, features, tech stack, how to run
  - CONTEXT_MAP.md — file structure, API endpoints, tools, data formats, state variables
  - DATA_FLOW.md — trace of message flow, tool loop, memory system, heartbeat, deployment, branch/prod sync
  - SITE_MAP.md — this file