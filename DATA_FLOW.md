<think>
The user wants me to generate a DATA_FLOW.md file that traces the data flow through the aelidirect platform. I need to analyze all the source code provided and create a comprehensive data flow document covering:

1. Main chat flow (user message → SSE stream → agent loop → response)
2. Tool call loop (LLM response → tool execution → result → next LLM call)
3. Memory system (long-term save/load, short-term conversation history)
4. Heartbeat/todo execution flow
5. Deployment flow (pod management)
6. Config and state management
7. Branch/prod sync flow

Let me trace through the code carefully.


Now I'm looking at the main pipeline entry points and how they connect. The chat flow starts at `direct_start()` which initializes the project and returns a stream URL, then `direct_stream()` takes over and manages the entire SSE communication lifecycle. For the tool system, I need to trace how the LLM's tool calls get executed and their results fed back into the conversation context. The memory layer has two components: `_save_conversation()` handles persisting the full message history, while `_load_conversation_history()` retrieves and manages that stored data.

The heartbeat mechanism runs on a scheduler that triggers todo execution, which internally calls back into the chat pipeline through `_execute_todo_via_chat()`. For deployments, there's a `spin_up_pod()` function that orchestrates the container lifecycle. State management flows through `config` as the primary source of truth and `_direct_state` for request-level state, while branch/production sync is handled by routes like `wipe_branch()` and `deploy_branch()`.

The conversation history system batches messages during saves, loads the last 5 conversations into the system prompt, and periodically summarizes older ones to keep context manageable. Now I'm putting together a comprehensive data flow document that ties all these pieces together.blocks to 1-line summaries
    │     → Trims stale file reads (read before patch to same file)
    │     → Trims confirmatory bash output (exit code 0)
    │     → Trims old_text from patch_file args (replaced with "(trimmed N chars)")
    │     → Never trims last 6 messages
    │
    yield sse_event("turn", {"turn": total_turns, "action_turns": action_turns, "max": max_turns})
    │
    └─► call_llm(selected, api_key, base_url, model,
                 _trimmed_messages,          ← trimmed for context efficiency
                 DIRECT_TOOL_DEFS,           ← list_files, read_file, patch_file, etc.
                 temperature=0.3)

          ├─► HTTP POST with body["tools"] = DIRECT_TOOL_DEFS
          │     → LLM can respond with text OR tool_calls
          │
          └─► extract_response(raw)
                ├─► type: "text" → yield response, done
                └─► type: "tool_call" → execute tools, loop back
```

#### Phase 3 — TEST (if test_agent tool called, or automated after coding)
**File:** `backend/pipeline.py` — test phase block (line ~590)

```
If test_agent tool is called OR _made_code_changes:
  │
  ├─► yield sse_event("phase", {"phase": "testing"})

  ├─► test_and_fix_loop(scope, context, project_dir)
      [test_agent.py: test_and_fix_loop()]

      Iteration 1:
      ├─► plan_tests(scope, context, source_batch)    [Phase 1 of test_agent]
      │     └─► call_llm() with PLAN_SYSTEM_PROMPT
      │           → Returns JSON test plan with test_cases[]
      │
      ├─► run_tests(plan)                           [Phase 2 of test_agent]
      │     ├─► For each test case:
      │     │     ├─► _run_setup_steps() → HTTP API calls via httpx
      │     │     ├─► If type=="api" → _run_api_test() → httpx calls
      │     │     ├─► If type=="browser" → _run_browser_test() → Playwright
      │     │     └─► If type=="unit" → _run_unit_test() → importlib
      │     │
      │     └─► Returns [{ id, name, status, details, ... }]

      ├─► If any failures AND iteration < MAX_TEST_FIX_ITERATIONS:
      │     ├─► format_failures_as_message(results, plan)
      │     │     → Formats as Markdown error report
      │     │
      │     └─► send_to_chat_pipeline(fix_msg, project_dir)
      │           → HTTP POST to /api/direct/start
      │           → SSE stream consumed internally
      │           → Agent fixes code → files patched on disk
      │           → Loop back to run_tests() with updated source

      └─► Up to MAX_TEST_FIX_ITERATIONS (2) fix attempts

yield sse_event("phase", {"phase": "post_test"})
```

#### Phase 4 — POST-TEST / TD REVIEW
**File:** `backend/pipeline.py` — TD review block (line ~660)

```
If _used_any_tools:
  │
  ├─► Build _review_input:
  │     ├─► Original task (msg)
  │     ├─► Agent plan (_plan_text)
  │     ├─► Agent final response (_final_response)
  │     ├─► Test fix iterations count
  │     └─► Test evidence (all test results across iterations)
  │
  └─► call_llm(selected, api_key, base_url, model,
               [{"role": "system", "content": TODO_TD_REVIEW_PROMPT},
                {"role": "user", "content": _review_input}],
               tools=None, temperature=0.3)
      → extract_response() → _td_review_text

