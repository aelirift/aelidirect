<think>
The user wants me to generate a DATA_FLOW.md documentation file that traces the data flow through the aelidirect system. Let me analyze the source code provided and trace through each of the seven requested flows:

1. Main chat flow (user message → SSE stream → agent loop → response)
2. Tool call loop (LLM response → tool execution → result → next LLM call)
3. Memory system (long-term save/load, short-term conversation history)
4. Heartbeat/todo execution flow
5. Deployment flow (pod management)
6. Config and state management
7. Branch/prod sync flow

However, I notice that the user has only provided partial files:
- backend/tools.py - Complete
- backend/direct_todo.py - Complete
- backend/llm_client.py - Complete
- backend/pod.py - Complete
- backend/test_agent.py - Complete
- backend/constants.py - Complete
- frontend/index.html - Complete (but quite large and contains a lot of UI code)

Missing files that would be needed for complete tracing:
- backend/main.py - The FastAPI server (routes, SSE handling)
- backend/state.py - State management
- backend/pipeline.py - The agent loop/pipeline
- backend/heartbeat.py - Heartbeat execution
- backend/platform_routes.py - Platform-specific routes
- backend/history.py - Conversation history


- backend/td.py - TD (test-driven?) 
- backend/docs.py

I can trace the flows using what I have available. The main chat flow starts with the frontend sending messages to `/api/direct/start` via `send_to_chat_pipeline`, which returns a stream URL consumed as an SSE stream. The backend main.py receives this and initiates the agent loop through pipeline.py, which calls llm_client.py with tools, handles tool calls via tools.py, and streams responses back via SSE. For the tool call loop, llm_client.py returns tool_calls in its response, which pipeline.py then executes through tools.py and feeds results back to the LLM for the next iteration.

Memory flows through direct_todo.py for todos and direct_memory for persistent storage, with conversations stored in .direct_conversations. Heartbeat scheduling lives in direct_todo.py and is executed by heartbeat.py, which handles auto-execution and status recording. The deployment flow uses pod.py's spin_up_pod function to manage containers through podman. Config persists in .config.json with _agent_state in pod.py for pod-specific state. Branch and prod synchronization involves platform_routes.py for branch operations, tools.py for the dual file cache (main and branch), and the branch-wipe/deploy functionality from frontend calls to backend endpoints.

Now I need to generate the DATA_FLOW.md file with proper references to what's actually present in the provided code. I'll trace each flow using only the files that were supplied, noting where files like main.py, state.py, pipeline.py, and heartbeat.py would fit into the architecture but aren't available in the provided snippet. The frontend reference to `/api/direct/start`, `/api/platform/branch-status`, `/api/platform/branch-wipe`, `/api/platform/branch-deploy`, and `/api/platform/heartbeat-progress` indicates what backend endpoints exist, even if I can only infer their structure from their names and how they're called. Looking at the files that are available, I can trace specific connections: the LLM client shows how tool calls are extracted and parsed, the tool execution functions in tools.py show the actual implementation of read_file, edit_file, patch_file, and others, pod.py demonstrates the spin_up_pod lifecycle and health checking, and the test agent shows how the full plan-run-fix loop operates. The frontend JavaScript shows the SSE stream consumption pattern. However, without seeing main.py, state.py, pipeline.py, and heartbeat.py directly, I'll need to reconstruct the missing pieces based on what's clearly implied by these available components and how they interact with each other. The test agent shows the full flow clearly. When a test fails, it calls `send_to_chat_pipeline` with the failure message, which posts to `/api/direct/start` and consumes the SSE stream. The chat pipeline then processes the failure, fixes the issues, and returns the result.

I have enough context to trace the complete flows now. I'll write the DATA_FLOW.md documenting all 7 flows, using inline code references to show how data moves through the system based on what's actually in the provided code.
</think>

# aelidirect -- Data Flow

> **Note on scope:** The following traces are based on the provided source files (`tools.py`, `llm_client.py`, `direct_todo.py`, `pod.py`, `test_agent.py`, `constants.py`, `index.html`). Missing files (`main.py`, `pipeline.py`, `state.py`, `heartbeat.py`, `platform_routes.py`, `history.py`) are reconstructed from cross-references and call patterns in the provided code.

---

## 1. Main Chat Flow

