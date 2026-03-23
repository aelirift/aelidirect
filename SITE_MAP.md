<think>
The user wants me to create a SITE_MAP.md file based on the provided source code. Let me analyze each file and extract the functions/classes with brief descriptions.

Let me go through each file:

### backend/tools.py
- `_cache_key()` — cache key generation
- `_is_platform_project()` — check if project is platform self-editing
- `file_cache_get()` — get cached file content
- `file_cache_set()` — set cached file content
- `file_cache_set_main()` — directly set main cache
- `file_cache_wipe_branch()` — copy main → branch cache
- `file_cache_deploy_to_main()` — copy branch → main cache
- `file_cache_clear()` — clear caches for project/all
- `_is_safe_path()` — check if path is within project
- `set_active_project()` — set active project directory
- `get_active_project()` — get active project directory
- `init_project_dir()` — initialize new project directory
- `write_project_env()` — write project_env.md metadata
- `read_project_env()` — read project_env.md metadata
- `rename_project()` — update project name in project_env.md
- `execute_tool()` — execute a tool by name
- `_tool_list_files()` — list files in project
- `_tool_read_file()` — read file from project
- `_tool_edit_file()` — create/overwrite file
- `_tool_patch_file()` — targeted edit to existing file
- `_tool_read_file_tail()` — read last N lines
- `_tool_grep_code()` — search all project files
- `_tool_read_lines()` — read specific line range
- `_tool_read_project()` — read all source code files

TOOL_DEFINITIONS (list of tool schemas): list_files, read_file, edit_file, patch_file, read_file_tail, read_lines, grep_code, read_project
 
### backend/direct_todo.py
The todo management functions handle task lifecycle operations: `add_todo()` creates new tasks with optional categorization, `_classify_result()` evaluates execution outcomes as success, partial, or failure. Task status updates and completion tracking are managed through `update_todo()` and `delete_todo()`, while retrieval functions like `get_todos()`, `get_pending_todos()`, and `get_todo()` allow access to task lists and individual items. Heartbeat monitoring is available via `get_heartbeat()` and `save_heartbeat()` to track task execution patterns.

### backend/llm_client.py
The LLM client module defines `call_llm()` as the primary interface for making language model requests, with `extract_response()` handling response parsing. The `LLMError` exception class manages error scenarios during API interactions.

### backend/pod.py
Pod management handles the container lifecycle through `get_available_port()` for resource allocation and `release_port()` for cleanup. Application detection is performed by `detect_app_type()`, while `generate_containerfile()` creates the necessary container configuration. Image building occurs through `build_image()`, with `spin_up_pod()` orchestrating the full deployment sequence. Health monitoring and status tracking are handled by `health_check()` and `get_pod_status()`, respectively.

Additional pod operations include `destroy_pod()` for termination, `list_pods()` for enumeration, and `get_pod_logs()` for retrieving container output. Port management is supported via `_kill_pod_on_port()` and `_is_port_free()` for checking resource availability. State management functions like `set_agent_state()` and `get_agent_port()` coordinate agent interactions with the pod environment.

### backend/test_agent.py
The test agent coordinates platform verification through `load_source_batch()` for data preparation, with `plan_tests()` defining the testing strategy and `run_tests()` executing the verification process.

The implementation includes specialized test runners for different environments: `_run_setup_steps()` handles preparation, `_run_api_test()` validates HTTP interfaces, `_run_browser_test()` exercises web interactions, and `_run_unit_test()` validates Python code directly. The `test_and_fix_loop()` function implements an iterative improvement cycle that applies fixes and re-validates, with `format_failures_as_message()` and `send_to_chat_pipeline()` managing communication about test outcomes. The main entry point is `handle_test_agent()`, which orchestrates the entire testing workflow.

### backend/constants.py