yield sse_event("td_review", { status: "complete", review: _td_review_text })
```

### Conversation Persistence (on completion)
**File:** `backend/pipeline.py` — `event_generator()` finally block (line ~700)

```
yield sse_event("done", { turns, action_turns, test_evidence, td_review })
  │
  ├─► _save_conversation(project_dir, msg, messages, test_evidence)
  │     [history.py: _save_conversation()]
  │     → Writes to CONVERSATIONS_DIR / {project_dir} / {timestamp}.json
  │     → Includes full messages array (minus system), test_evidence
  │
  ├─► _regenerate_docs()                          [docs.py: _regenerate_docs()]
  │     → Background task: calls LLM to regenerate SPEC.md, SITE_MAP.md, etc.
  │     → Uses asyncio.get_event_loop().create_task()
  │
  └─► If branch editing + code changes + no tests ran:
        └─► systemctl --user restart aelidirect-branch.service
```

### SSE Events Emitted
**File:** `backend/pipeline.py` — `sse_event()` helper (line ~1)

| Event Type | Payload | When |
|---|---|---|
| `phase` | `{phase}` | Phase transitions |
| `turn` | `{turn, action_turns, max}` | Each LLM call |
| `thinking` | `{content}` | Planning output |
| `response` | `{content}` | Final text responses |
| `tool_call` | `{name, args}` | Tool invocation |
| `tool_result` | `{name, result}` | Tool output |
| `test_phase` | `{status, ...}` | Test execution status |
| `test_feedback` | `{failed, iteration}` | Test failures |
| `pod_url` | `{url}` | Deployment result |
| `td_review` | `{status, review?}` | TD review status |
| `done` | `{turns, action_turns, ...}` | Completion |
| `error` | `{message, traceback}` | Fatal errors |

---

## 2. Tool Call Loop

### Tool Definitions
**File:** `backend/tools.py` — `TOOL_DEFINITIONS` array (line ~110)

Sent to LLM as JSON schemas. Tools available:
- `list_files` — list directory contents
- `read_file` — read single file (with caching)
- `edit_file` — create / full-rewrite file
- `patch_file` — targeted edit (old_text → new_text)
- `read_file_tail` — last N lines of file
- `read_lines` — specific line range with ±20 padding
- `grep_code` — case-insensitive search across all files
- `read_project` — read all files if under READ_PROJECT_BUDGET (100k chars)

### Tool Execution Flow
**File:** `backend/pipeline.py` — inside `while action_turns < max_turns` loop (line ~430)

```
LLM response: extract_response(raw)
  │
  ├─► If type == "text":
  │     yield sse_event("response", {content})
  │     → Loop ends, proceed to test phase
  │
  └─► If type == "tool_call":
        For each tool_call in tool_calls:
        │
        ├─► Parse tool_call:
        │     ├─► tc["id"]              — tool call ID
        │     ├─► tc["function_name"]    — tool name
        │     └─► tc["arguments"]        — {path, old_text, new_text, ...}
        │
        ├─► all_readonly = all(tool.name in READONLY_TOOLS for tool in tool_calls)
        │     → If ALL tools are readonly (read_file, grep_code, etc.)
        │       → action_turns does NOT increment
        │
        ├─► yield sse_event("tool_call", {name, args})
        │     → Frontend shows tool call in real-time
        │
        ├─► Route by tool name:
        │     ├─► File tools (execute_tool)
        │     │     [tools.py: execute_tool()]
        │     │     ├─► list_files → _tool_list_files()
        │     │     ├─► read_file → _tool_read_file()  ← cache check
        │     │     ├─► edit_file → _tool_edit_file()  ← cache set
        │     │     ├─► patch_file → _tool_patch_file() ← cache set
        │     │     ├─► read_file_tail → _tool_read_file_tail()
        │     │     ├─► read_lines → _tool_read_lines()
        │     │     ├─► grep_code → _tool_grep_code()
        │     │     └─► read_project → _tool_read_project()
        │     │
        │     ├─► deploy → spin_up_pod() [pod.py: spin_up_pod()]
        │     ├─► restart_platform → systemctl restart
        │     ├─► http_check → http_get()
        │     ├─► bash → subprocess.run()
        │     ├─► git_status/diff/log/commit → subprocess.run(["git", ...])
        │     ├─► memory_save → write to MEMORY_DIR / {project} / {key}.md
        │     ├─► memory_load → read from MEMORY_DIR
        │     ├─► memory_list → glob MEMORY_DIR
        │     └─► test_agent → handle_test_agent() [test_agent.py]
        │
        ├─► yield sse_event("tool_result", {name, result: truncated})
        │     → TRUNCATE_TOOL_RESULT = 2000 chars max sent to LLM
        │
        ├─► messages.append({"role": "tool", "tool_call_id": tc["id"], "content": result})
        │     → Appended to conversation for next LLM call
        │
        └─► _made_code_changes = True if name in ("edit_file", "patch_file")

        If not all_readonly:
          action_turns += 1
        → Loop back to call_llm() with updated messages