**User message → SSE stream → agent loop → response**

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                              MAIN CHAT FLOW                                         │
└─────────────────────────────────────────────────────────────────────────────────────┘

  FRONTEND (index.html)
  │
  │ sendMessage() → POST /api/direct/start
  │   { message: "...", project_dir: "..." }
  │   ───────────────────────────────────────────►  backend/main.py
  │                                                          │
  │                                                          ▼
  │                                                   SSE stream_url
  │                                                   returned to client
  │
  │   EventSource(stream_url)  ──────────────────►  backend/main.py
  │        (client-side SSE consumer)                  │
  │                                                     ▼
  │                                              pipeline.run_agent_loop()
  │                                                   (pipeline.py)
  │                                                        │
  │                                                        ▼
  │                                             llm_client.call_llm()
  │                                                   with tools=[TOOL_DEFINITIONS]
  │                                                        │
  │   ◄────────── SSE events (event: response) ────────────
  │   ◄────────── SSE events (event: done) ───────────────
  │
  │ addMsg('assistant', content)   ──► rendered in .messages div
  │ addMsg('success', ...)        ──► shown on completion
```

**Key data transformations:**

| Step | Source | Function | Output |
|------|--------|----------|--------|
| Start chat | `index.html` | `sendMessage()` (line ~800) | POST body with `{message, project_dir}` |
| Stream URL | `main.py` | `POST /api/direct/start` route | `{stream_url: "/api/direct/stream/..."}` |
| SSE events | `main.py` | SSE generator in stream route | `event: response`, `event: tool_call`, `event: done` |
| Display | `index.html` | `SSE handler` (line ~950) | DOM insertion via `addMsg()` |

**SSE event types** (inferred from `test_agent.py` line 270 and frontend handler):
- `event: response` → `d.content` displayed as assistant message
- `event: tool_call` → tool name + arguments logged (hidden from user)
- `event: done` → marks conversation end, hides spinner
- `event: error` → shown as error message

**Tool result flow (interleaved):**

```
  Agent loop outputs tool_call event
         │
         ▼
  frontend: SSE handler sees event_type == "tool_call"
         │
         ▼
  Call execute_tool() server-side (tool result string)
         │
         ▼
  SSE event: "tool_result" with result string
         │
         ▼
  frontend logs it as .msg.tool bubble
         │
         ▼
  Agent loop sends tool result back to LLM as assistant message
         │
         ▼
  LLM produces next response (more text OR more tool calls)
```

---

## 2. Tool Call Loop

**LLM response → tool execution → result → next LLM call**

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                           TOOL CALL LOOP                                           │
└─────────────────────────────────────────────────────────────────────────────────────┘

  llm_client.py: call_llm()
  ─────────────────────────────────────────────────────────────────────
  │ Input: messages (with prior tool results), tools=[TOOL_DEFINITIONS]
  │ Output: raw LLM API response (dict)
  ▼
  llm_client.py: extract_response()  (line 63)
  ─────────────────────────────────────────────────────────────────────
  │ Parses raw response:
  │   - If message.tool_calls exists → type="tool_call"
  │   - Otherwise → type="text"
  ▼
  ┌─────────────┐     ┌──────────────────────────────────────────────┐
  │ type=text   │     │ type=tool_call                               │
  └─────────────┘     └──────────────────────────────────────────────┘
         │                      │
         ▼                      ▼
  Return to pipeline      For each tool_call in tool_calls:
  as final response         │
                            ▼
                     tools.py: execute_tool(name, arguments, project_dir)
                     ───────────────────────────────────────────────
                     │ Line 172: dispatches by name
                     │ Line 174: list_files       → _tool_list_files()
                     │ Line 176: read_file         → _tool_read_file()
                     │ Line 178: edit_file        → _tool_edit_file()
                     │ Line 180: patch_file       → _tool_patch_file()
                     │ Line 184: read_file_tail   → _tool_read_file_tail()
                     │ Line 186: read_lines       → _tool_read_lines()
                     │ Line 188: grep_code        → _tool_grep_code()
                     │ Line 190: read_project     → _tool_read_project()
                     │ Returns: string result
                     ▼
                     ┌──────────────────────────────────────────────┐
                     │ CACHE CHECK (for read operations)             │
                     │ tools.py: file_cache_get(project, path)      │
                     │   Line 53: checks _file_cache_branch for     │
                     │            platform project, else main_cache │
                     │   Line 56: mtime validation via _file_cache_ │
                     │            mtime dict                        │
                     └──────────────────────────────────────────────┘
                            │
                            ▼
                     tool result string
                            │
                            ▼
                     Append as assistant message to messages[]
                     ───────────────────────────────────────────────
                     │ role: "assistant"
                     │ content: tool call description
                     │ tool_call_id: "..."
                     │ name: tool_name
                     │
                     │ role: "tool"
                     │ tool_call_id: "..."
                     │ content: tool_result_string
                     ▼
                     BACK TO: llm_client.call_llm()  ← loop repeats
                            │
                            ▼
                     (until LLM returns type=text)
```

**Tool schema definitions** (`tools.py` line 217–313):

