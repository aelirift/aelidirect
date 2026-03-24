# Site Map

## backend/
### app.py — FastAPI app, all top-level API routes
  - create_app() — Assembles routes and lifespan
  - `@router.post /api/config` — Update provider config
  - `@router.get /api/config` — Get current config
  - `@router.get /api/projects` — List all projects
  - `@router.get /api/projects/{project}` — Get project metadata
  - `@router.delete /api/projects/{project}` — Delete project
  - `@router.post /api/pods` — Create a pod from project
  - `@router.delete /api/pods/{session_id}` — Destroy pod
  - `@router.post /api/pods/{session_id}/restart` — Restart pod
  - `@router.get /api/pods` — List all running pods
  - `@router.get /api/pods/{session_id}/logs` — Get pod logs
  - `@router.get /health` — Health check endpoint

### state.py — Global config dict, provider helpers, prompts
  - `config` dict — Global app config
  - `_get_provider()` — Returns active provider credentials
  - `_pod_url()` — Constructs pod URL for a project
  - `sse_event()` — Formats SSE event string
  - `_is_readonly_tool_call()` — Checks if tool makes no changes
  - `_direct_state` dict — Direct mode session state
  - `DIRECT_AGENT_PROMPT` — Agent system prompt string
  - `DIRECT_TOOL_DEFS` — Tool schemas sent to LLM
  - `TODO_TD_REVIEW_PROMPT` — TD review system prompt

### pipeline.py — Direct chat pipeline: start, stream, SSE events
  - `_trim_messages()` — Trims stale content from message history
  - `@router.post /api/direct/start` — create_or_select_project() — Creates or reopens project, returns stream URL
  - `@router.get /api/direct/stream` — run_chat_pipeline() — Main SSE streaming endpoint, full agent loop

### heartbeat.py — Todo executor, scheduler, todo/heartbeat routes
  - `_execute_todo_via_chat()` — Executes a todo by calling chat endpoints internally
  - `_heartbeat_scheduler()` — Background loop, fires todos on interval
  - `@router.get /api/direct/todos/{project_dir}` — api_get_todos() — List all todos
  - `@router.post /api/direct/todos/{project_dir}` — api_add_todo() — Create a todo
  - `@router.put /api/direct/todos/{project_dir}/{todo_id}` — api_update_todo() — Update todo status
  - `@router.get /api/direct/todos/{project_dir}/{todo_id}` — api_get_todo() — Get single todo with schedule info
  - `@router.delete /api/direct/todos/{project_dir}/{todo_id}` — api_delete_todo() — Delete a todo
  - `@router.get /api/direct/heartbeat/{project_dir}` — api_get_heartbeat() — Get heartbeat config + next run estimate
  - `@router.post /api/direct/heartbeat/{project_dir}` — update_heartbeat_config() — Enable/disable/configure heartbeat
  - `@router.post /api/direct/heartbeat/{project_dir}/run` — trigger_heartbeat_now() — Run next pending todo immediately
  - `@router.get /api/platform/heartbeat-progress` — get_heartbeat_progress() — Live progress of running heartbeat task

### platform_routes.py — Branch/prod management: wipe, deploy, status
  - `_IS_BRANCH` — Whether server is running on branch port
  - `@router.get /api/platform/branch-status` — get_branch_status() — Compares branch vs prod source files
  - `@router.post /api/platform/branch-wipe` — wipe_branch() — Copies prod → branch, clears caches, restarts branch
  - `@router.post /api/platform/branch-deploy` — deploy_branch() — Copies branch → prod, restarts prod

### history.py — Conversation persistence, list, erase
  - `_save_conversation()` — Saves conversation to disk as JSON
  - `_load_conversation_history()` — Loads recent conversations as text for system prompt
  - `_summarize_old_conversations()` — LLM summarises old conversations to save tokens
  - `@router.delete /api/direct/history/{project_dir}` — erase_history() — Deletes all conversation history
  - `@router.get /api/direct/history/{project_dir}` — list_project_conversations() — Lists recent conversations