```

### File Caching (Dual Cache for Platform Editing)
**File:** `backend/tools.py` — `_file_cache_main`, `_file_cache_branch` (line ~35)

```
_tool_read_file():
  ├─► file_cache_get(project, path)           ← Check cache first
  │     ├─► If _is_platform_project: → _file_cache_branch
  │     └─► Else: → _file_cache_main
  │
  ├─► Check disk mtime vs _file_cache_mtime[key]
  │     └─► If cache miss OR mtime changed → read from disk
  │
  └─► file_cache_set(project, path, content)  ← Populate cache

_tool_patch_file() / _tool_edit_file():
  └─► file_cache_set(project, path, new_content)
        → Updates branch cache for platform project
```

---

## 3. Memory System

### Long-Term Memory (Persistent Files)
**File:** `backend/direct_todo.py` — memory tools, `MEMORY_DIR` from `constants.py`

```
memory_save(key, content):
  └─► Write to: MEMORY_DIR / {project_name} / {key}.md
        └─► Creates directory if needed

memory_load(key):
  └─► Read from: MEMORY_DIR / {project_name} / {key}.md
        └─► Returns content or "Memory '{key}' not found"

memory_list():
  └─► Glob: MEMORY_DIR / {project_name} / *.md
        └─► Returns list of saved memory keys
```

**Loaded into system prompt** at `direct_stream()` line ~350:
```
for f in sorted(mem_dir.glob("*.md")):
    memories.append(f"[{f.stem}]: {f.read_text()[:500]}")
system_prompt += "\n\n[LONG-TERM MEMORY]\n" + "\n".join(memories)
```
→ Each memory truncated to 500 chars

### Short-Term Memory (Conversation History)
**File:** `backend/history.py`

```
_save_conversation(project_name, user_message, messages, test_evidence):
  ├─► conv_dir = CONVERSATIONS_DIR / {project_name}
  ├─► ts = datetime.utcnow().strftime("%Y-%m-%dT%H-%M-%S")
  ├─► Serialize messages (strip system, keep user/assistant/tool)
  ├─► Write: {conv_dir} / {ts}.json
  │     └─► Includes: timestamp, user_message, messages, llm_summary, test_evidence
  └─► Enforced limit: CONVERSATION_HISTORY_LIMIT = 50 files per project
        → Oldest files deleted when limit exceeded

_load_conversation_history(project_name, prov, selected):
  ├─► conv_dir = CONVERSATIONS_DIR / {project_name}
  ├─► Load last 5 conversation files
  ├─► For each: if llm_summary exists → use it; else → format as text
  ├─► Concatenate all with "\n\n" separators
  └─► Return (truncated to 40k chars if needed)
      → Fed into system prompt as [RECENT CONVERSATION HISTORY]
```

### Conversation Summarization (Background Cleanup)
**File:** `backend/history.py` — `_summarize_old_conversations()` (line ~80)

```
Triggered: When loading history and > SUMMARIZE_BATCH_SIZE (10) unsummarized convs
  ├─► Load oldest 10 unsummarized conversations
  ├─► call_llm() with summarization prompt
  │     → Prompt: "For EACH conversation, list EVERY bug found, fix applied, feature added"
  ├─► Parse response → extract summaries per conversation
  ├─► Write back llm_summary field to each .json file
  └─► Subsequent loads use llm_summary instead of full text
        → ~30-40k tokens saved per conversation
```

---

## 4. Heartbeat / Todo Execution Flow

### Todo Storage
**File:** `backend/direct_todo.py`

```
Todo file: TODOS_DIR / {project_name}.json

Todo structure:
  { id, task, category, status, created_at, started_at, completed_at,
    duration_secs, attempts, result_status, last_result, td_review }

Statuses: "pending" | "attempted" | "done"

add_todo(project, task, category)       → Append to list, return item
update_todo(project, id, status, result)
  ├─► status="attempted" → set started_at, increment attempts
  ├─► status="done" → set completed_at, compute duration_secs
  └─► _classify_result(result) → "success" | "failure" | "partial"