Configuration values are centralized here, covering path definitions for backend, production, and branch environments, port assignments for both production and branch instances, timeout thresholds for LLM calls and subprocess operations, retry parameters including maximum attempts and delay intervals, file size limits for project reading and truncation, and file extension handling. Additional settings manage test fix iterations, conversation history, and memory directories.

### frontend/index.html

The interface provides project management through `loadProjects()`, conversation display via `addMsg()`, and chat submission with `sendMessage()`. Message rendering includes specialized handlers like `renderToolCall()` and `renderPhase()` for different message types. Todo and heartbeat panels support interaction through dedicated functions, with modals for viewing details and markdown rendering for formatted output. Configuration is accessible via `showConfig()` and `hideConfig()`. The branch testing feature includes status checking and deployment functions. Heartbeat progress tracking uses polling mechanisms for real-time updates.
</think>

# Site Map

## backend/
### tools.py — LLM-callable file/editing tools
  - `_cache_key()` — generate cache key tuple
  - `_is_platform_project()` — check if project is platform self-editing
  - `file_cache_get()` — get cached file content
  - `file_cache_set()` — set cached file content
  - `file_cache_set_main()` — directly set main cache
  - `file_cache_wipe_branch()` — copy main → branch cache
  - `file_cache_deploy_to_main()` — copy branch → main cache
  - `file_cache_clear()` — clear caches for project/all
  - `_is_safe_path()` — validate path is within project
  - `set_active_project()` — set active project directory
  - `get_active_project()` — get active project directory
  - `init_project_dir()` — initialize new project directory
  - `write_project_env()` — write project_env.md metadata
  - `read_project_env()` — read project_env.md metadata
  - `rename_project()` — update project name in project_env.md
  - `execute_tool()` — execute a tool by name
  - `_tool_list_files()` — list files in project
  - `_tool_read_file()` — read file from project
  - `_tool_edit_file()` — create/overwrite file
  - `_tool_patch_file()` — targeted edit to existing file
  - `_tool_read_file_tail()` — read last N lines
  - `_tool_grep_code()` — search all project files
  - `_tool_read_lines()` — read specific line range
  - `_tool_read_project()` — read all source code files
  - TOOL_DEFINITIONS — list_files, read_file, edit_file, patch_file, read_file_tail, read_lines, grep_code, read_project

### direct_todo.py — Todo list and heartbeat persistence
  - `add_todo()` — add todo item / category feature
  - `_classify_result()` — classify result success/failure/partial
  - `update_todo()` — update todo status/result
  - `delete_todo()` — delete todo by id
  - `get_todos()` — get all todos
  - `get_pending_todos()` — get pending/attempted todos
  - `get_todo()` — get single todo by id
  - `get_heartbeat()` — get heartbeat config
  - `save_heartbeat()` — save heartbeat config
  - `record_heartbeat_run()` — record heartbeat execution
  - `set_todo_review()` — set TD review for todo

### llm_client.py — OpenRouter/MiniMax LLM client
  - `call_llm()` — make LLM API call with retry
  - `extract_response()` — parse LLM response type/tool_calls
  - `LLMError` — exception class

### pod.py — Podman container management
  - `_load_ports()` — load port allocations
  - `_save_ports()` — save port allocations
  - `_is_port_free()` — check OS-level port availability
  - `_safe_pod_name()` — convert project name to pod name
  - `get_available_port()` — find unused port in range
  - `release_port()` — release port allocation
  - `detect_app_type()` — detect fastapi/flask/static
  - `generate_containerfile()` — generate Containerfile
  - `build_image()` — build podman image
  - `_force_destroy_pod()` — force-destroy pod by name
  - `_create_pod()` — create podman pod and run container
  - `health_check()` — poll pod until HTTP 200
  - `spin_up_pod()` — full lifecycle destroy/build/start/health
  - `_kill_pod_on_port()` — kill pod using specific port
  - `_get_logs()` — get container stdout/stderr
  - `destroy_pod()` — stop/remove pod legacy
  - `get_pod_status()` — get pod status legacy
  - `get_pod_status_by_name()` — get pod status by name
  - `list_pods()` — list all aelimini pods
  - `get_pod_logs()` — get logs legacy
  - `get_pod_logs_by_name()` — get logs by pod name
  - `http_get()` — make HTTP GET request
  - `set_agent_state()` — set agent tool executor state
  - `get_agent_port()` — get agent host port
  - `execute_pod_tool()` — execute diagnostics pod tool
  - `_pt_list_files()` — list project files
  - `_pt_read_file()` — read project file
  - `_pt_edit_file()` — edit project file
  - POD_TOOL_DEFINITIONS — list_project_files, read_project_file, edit_project_file, check_pod_status, get_container_logs