| Tool | Parameters | Executor | Notes |
|------|------------|----------|-------|
| `list_files` | `path` | `_tool_list_files()` | Dir listing, skip hidden |
| `read_file` | `path` | `_tool_read_file()` | Cache-aware, truncates at 16k chars |
| `edit_file` | `path`, `content` | `_tool_edit_file()` | Full rewrite, updates cache |
| `patch_file` | `path`, `old_text`, `new_text` | `_tool_patch_file()` | Targeted replace, 1-match required |
| `read_file_tail` | `path`, `lines` | `_tool_read_file_tail()` | Last N lines, truncation detection |
| `read_lines` | `path`, `start`, `end` | `_tool_read_lines()` | Range read with ±20 line padding |
| `grep_code` | `pattern` | `_tool_grep_code()` | Case-insensitive search across all files |
| `read_project` | — | `_tool_read_project()` | Full batch read, budget-gated at 100k chars |

**File cache architecture** (`tools.py` lines 25–50):

```
  _file_cache_main    ──► prod source files (platform + all projects)
  _file_cache_branch   ──► branch edits (platform self-editing)
  _file_cache_mtime   ──► disk mtime tracker for invalidation

  Cache key: (str(project.resolve()), rel_path)
  Platform project detection: project.name == PLATFORM_PROJECT_NAME
                              or project.resolve() == BRANCH_ROOT.resolve()
```

---

## 3. Memory System

**Long-term save/load + short-term conversation history**

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                          MEMORY SYSTEM                                              │
└─────────────────────────────────────────────────────────────────────────────────────┘

  constants.py defines storage dirs (line 17–24):
  ───────────────────────────────────────────────
  │ .direct_memory/         → Long-term memory blobs per project
  │ .direct_conversations/  → Per-conversation message history
  │ .direct_todos/         → Todo items (TODOS_DIR)
  │ .direct_heartbeats/    → Heartbeat config + history
  │ .td_reports/           → TD review reports
  ▼

  LONG-TERM MEMORY  (inferred from constants.py + test_agent.py)
  ──────────────────────────────────────────────────────────────────
  │
  │ Memory files: .direct_memory/{project_name}.json
  │ Format (inferred): {summary, last_updated, ...}
  │
  │ Access: tools.py project_env functions
  │   read_project_env(project_dir) → dict from project_env.md
  │   write_project_env(project_dir, ...) → writes project_env.md
  │
  │ Platform memory: BRANCH_ROOT/.direct_memory/
  │                  PROD_ROOT/.direct_memory/
  │                  (separate memory per environment)
  ▼

  SHORT-TERM CONVERSATION HISTORY
  ──────────────────────────────────────────────────────────────────
  │
  │ Storage: .direct_conversations/{project_name}/{conversation_id}.json
  │ (seen in test_agent.py line 18: BASE_URL, backend/.direct_conversations)
  │
  │ In test_agent.py: send_to_chat_pipeline() (line 266)
  │   1. POST /api/direct/start {message, project_dir}
  │   2. Consume SSE stream, collecting all response/done events
  │   3. Return collected response text
  │
  │ Conversation token budget: CONVERSATION_TOKEN_BUDGET = 50,000
  │ Chars-per-token: CHARS_PER_TOKEN = 4
  │ Summarize batch size: SUMMARIZE_BATCH_SIZE = 10
  │
  │ TD analysis context: TRUNCATE_TD_CONTEXT = 400,000 chars cap
  │ TD analysis recent count: TD_ANALYSIS_RECENT_COUNT = 30 conversations
  ▼

  TODO-STORE (direct_todo.py)
  ──────────────────────────────────────────────────────────────────
  │
  │ File: .direct_todos/{project_name}.json
  │ (safe name: project_name with "/" and ".." replaced)
  │
  │ Structure per todo item:
  │   {
  │     id: str (uuid[:8]),
  │     task: str,
  │     category: "feature" | "debug" | "question" | "refactor",
  │     status: "pending" | "attempted" | "done",
  │     created_at: ISO timestamp,
  │     started_at: ISO timestamp | null,
  │     completed_at: ISO timestamp | null,
  │     duration_secs: int | null,
  │     attempts: int,
  │     result_status: "success" | "failure" | "partial" | null,
  │     last_result: str | null,     ← TRUNCATE_TODO_RESULT = 10,000
  │     td_review: str | null,
  │   }
  │
  │ Key functions (direct_todo.py):
  │   add_todo(project_name, task, category)     → creates + persists
  │   update_todo(project_name, todo_id, status, result) → updates + classifies
  │   _classify_result(result) → scans for fail/partial signals
  │   get_todos(project_name) → loads all
  │   get_pending_todos(project_name) → filters status in (pending, attempted)
  ▼