delete_todo(project, id)
get_todos(project)                     → Load from JSON
get_pending_todos(project)            → Filter by pending/attempted
get_todo(project, id)
set_todo_review(project, id, td_review, td_status)
```

### Heartbeat Storage
**File:** `backend/direct_todo.py` — HEARTBEAT_DIR

```
Heartbeat file: HEARTBEATS_DIR / {project_name}.json

Heartbeat structure:
  { enabled, interval_minutes, last_run, next_run, running, history[] }

history entry: { timestamp, todo_id, task, result }
  → Kept to last 50 runs

get_heartbeat(project)    → Load or return default {enabled: False, ...}
save_heartbeat(project, hb) → Write to JSON
record_heartbeat_run(project, todo_id, task, result)
  → Append to history[], update last_run
```

### Heartbeat Scheduler
**File:** `backend/heartbeat.py` — `_heartbeat_scheduler()` (line ~80)

```
_asyncio.create_task(_heartbeat_scheduler())   [app.py startup]
  │
  └─► while True (every 30 seconds):
        ├─► Iterate HEARTBEATS_DIR.glob("*.json")
        │     ├─► Skip if not enabled or already running
        │     ├─► Check interval: (now - last_run) >= interval_minutes?
        │     ├─► Check project directory exists
        │     ├─► Check pending todos exist
        │     └─► Check API key configured
        │
        └─► If all conditions met:
              hb["running"] = True
              save_heartbeat(project, hb)
              await _execute_todo_via_chat(project, pending[0])
              hb = get_heartbeat(project)
              hb["running"] = False
              hb["last_run"] = now
              save_heartbeat(project, hb)
```

### Todo Execution via Chat Pipeline
**File:** `backend/heartbeat.py` — `_execute_todo_via_chat()` (line ~20)

```
_execute_todo_via_chat(project_dir, todo_item):
  │
  ├─► _heartbeat_progress.update({active: True, project, todo_id, task, ...})
  │
  ├─► update_direct_todo(project, todo_id, "attempted")
  │
  ├─► httpx.AsyncClient → POST /api/direct/start
  │     body: { message: task, project_dir: project_dir }
  │     └─► Returns: { stream_url: "/api/direct/stream?..." }
  │
  └─► Consume SSE stream internally:
        async with client.stream("GET", f"{base_url}{stream_url}"):
          For each SSE event:
          ├─► event_type="turn" → update progress.turn, progress.max_turns
          ├─► event_type="tool_call" → update progress.step, total_steps
          ├─► event_type="tool_result" → update progress.step with result preview
          ├─► event_type="response" → capture result_text
          ├─► event_type="thinking" → update progress.step with preview
          ├─► event_type="test_phase" → update progress.step with test status
          ├─► event_type="test_feedback" → update progress.step, reset turn=0
          ├─► event_type="td_review" → update progress.step
          ├─► event_type="done" → break (success)
          └─► event_type="error" → raise Exception
  │
  ├─► _classify_result(result_text) → result_status
  ├─► _heartbeat_progress.update({active: False, result_status, result_message, ...})
  ├─► update_direct_todo(project, todo_id, "done", result_text)
  └─► record_heartbeat_run(project, todo_id, task, result_text)
```

### API Routes for Todo/Heartbeat
**File:** `backend/heartbeat.py`

| Method | Endpoint | Handler | Description |
|---|---|---|---|
| GET | `/api/direct/todos/{project}` | `api_get_todos` | List all todos |
| POST | `/api/direct/todos/{project}` | `api_add_todo` | Add todo |
| PUT | `/api/direct/todos/{project}/{id}` | `api_update_todo` | Update status |
| GET | `/api/direct/todos/{project}/{id}` | `api_get_todo` | Get todo + schedule info |
| DELETE | `/api/direct/todos/{project}/{id}` | `api_delete_todo` | Delete todo |
| GET | `/api/direct/heartbeat/{project}` | `api_get_heartbeat` | Get heartbeat config |
| POST | `/api/direct/heartbeat/{project}` | `api_set_heartbeat` | Enable/configure |
| POST | `/api/direct/heartbeat/{project}/run` | `api_run_heartbeat_now` | Run next todo NOW |
| GET | `/api/platform/heartbeat-progress` | `get_heartbeat_progress` | Poll current progress |

---

## 5. Deployment Flow (Pod Management)

### Entry Point
**File:** `backend/pipeline.py` — `deploy` tool handler (line ~500)

```
tool.name == "deploy":
  ├─► spin_up_pod(project_dir, project_name, port, version)
  │     [pod.py: spin_up_pod() — line ~150]
  │
  ├─► If success:
  │     ├─► rename_project(project_dir, project_name)
  │     ├─► write_project_env(project_dir, ..., extra={pod_port, deploy_version})
  │     ├─► _wpd(project_path, ...)  → frontend addProject() call
  │     └─► yield sse_event("pod_url", {url: _pod_url(port)})
  │           → Browser shows "Open App" button
  │
  └─► If failure:
        └─► yield error: "FAILED at {phase}: {message}\nLogs: {logs[:500]}"