### td.py — Technical Director review, analysis reports
  - `TD_ANALYSIS_PROMPT` — System prompt for multi-conversation TD analysis
  - `_parse_td_verdict()` — Parses STATUS: line from TD review
  - `@router.post /api/td-analysis` — run_td_analysis() — Runs TD analysis across all projects
  - `@router.get /api/td-analysis` — get_latest_td_analysis() — Returns most recent TD report
  - `@router.get /api/td-reports` — list_td_reports() — Lists all saved TD reports
  - `@router.get /api/td-reports/{timestamp}` — get_td_report() — Returns specific TD report by timestamp

### docs.py — Auto-documentation regeneration
  - `_regenerate_docs()` — Regenerates SPEC.md, CONTEXT_MAP.md, DATA_FLOW.md, SITE_MAP.md in parallel

### tools.py — File tools for the LLM agent (read/write/patch/list/grep)
  - `_SAFE_ROOTS` — Allowed symlink root directories
  - `_active_project_dir` dict — Current active project
  - `_file_cache_main` / `_file_cache_branch` — Dual file caches for platform editing
  - `_is_platform_project()` — Checks if project is the platform self-editing project
  - `file_cache_get()` / `file_cache_set()` / `file_cache_set_main()` — Cache access
  - `file_cache_wipe_branch()` — Copies main cache → branch cache
  - `file_cache_deploy_to_main()` — Copies branch cache → main cache
  - `file_cache_clear()` — Clears cache for a project
  - `_is_safe_path()` — Validates path is within project or safe roots
  - `set_active_project()` / `get_active_project()` — Active project management
  - `init_project_dir()` — Initialises new project directory
  - `write_project_env()` / `read_project_env()` / `rename_project()` — project_env.md management
  - `TOOL_DEFINITIONS` — JSON schemas sent to LLM for all file tools
  - `execute_tool()` — Dispatches tool call to implementation
  - `_tool_list_files()` — Lists files in project directory
  - `_tool_read_file()` — Reads file (returns from cache if unchanged)
  - `_tool_edit_file()` — Creates or overwrites a file
  - `_tool_patch_file()` — Targeted edit: finds old_text, replaces with new_text
  - `_tool_read_file_tail()` — Reads last N lines of a file
  - `_tool_grep_code()` — Case-insensitive search across all project files
  - `_tool_read_lines()` — Reads specific line range with padding
  - `_tool_read_project()` — Reads all source files; returns listing if over budget

### direct_todo.py — Todo list and heartbeat config per project
  - `_now()` — Returns UTC timestamp string
  - `_todo_path()` / `_load_todos()` / `_save_todos()` — Todo file I/O helpers
  - `add_todo()` — Adds a new todo item
  - `_classify_result()` — Classifies result text as success/failure/partial
  - `update_todo()` — Updates todo status, timestamps, result
  - `delete_todo()` / `get_todos()` / `get_pending_todos()` / `get_todo()` — Todo retrieval
  - `get_heartbeat()` / `save_heartbeat()` / `record_heartbeat_run()` — Heartbeat config management
  - `set_todo_review()` — Attaches TD review to a completed todo

### llm_client.py — Minimal LLM HTTP client (OpenRouter, MiniMax)
  - `LLMError` — Exception for API failures after retries
  - `call_llm()` — Makes single LLM API call with retry
  - `extract_response()` — Parses LLM response, handles tool_calls

### pod.py — Podman pod lifecycle: build, run, health check
  - `PORT_RANGE` / `PORT_FILE` / `INTERNAL_PORT` — Port configuration
  - `_load_ports()` / `_save_ports()` / `_is_port_free()` — Port file management
  - `_safe_pod_name()` — Converts project name to safe podman name
  - `get_available_port()` — Finds unused port in range
  - `release_port()` — Releases port allocation
  - `detect_app_type()` — Detects FastAPI/Flask/static from project files
  - `generate_containerfile()` — Generates Containerfile for app type
  - `build_image()` — Runs podman build
  - `_force_destroy_pod()` / `_create_pod()` — Pod lifecycle primitives
  - `health_check()` — Polls pod until HTTP 200
  - `spin_up_pod()` — Full lifecycle: destroy old → build → create → health check
  - `_kill_pod_on_port()` / `_get_logs()` — Debug helpers
  - `destroy_pod()` / `get_pod_status()` / `get_pod_status_by_name()` — Legacy status calls
  - `list_pods()` / `get_pod_logs()` / `get_pod_logs_by_name()` — Log/listing helpers
  - `http_get()` — Makes HTTP GET request, returns status + body
  - `_agent_state` dict — Agent tool state
  - `set_agent_state()` / `get_agent_port()` — State accessors
  - `POD_TOOL_DEFINITIONS` — Tool schemas for Diagnostics agent
  - `execute_pod_tool()` — Dispatches pod tool to implementation
  - `_pt_list_files()` / `_pt_read_file()` / `_pt_edit_file()` — Pod tool implementations