```

**Result classification logic** (`direct_todo.py` lines 44–52):

```python
def _classify_result(result: str) -> str:
    # failure signals: error, failed, traceback, exception, cannot, could not, unable, crash, fatal
    # partial signals: partially, issue, warning, "but ", "however", not fully, incomplete, workaround
    # Has failure + not fixed → "failure"
    # Has partial signal     → "partial"
    # Otherwise              → "success"
```

---

## 4. Heartbeat / Todo Execution Flow

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                     HEARTBEAT / TODO AUTO-EXECUTION                               │
└─────────────────────────────────────────────────────────────────────────────────────┘

  HEARTBEAT CONFIG  (direct_todo.py lines 93–110)
  ──────────────────────────────────────────────────────────────────
  │
  │ File: .direct_heartbeats/{project_name}.json
  │ Structure:
  │   {
  │     enabled: bool,
  │     interval_minutes: int,
  │     last_run: ISO timestamp | null,
  │     next_run: ISO timestamp | null,
  │     running: bool,
  │     history: [{timestamp, todo_id, task, result}, ...]  ← last 50
  │   }
  │
  │ set_heartbeat(project_name, config)  → saves
  │ get_heartbeat(project_name)         → loads
  ▼

  FRONTEND CONTROLS  (index.html lines 600–800)
  ──────────────────────────────────────────────────────────────────
  │
  │ UI: heartbeat toggle + interval input in right-panel (Heartbeat tab)
  │ Call: POST /api/direct/heartbeat/set {enabled, interval_minutes}
  │
  │ record_heartbeat_run(project_name, todo_id, task, result)
  │   → appends to history[], keeps last 50
  │   → updates last_run timestamp
  ▼

  HEARTBEAT EXECUTION LOOP  (heartbeat.py — not provided, inferred)
  ──────────────────────────────────────────────────────────────────
  │
  │ Periodic scheduler (triggered by backend timer or cron)
  │   │
  │   ▼
  │ get_pending_todos(project_name)  ← from direct_todo.py
  │   │
  │   ▼
  │ For each pending todo (in order):
  │   │
  │   ▼
  │ update_todo(project_name, todo_id, "attempted", "")
  │   │
  │   ▼
  │ Call agent pipeline with todo.task as the user message
  │   (same flow as §1 Main Chat Flow, but initiated server-side)
  │   │
  │   ▼
  │ Agent executes work, produces result
  │   │
  │   ▼
  │ update_todo(project_name, todo_id, "done", result)
  │   │
  │   ▼
  │ record_heartbeat_run(project_name, todo_id, task, result)
  │   │
  │   ▼
  │ SSE event: "heartbeat_progress"  → frontend pollHeartbeatProgress()
  │   (seen in index.html line 1040: /api/platform/heartbeat-progress)
  ▼

  FRONTEND HEARTBEAT PROGRESS POLLING  (index.html lines 1020–1100)
  ──────────────────────────────────────────────────────────────────
  │
  │ pollHeartbeatProgress()  ──► GET /api/platform/heartbeat-progress
  │   │
  │   ▼
  │ If active: shows pulsing branch-bar with step info
  │   "step N · write turn/max_turns · elapsed time"
  │   Polls every 1.5s while active
  │   │
  │   ▼
  │ If finished: shows status badge (success/failure/partial)
  │   Refreshes todos + heartbeat data
  │   Switches back to branch status view after 8s
  │   │
  │   ▼
  │ If idle: shows branch status (from /api/platform/branch-status)
  │   Polls every 30s
  ▼
```

**Frontend SSE handler for heartbeat** (`index.html` line 1042):
```javascript
// Merged into checkBranchStatus() + pollHeartbeatProgress()
// pollHeartbeatProgress() polls /api/platform/heartbeat-progress
// checkBranchStatus() polls /api/platform/branch-status
```

---