```

### spin_up_pod() — Full Lifecycle
**File:** `backend/pod.py` — `spin_up_pod()` (line ~150)

```
Phase 1 — DESTROY:
  _force_destroy_pod(pod_name)
    └─► podman pod rm -f {pod_name}
  Wait up to 20s for port to be released
  If port still occupied → _kill_pod_on_port(port)

Phase 2 — BUILD:
  detect_app_type(project_dir)
    └─► Check files → "fastapi" | "flask" | "static" | "python-http"
  generate_containerfile(project_dir, app_type)
    └─► Write Containerfile to project_dir / Containerfile
  build_image(project_dir, image_name)
    └─► podman build -t {image_name} -f Containerfile {project_dir}
        Timeout: 120s

Phase 3 — START:
  _create_pod(pod_name, image_name, host_port)
    ├─► podman pod create --name {pod_name} -p {host_port}:8000
    └─► podman run -d --pod {pod_name} --name {pod_name}-app {image_name}

Phase 4 — HEALTH CHECK:
  health_check(port, path="/health", retries=15, delay=2.0)
    └─► Poll http://localhost:{port}/health
        Loop up to 15 times, 2s delay between attempts
        Success: HTTP 200 response
  If health fails:
    └─► _get_logs(pod_name) → capture container stderr/stdout
        → Returned in result["logs"] for Diagnostics agent

Return: { success, pod_name, port, version, message, logs, phase }
```

### Port Allocation
**File:** `backend/pod.py` — `get_available_port()` (line ~60)

```
get_available_port(project_name):
  ├─► Load .ports.json → build used={...}
  ├─► podman pod ls → extract actual port allocations
  ├─► For each port in POD_PORT_RANGE (11001-11098):
  │     ├─► Not in used set?
  │     ├─► Not in use by podman?
  │     └─► socket.bind() succeeds on 0.0.0.0:{port}?
  │           → If all pass: allocate to project, save to .ports.json
  └─► Return port or None

release_port(project_name):
  └─► Remove entry from .ports.json
```

### Diagnostics Agent Tools
**File:** `backend/pod.py` — `execute_pod_tool()` (line ~310)

```
list_project_files  → _pt_list_files(project_dir)
read_project_file    → _pt_read_file(project_dir, path)
edit_project_file    → _pt_edit_file(project_dir, path, content)
check_pod_status     → get_pod_status_by_name(pod_name) + http_get(port, "/health")
get_container_logs  → get_pod_logs_by_name(pod_name)
```

---

## 6. Config and State Management

### Config File
**File:** `backend/state.py` — `config` dict, loaded from `CONFIG_FILE` (`.config.json`)

```
.CONFIG.JSON STRUCTURE:
{
  "providers": {
    "openrouter": { "api_key": "...", "base_url": "https://openrouter.ai/api/v1", "models": [...] },
    "minimax":    { "api_key": "...", "base_url": "https://api.minimax.chat", "models": [...] }
  },
  "selected": "openrouter"        ← Active provider key
}

config = {"providers": {...}, "selected": "openrouter"}
  → Persisted to .config.json on changes
  → Loaded at startup by load_config()
```

### Provider Resolution
**File:** `backend/state.py` — `_get_provider()`

```
_get_provider():
  └─► return config["providers"][config["selected"]]
        → { api_key, base_url, model: config["selected_model"] }
```

### Per-Request State
**File:** `backend/pipeline.py` — `_direct_state` dict (line ~20)

```
_direct_state = {
  "project_dir": Path,     ← Current project path
  "project_name": str,     ← Project display name
  "port": int,            ← Assigned pod port
}

Updated at:
  ├─► direct_start() → after project resolution
  └─► direct_stream() → after set_active_project()
```

### Heartbeat Progress State
**File:** `backend/state.py` — `_heartbeat_progress` dict

```
_heartbeat_progress = {
  "active": bool,
  "project": str,
  "todo_id": str,
  "task": str,
  "step": str,             ← Current step description
  "turn": int,
  "max_turns": int,
  "total_steps": int,
  "started_at": iso_str,
  "finished_at": iso_str,
  "result_status": str,
  "result_message": str,
}

