# Site Map

## backend/
### constants.py — Single source of truth for all shared constants
  Ports, paths, timeouts, limits, truncation values. Import from here, never hardcode.

### main.py — FastAPI server, chat pipeline, all API endpoints
  - _save_config() — persist provider config to .config.json
  - _get_provider() — get active LLM provider (api_key, base_url, model)
  - sse_event() — format SSE event string
  - _is_readonly_tool_call() — check if tool call is read-only (doesn't count as action turn)
  - _save_conversation() — save conversation JSON with messages + test evidence
  - _load_conversation_history() — load + summarize recent conversations for system prompt
  - direct_start() — POST /api/direct/start — create/select project, return stream URL
  - direct_stream() — GET /api/direct/stream — THE pipeline entry point
  - event_generator() — SSE generator: agent loop → test phase → TD review → done
  - _execute_todo_via_chat() — heartbeat executor: thin SSE consumer, bookkeeping only
  - _heartbeat_scheduler() — background task, checks heartbeats every 30s, triggers todos
  - _regenerate_docs() — auto-regenerate SPEC, CONTEXT_MAP, DATA_FLOW, SITE_MAP in parallel
  - _parse_td_verdict() — extract STATUS: PASS/FAIL/PARTIAL from TD review text
  - Endpoints: /api/config, /api/projects, /api/platform/branch-status, /api/platform/branch-wipe,
    /api/platform/branch-deploy, /api/direct/todos, /api/direct/heartbeat, /api/direct/history,
    /api/td-analysis, /api/td-reports

### tools.py — Tool definitions (JSON schemas) + executors
  - TOOL_DEFINITIONS — JSON schemas sent to LLM so it knows available tools
  - execute_tool() — dispatch tool call by name to executor function
  - _tool_read_file() — read file (uses cache, truncates at READ_FILE_TRUNCATE)
  - _tool_patch_file() — find-and-replace edit (text matching, not line numbers)
  - _tool_edit_file() — create new file or full rewrite
  - _tool_read_lines() — read specific line range
  - _tool_grep_code() — search project files for pattern
  - _tool_read_project() — read all source files in one batch (if under budget)
  - File cache: file_cache_get/set/clear, branch/main dual cache for platform editing

### llm_client.py — LLM API wrapper
  - call_llm() — single HTTP POST to chat/completions API with retry
  - extract_response() — parse LLM response into {type: text|tool_call, content, tool_calls}

### pod.py — Container lifecycle (Podman)
  - spin_up_pod() — full lifecycle: destroy old → build → create → health check
  - health_check() — poll /health until HTTP 200 or give up
  - generate_containerfile() — detect app type, produce Dockerfile
  - Port management: get_available_port(), release_port(), PORT_RANGE 11001-11098

### direct_todo.py — Todo CRUD + heartbeat config
  - add_todo() / update_todo() / delete_todo() / get_todos() — todo persistence (JSON files)
  - get_pending_todos() — todos not yet completed
  - _classify_result() — classify agent result as success/failure/partial
  - get_heartbeat() / save_heartbeat() / record_heartbeat_run() — heartbeat config + history
  - set_todo_review() — attach TD review verdict to a todo

### test_agent.py — Two-phase automated testing
  - plan_tests() — Phase 1: LLM generates test plan from source + scope + context
  - run_tests() — Phase 2: execute tests (API via httpx, browser via Playwright, unit via import)
  - _run_setup_steps() — create preconditions before each test (add todos, enable heartbeat, etc.)
  - format_failures_as_message() — format test failures as text for feeding back to coder
  - load_source_batch() — load all source files in one shot for LLM context

## frontend/
### index.html — Single-page app (chat UI, todos, heartbeat, config)
  - sendMessage() — send user input to pipeline via POST /api/direct/start → EventSource
  - SSE handlers: turn, thinking, tool_call, tool_result, response, test_phase, test_feedback, td_review, done
  - loadProject() — switch active project, load todos + heartbeat
  - switchTab() — switch between Chat / Todo / Heartbeat tabs
  - loadTodos() — fetch + render todo list with countdown timers
  - loadHeartbeat() — fetch + render heartbeat panel with queue + history
  - showTodoDetail() — modal with todo details, schedule, TD review
  - checkBranchStatus() — compare branch vs prod, show deploy/wipe buttons
  - Config panel: loadConfigPage(), saveProvider(), setActiveProvider()

## Root docs (auto-generated after each conversation)
  - SPEC.md — what the project is, features, tech stack
  - CONTEXT_MAP.md — detailed API reference, file structures, data formats
  - DATA_FLOW.md — data flow diagrams, interaction patterns
  - SITE_MAP.md — this file