## 5. Deployment Flow (Pod Management)

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                         POD DEPLOYMENT FLOW                                         │
└─────────────────────────────────────────────────────────────────────────────────────┘

  pod.py: spin_up_pod()  — THE SINGLE DEPLOY FUNCTION  (line 175)
  ──────────────────────────────────────────────────────────────────
  │
  │ Input: project_dir, project_name, host_port, version
  │ Output: {success, pod_name, port, version, message, logs, phase}
  │
  │ PHASE 1: DESTROY  (line 193)
  │   _force_destroy_pod(pod_name)
  │     → podman pod rm -f {pod_name}
  │   │
  │   ▼
  │   Wait for port release (up to 15s)
  │   │
  │   ▼
  │   If port still occupied:
  │     _kill_pod_on_port(host_port)  → finds + destroys aelimini pod on port
  │     Wait another 5s
  │
  │ PHASE 2: BUILD  (line 211)
  │   detect_app_type(project_dir)
  │     → checks for FastAPI/Flask in *.py files
  │     → checks for index.html
  │     → returns: "fastapi" | "flask" | "static" | "python-http"
  │   │
  │   ▼
  │   generate_containerfile(project_dir, app_type, port)
  │     → writes Containerfile to project_dir/
  │     → FastAPI:  uvicorn main:app --host 0.0.0.0 --port 8000
  │     → Flask:    flask --app main run --host 0.0.0.0 --port 8000
  │     → Static:   python3 -m http.server 8000 --directory /app
  │   │
  │   ▼
  │   podman build -t {image_name} -f Containerfile {project_dir}
  │     → timeout: 120s
  │
  │ PHASE 3: START  (line 220)
  │   podman pod create --name {pod_name} -p {host_port}:8000
  │   │
  │   ▼
  │   podman run -d --pod {pod_name} --name {pod_name}-app {image_name}
  │     → timeout: 60s
  │
  │ PHASE 4: HEALTH CHECK  (line 230)
  │   health_check(host_port, "/health", retries=15, delay=2.0)
  │     → HTTP GET http://localhost:{port}/health
  │     → Waits for HTTP 200
  │     → Returns (True, msg) or (False, last_error)
  │
  │ RESULT:
  │   success=True  → pod is running, health confirmed
  │   success=False → {logs: container logs, phase: where it failed}
  │                    phase ∈ {"destroy", "build", "start", "health"}
  ▼

  PORT ALLOCATION  (pod.py lines 32–67)
  ──────────────────────────────────────────────────────────────────
  │
  │ .ports.json tracks {project_name: port}
  │ PORT_RANGE = 11001–11099
  │
  │ get_available_port(project_name):
  │   1. Check .ports.json
  │   2. Check podman pod ls for actual port usage
  │   3. Check OS-level socket availability
  │   4. First free port wins → saved to .ports.json
  │
  │ release_port(project_name) → removes from .ports.json
  ▼

  POD NAMING  (pod.py line 71)
  ──────────────────────────────────────────────────────────────────
  │
  │ _safe_pod_name(project_name):
  │   → lowercase, alphanumeric only, _ replaces special chars
  │   → truncated to 40 chars (SAFE_NAME_MAX_LENGTH)
  │   → prefixed "aelimini-"
  │   → e.g., "aelimini-my_project"
  ▼

  DIAGNOSTICS TOOLS  (pod.py lines 380–450)
  ──────────────────────────────────────────────────────────────────
  │
  │ Tools available to Diagnostics agent:
  │   list_project_files  → _pt_list_files()
  │   read_project_file   → _pt_read_file()
  │   edit_project_file   → _pt_edit_file()
  │   check_pod_status    → get_pod_status_by_name() + http_get()
  │   get_container_logs  → _get_logs()
  │
  │ Agent state set via: set_agent_state(project_dir, session_id, host_port)
  ▼
```

**Pod lifecycle state machine:**

```
  spin_up_pod()
       │
       ├─► [destroy] ──► _force_destroy_pod() ──► podman pod rm -f
       │                          │
       │                          ├─► port free ──► continue
       │                          └─► port busy ──► _kill_pod_on_port()
       │
       ├─► [build] ────► detect_app_type() ──► generate_containerfile()
       │                    └─► podman build -t {image}:v{version}
       │
       ├─► [start] ────► podman pod create -p {port}:8000
       │                    └─► podman run -d --pod {name}
       │
       └─► [health] ───► health_check() ──► HTTP GET /health
                            │
                            ├─► HTTP 200 within 15×2s ──► success=True
                            └─► timeout ──► success=False, logs captured