Polled by frontend: GET /api/platform/heartbeat-progress
```

### Agent State for Pod Tools
**File:** `backend/pod.py` — `_agent_state` dict (line ~295)

```
_agent_state = {
  "project_dir": Path,
  "project_name": str,
  "session_id": str,
  "host_port": int,
}

set_agent_state(project_dir, session_id, host_port, project_name)
  └─► Used by execute_pod_tool() for Diagnostics agent
```

### Message Trimming State
**File:** `backend/pipeline.py` — `_trim_messages()` (line ~190)

```
Never trims:
  ├─► Last 6 messages (protect recent contextblocks → first non-empty line summary
  ├─► old_text in patch_file args → "(trimmed N chars)"
  └─► Tool results (stale reads) → "(stale read — file patched later)"

Trimmed:
  ├─► File reads followed by a patch to the same file
  └─► Confirmatory bash output (exit code 0, git add/commit, pip install, etc.)
```

---

## 7. Branch / Prod Sync Flow

### Directory Structure
**File:** `backend/constants.py`

```
PROD_ROOT  = /path/to/aelidirect/          ← Production server (port 10100)
BRANCH_ROOT = /home/aeli/projects/aelidirect_branch  ← Testing server (port 10101)

PLATFORM_SOURCE_FILES = [
  "frontend/index.html", "backend/app.py", "backend/state.py",
  "backend/pipeline.py", "backend/heartbeat.py", "backend/platform_routes.py",
  "backend/history.py", "backend/td.py", "backend/docs.py",
  "backend/tools.py", "backend/direct_todo.py", "backend/llm_client.py",
  "backend/pod.py", "backend/test_agent.py", "backend/constants.py",
]

PLATFORM_DATA_DIRS = [
  "backend/.direct_conversations", "backend/.direct_heartbeats",
  "backend/.direct_todos", "backend/.direct_memory",
  "backend/.td_reports", "projects/",
]

PLATFORM_DATA_FILES = [
  "backend/.config.json", "backend/.ports.json",
  "SPEC.md", "CONTEXT_MAP.md", "DATA_FLOW.md",
]
```

### Platform Self-Editing (Auto-Wipe on Start)
**File:** `backend/pipeline.py` — `direct_stream()` platform check (line ~325)

```
When project_dir == "aelidirect_platform":
  │
  ├─► For each file in PLATFORM_SOURCE_FILES:
  │     ├─► Compare MD5 hash: PROD_ROOT/{file} vs BRANCH_ROOT/{file}
  │     └─► Check if branch_mtime > prod_mtime (branch was edited)
  │
  └─► If no branch files are newer:
        ├─► Import shutil
        ├─► For each PLATFORM_SOURCE_FILE:
        │     └─► shutil.copy2(prod_file, branch_file)
        ├─► file_cache_wipe_branch()           [tools.py]
        │     └─► _file_cache_branch.clear()
        │         _file_cache_branch.update(_file_cache_main)
        └─► Log: "[platform] Auto-wiped branch from prod (no testing in progress)"
        │
        └─► Agent edits BRANCH_ROOT files directly
```

### Branch Status Check
**File:** `backend/platform_routes.py` — `get_branch_status()` (line ~20)

```
GET /api/platform/branch-status:
  ├─► Compare MD5 hashes for all PLATFORM_SOURCE_FILES
  ├─► For each file:
  │     ├─► Both exist + same hash → unchanged
  │     ├─► Only branch exists → "added"
  │     ├─► Only prod exists → "removed"
  │     └─► Different hash → "modified", include branch_newer flag + mtimes
  └─► Return: { has_changes, changes: [{file, status, branch_newer?}], branch_path }
```

### Branch Wipe (Prod → Branch)
**File:** `backend/platform_routes.py` — `wipe_branch()` (line ~50)

```
POST /api/platform/branch-wipe:

Blocks if:
  └─► _heartbeat_progress["active"] AND project == "aelidirect_platform"
        → "Agent is actively editing branch files — wait for completion"

Execution:
  1. Source files:
       For each PLATFORM_SOURCE_FILE:
         └─► shutil.copy2(prod_file, branch_file)

  2. Data directories (full sync):
       For each PLATFORM_DATA_DIR:
         └─► shutil.copytree(prod_dir, branch_dir, symlinks=True)

  3. Data files:
       For each PLATFORM_DATA_FILE:
         └─► shutil.copy2(prod_file, branch_file)

  4. Cache sync:
       └─► file_cache_wipe_branch()
             → _file_cache_branch = _file_cache_main (copy)

  5. Restart branch server:
       └─► systemctl --user restart aelidirect-branch.service
             → Branch server picks up new file cache
```

### Branch Deploy (Branch → Prod)
**File:** `backend/platform_routes.py` — `deploy_branch()` (line ~100)

```
POST /api/platform/branch-deploy:

Blocks if:
  ├─► Running from branch server (_IS_BRANCH)
  ├─► _heartbeat_progress["active"]          → "Agent is running"
  └─► get_heartbeat("aelidirect_platform").running → "Branch is running a task"

Execution:
  1. Source files:
       For each PLATFORM_SOURCE_FILE:
         └─► shutil.copy2(branch_file, prod_file)

  2. If any errors → abort, return errors

  3. Cache sync:
       └─► file_cache_deploy_to_main()
             → For each entry in _file_cache_branch:
               _file_cache_main[key] = content
             → Only copies branch cache entries (platform-related)

  4. Restart prod server:
       └─► systemctl --user restart aelidirect.service
             → Prod server restarts with new source code
```

### Frontend Branch Bar
**File:** `frontend/index.html` — `checkBranchStatus()`, `pollHeartbeatProgress()` (line ~1)

```
checkBranchStatus() [polls /api/platform/branch-status]:
  ├─► If is_branch=True → show "You are on the branch server"
  └─► Else → show branch status:
        ├─► No changes → idle state
        └─► Branch has newer files → show file names, test/deploy buttons

pollHeartbeatProgress() [polls /api/platform/heartbeat-progress]:
  ├─► If active → show pulsing indicator, current step, elapsed time
  └─► If finished → show result status (success/failure/partial), refresh data

Branches:
  ├─► Wipe button → POST /api/platform/branch-wipe
  ├─► Deploy button → POST /api/platform/branch-deploy
  └─► Heartbeat progress bar (merged into branch bar)
```

### File Cache Dual-Channel
**File:** `backend/tools.py` — dual cache system (line ~35)

```
Platform editing uses BOTH caches simultaneously:

_main_cache:     Persists across prod ↔ branch syncs
_branch_cache:   Tracks agent's live edits on branch

Cache operations:
  ├─► Read (agent reads file):
  │     └─► _is_platform_project? → _file_cache_branch.get()
  │         (reads from branch cache, not disk, during editing)
  │
  ├─► Write (agent patches file):
  │     └─► file_cache_set(project, path, content)
  │         → Updates _file_cache_branch (platform) or _file_cache_main (other)
  │
  ├─► Branch wipe:
  │     └─► file_cache_wipe_branch()
  │         → _file_cache_branch = _file_cache_main.copy()
  │
  └─► Branch deploy:
        └─► file_cache_deploy_to_main()
            → _file_cache_main.update(_file_cache_branch)
            → Branch edits now reflected in main cache
```

---

## End-to-End Summary

```
USER sends message
  │
  ▼
POST /api/direct/start         [pipeline.py: direct_start()]
  ├─► Determine/create project
  ├─► Allocate port
  └─► Return stream_url
  │
  ▼
EventSource GET /api/direct/stream    [pipeline.py: direct_stream()]
  ├─► Platform self-editing: auto-wipe or live-edit BRANCH_ROOT
  ├─► Build system prompt (+ SITE_MAP, SPEC, memory, history)
  ├─► Phase 1: PLANNING (call_llm, no tools)
  │     └─► LLM responds with text plan
  ├─► Phase 2: CODING (call_llm, tools enabled, up to 150 turns)
  │     └─► Tool call loop: execute_tool() → tool_result → call_llm()
  │           ├─► File tools: tools.py execute_tool() → cache
  │           ├─► deploy: pod.py spin_up_pod() → podman → health check
  │           ├─► memory: MEMORY_DIR read/write
  │           ├─► test_agent: test_agent.py handle_test_agent()
  │           └─► bash/git/http: subprocess / httpx
  ├─► Phase 3: TEST (if tools used or automated)
  │     └─► test_and_fix_loop(): plan → run → fix → re-run (≤2 iters)
  │           ├─► Phase 1: call_llm with PLAN_SYSTEM_PROMPT → test plan JSON
  │           ├─► Phase 2: run_tests() → api/browser/unit
  │           └─► On failure: send_to_chat_pipeline() → chat pipeline fix
  ├─► Phase 4: TD REVIEW (if tools used)
  │     └─► call_llm with TODO_TD_REVIEW_PROMPT → verdict + review
  └─► On done:
        ├─► _save_conversation() → CONVERSATIONS_DIR
        ├─► _regenerate_docs() [background] → SPEC, SITE_MAP, etc.
        └─► Branch restart if platform editing + code changed + no tests

HEARTBEAT triggers independently:
  every 30s scheduler → check intervals → _execute_todo_via_chat()
    └─► POST /api/direct/start + SSE consume internally
          └─► Same pipeline as user message

BRANCH/PROD sync:
  WIPE:   Prod → Branch  [POST /api/platform/branch-wipe]
  DEPLOY: Branch → Prod [POST /api/platform/branch-deploy]
  AUTO:   On platform chat start, if branch not newer → prod → branch
```
</think>

# aelidirect -- Data Flow

## Table of Contents
1. [Main Chat Flow](#1-main-chat-flow)
2. [Tool Call Loop](#2-tool-call-loop)
3. [Memory System](#3-memory-system)
4. [Heartbeat / Todo Execution Flow](#4-heartbeat--todo-execution-flow)
5. [Deployment Flow (Pod Management)](#5-deployment-flow-pod-management)
6. [Config and State Management](#6-config-and-state-management)
7. [Branch / Prod Sync Flow](#7-branch--prod-sync-flow)

---

## 1. Main Chat Flow

### Entry Point: `POST /api/direct/start`
**File:** `backend/pipeline.py` — `direct_start()` (line ~270)

```
Browser/Client
  │
  └─► POST /api/direct/start
        body: { message, project_dir?, project_name? }
        │
        ├─► Determine project
        │     ├─► If project_dir provided → read project_env.md from PROJECTS_ROOT / project_dir
        │     └─► Else → derive safe_name from message, init_project_dir(), write_project_env()
        │
        ├─► set_active_project(project_path)         [tools.py: set_active_project()]
        │
        ├─► read_project_env(project_dir)            [tools.py: read_project_env()]
        │     → returns { project_name, tech_stack, pod_port, ... }
        │
        └─► Returns JSON:
              { project_dir, project_name, port,
                stream_url: "/api/direct/stream?message=...&project_dir=..." }
```

### Streaming Endpoint: `GET /api/direct/stream`
**File:** `backend/pipeline.py` — `direct_stream()` (line ~310)

```
Browser EventSource
  │
  └─► GET /api/direct/stream?message=...&project_dir=...
        │
        ├─► Platform self-editing check
        │     └─► If project_dir == "aelidirect_platform" AND BRANCH_ROOT exists:
        │           ├─► Compare MD5 hashes of PLATFORM_SOURCE_FILES (prod vs branch)
        │           ├─► If branch newer → work on BRANCH_ROOT files (live editing)
        │           └─► If no branch newer → auto-wipe: copy PROD_ROOT → BRANCH_ROOT
        │                 [tools.py: file_cache_wipe_branch()]
        │
        ├─► set_active_project(project_path)         [tools.py: set_active_project()]
        │
        ├─► Build system prompt (concatenated):
        │     ├─► DIRECT_AGENT_PROMPT (core instructions)
        │     ├─► SITE_MAP.md (if exists)            [PROD_ROOT / "SITE_MAP.md"]
        │     ├─► SPEC.md (if exists)               [PROD_ROOT / "SPEC.md"]
        │     ├─► LONG-TERM MEMORY                   [MEMORY_DIR / {project_name}/*.md]
        │     └─► RECENT CONVERSATION HISTORY        [history.py: _load_conversation_history()]
        │           → Loads last 5 conversations (last 40k chars)
        │
        └─► Returns StreamingResponse (SSE)
              messages = [{"role": "system", "content": system_prompt},
                          {"role": "user", "content": msg}]
```

### Three-Phase Pipeline

#### Phase 1 — PLANNING (no tools, forced text response)
**File:** `backend/pipeline.py` — inside `direct_stream()` `event_generator()` (line ~380)

```
yield sse_event("phase", {"phase": "planning"})
yield sse_event("turn",  {"turn": 1, "action_turns": 0, "max": MAX_ACTION_TURNS})
  │
  └─► call_llm(selected, api_key, base_url, model,
               messages,                    ← system + user
               tools=None,                   ← NO TOOLS (plain text only)
               temperature=0.3)
      [llm_client.py: call_llm()]

      ├─► HTTP POST to LLM API endpoint
      │     └─► Request body includes messages + temperature + max_tokens
      │
      └─► extract_response(raw)
            └─► Returns { type: "text", content: "...", tool_calls: [] }

yield sse_event("thinking", {"content": plan_text})
messages.append({"role": "assistant", "content": plan_text})
messages.append({"role": "user", "content": "Good plan. Execute it now."})
```

#### Phase 2 — CODING (tools enabled, up to MAX_ACTION_TURNS)
**File:** `backend/pipeline.py` — `while action_turns < max_turns` loop (line ~400)

```
yield sse_event("phase", {"phase": "coding"})

while action_turns < MAX_ACTION_TURNS:
    │
    ├─► _trim_messages(messages)              [pipeline.py: _trim_messages()]
    │     → Collapses)
  ├─► User messages
  └─► System messages

Collapses:
  ├─►