### test_agent.py — Two-phase automated testing
  - `load_source_batch()` — load all source files as batch
  - `_discover_project_files()` — find source files in project
  - `plan_tests()` — phase 1: LLM generates test plan
  - `_run_setup_steps()` — execute setup/precondition steps
  - `run_tests()` — phase 2: execute all test cases
  - `_run_api_test()` — execute API test case
  - `_run_browser_test()` — execute Playwright browser test
  - `_run_unit_test()` — execute Python unit test
  - `format_failures_as_message()` — format failures for chat
  - `send_to_chat_pipeline()` — send failures through chat pipeline
  - `test_and_fix_loop()` — full test-fix-verify loop
  - `handle_test_agent()` — tool entry point from agent

### constants.py — Shared constants
  - BACKEND_DIR, PROD_ROOT, BRANCH_ROOT, PROJECTS_ROOT — paths
  - PROD_PORT, BRANCH_PORT, POD_PORT_RANGE — ports
  - PLATFORM_PROJECT_NAME, PLATFORM_SOURCE_FILES — platform
  - MAX_ACTION_TURNS, MAX_TEST_FIX_ITERATIONS — limits
  - LLM_TIMEOUT, LLM_RETRYABLE_CODES, LLM_MAX_RETRIES — LLM
  - READ_PROJECT_BUDGET, READ_FILE_TRUNCATE — file reading
  - CODE_EXTENSIONS, SKIP_DIRS — file discovery
  - TRUNCATE_* — string truncation limits

## frontend/
### index.html — Standalone agent UI
  - `loadProjects()` — load sidebar project list
  - `addMsg()` — add chat message / phase / tool / error
  - `sendMessage()` — submit chat message
  - `renderToolCall()` — render tool call message
  - `renderPhase()` — render phase indicator
  - `handleStream()` — SSE stream event handler
  - `getSelectedProject()` — get current project
  - `switchProject()` — switch to project
  - `showNewProjectModal()` — show new project dialog
  - `createNewProject()` — create new project
  - `loadTodos()` — load todo list
  - `renderTodoList()` — render todo items
  - `addTodo()` — add todo item
  - `runTodo()` — run todo item
  - `deleteTodo()` — delete todo item
  - `showTodoDetail()` — show todo detail modal
  - `renderTodoDetailModal()` — render todo detail content
  - `loadHeartbeat()` — load heartbeat config
  - `renderHeartbeat()` — render heartbeat controls/history
  - `toggleHeartbeat()` — enable/disable heartbeat
  - `runHeartbeatNow()` — trigger immediate heartbeat
  - `_fmtDuration()` — format seconds as duration
  - `_fmtTs()` — format ISO timestamp
  - `escHtml()` — escape HTML
  - `_extractIssues()` — extract error lines from result
  - `renderMarkdownSimple()` — render markdown as HTML
  - `checkBranchStatus()` — check branch server status
  - `_showBranchIdle()` — show idle branch status
  - `wipeBranch()` — reset branch to prod
  - `deployBranch()` — deploy branch to prod
  - `pollHeartbeatProgress()` — poll heartbeat progress

## Root docs
  - SPEC.md — platform specification