```

---

## 6. Config and State Management

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                     CONFIG AND STATE MANAGEMENT                                    │
└─────────────────────────────────────────────────────────────────────────────────────┘

  constants.py  (line 14–24)
  ──────────────────────────────────────────────────────────────────
  │
  │ Config file: backend/.config.json
  │ Ports file:   backend/.ports.json
  │
  │ All paths defined here, imported everywhere:
  │   BACKEND_DIR, PROD_ROOT, BRANCH_ROOT, PROJECTS_ROOT
  │   MEMORY_DIR, CONVERSATIONS_DIR, TODOS_DIR, HEARTBEATS_DIR
  │   TD_REPORTS_DIR
  ▼

  RUNTIME CONFIG  (inferred from test_agent.py + platform routes)
  ──────────────────────────────────────────────────────────────────
  │
  │ main.py likely loads .config.json at startup
  │ Contains: selected provider, api_key, base_url, model
  │   (referenced in test_agent.py line 133: from main import config)
  │
  │ Config per request:
  │   project_dir passed through: tools.py execute_tool(project_dir)
  │   _active_project_dir dict in tools.py (line 21)
  │     set_active_project(project_dir) / get_active_project()
  ▼

  AGENT STATE (per-request context)
  ──────────────────────────────────────────────────────────────────
  │
  │ tools.py: _active_project_dir = {"path": None}
  │   → thread/module-level global for fallback project
  │   → MUST pass project_dir explicitly in execute_tool()
  │
  │ pod.py: _agent_state = {project_dir, project_name, session_id, host_port}
  │   → set_agent_state() / get_agent_port()
  │   → Used by Diagnostics agent tools
  │
  │ llm_client.py: no persistent state (stateless per call)
  ▼

  Dual environment roots  (constants.py lines 10–12)
  ──────────────────────────────────────────────────────────────────
  │
  │ PROD_ROOT   = backend/..     (aelidirect/ — production code)
  │ BRANCH_ROOT = /home/aeli/projects/aelidirect_branch
  │
  │ PROJECTS_ROOT = PROD_ROOT / "projects"
  │   → All user projects stored under aelidirect/projects/
  │
  │ Platform self-editing project:
  │   PLATFORM_PROJECT_NAME = "aelidirect_platform"
  │   (special: uses branch_cache instead of main_cache)
  ▼
```

**Config file schema** (inferred from usage):

```json
{
  "selected": "openrouter",          // active provider key
  "providers": {
    "openrouter": {
      "api_key": "sk-...",
      "base_url": "https://openrouter.ai/api/v1",
      "model": "anthropic/claude-..."
    },
    "minimax": {
      "api_key": "...",
      "base_url": "https://api.minimax.chat/v1",
      "model": "..."
    }
  }
}
```

**LLM constants** (`constants.py` lines 60–64):

```python
LLM_TIMEOUT = 180.0          # per-request timeout
LLM_RETRYABLE_CODES = {429, 502, 503, 504}
LLM_MAX_RETRIES = 3
LLM_RETRY_DELAY = 3.0        # exponential backoff: delay × (attempt+1)
LLM_MAX_TOKENS = 16000
```

---

## 7. Branch / Prod Sync Flow

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                     BRANCH / PROD SYNCHRONIZATION                                   │
└─────────────────────────────────────────────────────────────────────────────────────┘

  DUAL FILE CACHE  (tools.py lines 25–50)
  ──────────────────────────────────────────────────────────────────
  │
  │ Two independent caches:
  │
  │   _file_cache_main   ──► PROD source files (source of truth)
  │   _file_cache_branch ──► BRANCH edits (diverges from prod)
  │
  │ Cache key: (str(project.resolve()), rel_path)
  │ Platform project uses branch cache, all others use main cache
  │
  │   _is_platform_project(project):
  │     → project.name == "aelidirect_platform"
  │     → OR project.resolve() == BRANCH_ROOT.resolve()
  │
  │ Cache operations:
  │   file_cache_get()     → reads branch or main based on project
  │   file_cache_set()     → writes branch or main based on project
  │   file_cache_set_main()→ direct write to main cache (init/wipe)
  │   file_cache_wipe_branch() → main → branch (branch reset)
  │   file_cache_deploy_to_main() → branch → main (successful deploy)
  │   file_cache_clear()   → selective or full cache clear
  ▼

  BRANCH WIPE  (reset branch to prod)
  ──────────────────────────────────────────────────────────────────
  │
  │ Frontend: wipeBranch()  (index.html line 895)
  │   → POST /api/platform/branch-wipe
  │   → Confirm dialog before action
  │
  │ Backend (platform_routes.py — not provided, inferred):
  │   │
  │   ▼
  │   1. List all files in BRANCH_ROOT
  │   2. For each file, if exists in PROD_ROOT:
  │        copy PROD_ROOT/file → BRANCH_ROOT/file
  │   3. For each file only in BRANCH_ROOT (non-platform data):
  │        delete BRANCH_ROOT/file
  │   4. Call file_cache_wipe_branch()  ← tools.py line 47
  │        → _file_cache_branch.clear()
  │        → _file_cache_branch.update(_file_cache_main)
  │   5. Sync data dirs from PROD to BRANCH:
  │        .direct_conversations, .direct_todos, .direct_heartbeats
  │   6. Return {ok: bool, wiped: [files], errors: [...]}
  │
  │ Frontend response:
  │   addMsg('system', 'Branch wiped — N items synced from prod.')
  ▼

  BRANCH DEPLOY  (deploy branch to prod)
  ──────────────────────────────────────────────────────────────────
  │
  │ Frontend: deployBranch()  (index.html line 917)
  │   → POST /api/platform/branch-deploy
  │   → Confirm dialog before action
  │
  │ Backend (platform_routes.py — not provided, inferred):
  │   │
  │   ▼
  │   1. Compare file timestamps: BRANCH_ROOT vs PROD_ROOT
  │      → Build list of changed files (branch newer than prod)
  │   2. For each changed file:
  │        copy BRANCH_ROOT/file → PROD_ROOT/file
  │   3. Call file_cache_deploy_to_main()  ← tools.py line 50
  │        → only platform-related entries copied
  │        → for key, content in _file_cache_branch.items():
  │             _file_cache_main[key] = content
  │   4. Sync data dirs from BRANCH to PROD
  │   5. Restart server (reload prod code)
  │   6. Return {ok: bool, deployed: [files], errors: [...]}
  │
  │ Frontend: after 3s delay → location.reload()
  │   (server restarted, client reconnects to new prod instance)
  ▼

  BRANCH STATUS CHECK  (index.html lines 850–893)
  ──────────────────────────────────────────────────────────────────
  │
  │ checkBranchStatus()  → GET /api/platform/branch-status
  │   │
  │   ▼
  │   Response (inferred):
  │   {
  │     is_branch: bool,        ← true if this IS the branch server
  │     has_changes: bool,       ← branch files differ from prod
  │     changes: [
  │       {file: "backend/main.py", branch_newer: bool, prod_newer: bool},
  │       ...
  │     ]
  │   }
  │   │
  │   ▼
  │   If is_branch=true:
  │     → Hide deploy/test buttons (branch server is read-only)
  │     → Show "You are on the branch server" label
  │   │
  │   ▼
  │   If is_branch=false (prod server):
  │     → Show branch status bar
  │     → branch_newer=true files → enable Test + Deploy buttons
  │     → branch_newer=false → show "Ready to test" (green)
  │
  │ Polling: every 30s via setInterval(checkBranchStatus, 30000)
  ▼