### test_agent.py — Two-phase automated testing: plan then run, with fix loop
  - `_now()` — Timestamp helper
  - `load_source_batch()` — Concatenates all platform source files for LLM
  - `_discover_project_files()` — Finds source files in a project directory
  - `PLAN_SYSTEM_PROMPT` — System prompt for test planning LLM
  - `plan_tests()` — Phase 1: LLM generates JSON test plan from source
  - `run_tests()` — Phase 2: Executes each test case
  - `_run_setup_steps()` — Runs precondition setup steps via httpx
  - `_run_api_test()` — Executes API test case via httpx
  - `_run_browser_test()` — Executes Playwright browser test case
  - `_run_unit_test()` — Executes Python unit test via importlib
  - `format_failures_as_message()` — Formats test failures for chat pipeline
  - `send_to_chat_pipeline()` — Sends message through chat SSE stream
  - `test_and_fix_loop()` — Full loop: plan → run → fix → re-run up to N iterations
  - `handle_test_agent()` — Tool interface entry point called from agent
  - CLI `main()` — Runs test agent from command line

### constants.py — Single source of truth for all shared constants
  - Path constants (BACKEND_DIR, PROD_ROOT, BRANCH_ROOT, PROJECTS_ROOT, etc.)
  - Port constants (PROD_PORT, BRANCH_PORT, POD_PORT_RANGE, etc.)
  - Platform file lists (PLATFORM_SOURCE_FILES, PLATFORM_DATA_DIRS, etc.)
  - Agent limits (MAX_ACTION_TURNS, MAX_TEST_FIX_ITERATIONS, etc.)
  - Timeout constants (SUBPROCESS_TIMEOUT, LLM_STREAM_TIMEOUT, etc.)
  - LLM client constants (LLM_TIMEOUT, LLM_MAX_RETRIES, etc.)
  - File reading/truncation limits (READ_FILE_TRUNCATE, TRUNCATE_TOOL_RESULT, etc.)

## frontend/
### index.html — Full standalone UI: chat, sidebar, config, todos, heartbeat, branch testing
  - `escHtml()` — HTML-safe escape utility
  - `showView()` — Switches between chat and config views
  - `setActiveProject()` — Sets active project in sidebar
  - `addMsg()` / `appendMsg()` — Adds rendered message to chat
  - `sendMessage()` — Sends user message, opens SSE stream
  - `startStream()` — Consumes SSE stream events
  - `showSuccess()` / `showError()` — Shows result banners
  - `loadConfig()` / `saveConfig()` / `applyProvider()` — Config CRUD and apply
  - `loadProjects()` — Loads and renders sidebar project list
  - `createProject()` / `selectProject()` / `deleteProject()` — Project management
  - `initChat()` / `clearMessages()` — Chat initialisation
  - `showCtxMap()` — Renders context map in right panel
  - `loadTodos()` / `addTodo()` / `runTodo()` / `deleteTodo()` — Todo list management
  - `loadHeartbeat()` / `updateHeartbeat()` / `runHeartbeatNow()` — Heartbeat UI control
  - `showTodoDetail()` — Renders todo detail modal with timeline and TD review
  - `_extractIssues()` / `renderMarkdownSimple()` — Issue extraction and markdown rendering
  - `checkBranchStatus()` / `_showBranchIdle()` — Checks and displays branch/prod diff status
  - `wipeBranch()` / `deployBranch()` — Triggers branch wipe or prod deploy
  - `pollHeartbeatProgress()` — Polls and displays live heartbeat execution progress

## Root docs/
  - SPEC.md — Project overview, features, tech stack, how to run
  - CONTEXT_MAP.md — File structure, endpoints, tools, data formats
  - DATA_FLOW.md — Trace of message flow, tool loop, memory, deployment
  - SITE_MAP.md — This file — compact file/function tree