```

**Branch/prod file sync logic** (inferred from frontend + cache system):

```
  BRANCH WIPE (branch ← prod):
  ┌──────────────────────────────────────────────────────────────┐
  │ tools.py: file_cache_wipe_branch()                           │
  │   _file_cache_branch = {}                                   │
  │   _file_cache_branch.update(_file_cache_main)  ← copies all │
  │                                                             │
  │ On disk:                                                    │
  │   for each PROD_ROOT/file:                                  │
  │     copy → BRANCH_ROOT/file                                  │
  │   for each BRANCH_ROOT-only file (non-data):                │
  │     delete from BRANCH_ROOT                                  │
  └──────────────────────────────────────────────────────────────┘

  BRANCH DEPLOY (prod ← branch):
  ┌──────────────────────────────────────────────────────────────┐
  │ tools.py: file_cache_deploy_to_main()                        │
  │   for key, content in _file_cache_branch.items():           │
  │     _file_cache_main[key] = content                          │
  │                                                             │
  │ On disk:                                                    │
  │   for each file where branch_mtime > prod_mtime:            │
  │     copy BRANCH_ROOT/file → PROD_ROOT/file                   │
  │   sync .direct_* dirs from BRANCH → PROD                    │
  │   restart server on PROD                                    │
  └──────────────────────────────────────────────────────────────┘
```

---

## Test-and-Fix Loop (Cross-cutting)

The **Test Agent** (`test_agent.py`) combines multiple flows:

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                        TEST-AND-FIX LOOP                                          │
│                        test_agent.py: test_and_fix_loop()                          │
└─────────────────────────────────────────────────────────────────────────────────────┘

  ┌───────────────────────────────────────────────────────────────────────────────┐
  │ STEP 1: PLAN (test_agent.py: plan_tests(), line 110)                          │
  │                                                                                │
  │   load_source_batch(scope)  → concatenates source files                        │
  │     → PLATFORM_FILES = [frontend/index.html, backend/*.py, SPEC.md]          │
  │     → ~37k chars total, well within context                                    │
  │                                                                                │
  │   call_llm(provider, model, messages, tools=None)                              │
  │     → PLAN_SYSTEM_PROMPT as system message                                     │
  │     → Source batch + scope + context as user message                           │
  │     → Returns: raw LLM response                                                │
  │                                                                                │
  │   extract_response(raw)                                                        │
  │     → parsed.content: JSON string with test plan                                │
  │     → JSON parsed → {"summary", "test_cases": [...]}                            │
  │                                                                                │
  │   Returns: plan dict                                                           │
  └───────────────────────────────────────────────────────────────────────────────┘
           │
           ▼
  ┌───────────────────────────────────────────────────────────────────────────────┐
  │ STEP 2: RUN (test_agent.py: run_tests(), line 190)                            │
  │                                                                                │
  │   For each test case in plan["test_cases"]:                                   │
  │                                                                                │
  │   a) Setup: _run_setup_steps(setup_steps, base_url)                           │
  │        → httpx.AsyncClient                                                     │
  │        → API calls to create preconditions (e.g., create todo, enable HB)    │
  │        → Fail here → test status="error", continue to next                    │
  │                                                                                │
  │   b) Execute by type:                                                         │
  │                                                                                │
  │      type=api   → _run_api_test(tc, base_url)                                 │
  │        → httpx async calls (GET/POST/PUT/DELETE)                              │
  │        → assertions: status_code, expected_fields, __exists__, __gt_zero__   │
  │                                                                                │
  │      type=browser → _run_browser_test(tc, base_url)                           │
  │        → Playwright async (chromium)                                          │
  │        → setup API calls first, then browser steps                           │
  │        → assertions: text, visible, count, evaluate, screenshot              │
  │                                                                                │
  │      type=unit  → _run_unit_test(tc)                                          │
  │        → importlib.import_module(module_name)                                  │
  │        → getattr(mod, func_name)(*args, **kwargs)                             │
  │        → assertions: exact match, __truthy__, __type__, __contains__         │
  │                                                                                │
  │   c) Collect results: [{id, name, type, status, details, ...}]                │
  └───────────────────────────────────────────────────────────────────────────────┘
           │
           ▼
  ┌───────────────────────────────────────────────────────────────────────────────┐
  │ STEP 3: FIX LOOP (test_agent.py: test_and_fix_loop(), line 315)               │
  │                                                                                │
  │   if all pass: return {final_status: "all_passed"}                            │
  │                                                                                │
  │   Format failures:                                                            │
  │     format_failures_as_message(results, plan)                                 │
  │       → extracts assertion_failed from each failed detail                    │
  │       → returns markdown error report                                        │
  │                                                                                │
  │   Send to chat pipeline:                                                      │
  │     send_to_chat_pipeline(fix_msg, project_dir)                              │
  │       → POST /api/direct/start {message, project_dir}  (line 266)            │
  │       → SSE stream consuming loop                                             │
  │       → Returns: agent's fix response text                                    │
  │                                                                                │
  │   Reload source: load_source_batch("platform")                                │
  │     → Files may have been edited by the fix agent                            │
  │                                                                                │
  │   Repeat: max MAX_TEST_FIX_ITERATIONS = 3 times                               │
  └───────────────────────────────────────────────────────────────────────────────┘
           │
           ▼
  ┌───────────────────────────────────────────────────────────────────────────────┐
  │ RESULT SUMMARY                                                                 │
  │                                                                                │
  │ Returns: {                                                                    │
  │   plan: {...},                                                                │
  │   iterations: [                                                               │
  │     {iteration: 1, results: [...], passed: N, failed: M,                    │
  │      fix_message: "...", fix_response: "..."},                                │
  │     {iteration: 2, ...},                                                       │
  │     ...                                                                       │
  │   ],                                                                          │
  │   final_status: "all_passed" | "max_iterations_reached",                    │
  │   summary: "..."                                                             │
  │ }                                                                             │
  └───────────────────────────────────────────────────────────────────────────────┘
```

---

## Summary: Cross-File Data References

| From → To | Data Passed | Location |
|-----------|-------------|----------|
| `index.html` → `main.py` | `POST {message, project_dir}` | `sendMessage()` |
| `main.py` → `index.html` | SSE stream URL | `/api/direct/start` response |
| `main.py` → `pipeline.py` | stream writer | agent loop entry |
| `pipeline.py` → `llm_client.py` | `messages[]`, `tools=TOOL_DEFINITIONS` | `call_llm()` |
| `llm_client.py` → `pipeline.py` | `{"type": "text"\|"tool_call", ...}` | `extract_response()` |
| `pipeline.py` → `tools.py` | `name`, `arguments`, `project_dir` | `execute_tool()` |
| `tools.py` → `tools.py` | cache read/write | `_file_cache_*` dicts |
| `tools.py` → disk | file I/O | `_tool_*_file()` functions |
| `direct_todo.py` → disk | todo JSON | `_save_todos()` |
| `pod.py` → OS | podman commands | `subprocess.run()` |
| `pod.py` → `pod.py` | state | `_agent_state` dict |
| `test_agent.py` → `main.py` | `POST /api/direct/start` | `send_to_chat_pipeline()` |
| `test_agent.py` → `llm_client.py` | messages | `call_llm()` |
| `test_agent.py` → `httpx` | HTTP requests | `_run_api_test()` |
| `test_agent.py` → `playwright` | browser actions | `_run_browser_test()` |
| `index.html` → `pod.py` (via backend) | pod commands | `/api/platform/*` endpoints |
| `constants.py` → all | paths, ports, limits | imported at module top |