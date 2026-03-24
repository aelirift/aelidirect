<think>
The user wants me to generate a DATA_FLOW.md file that traces the data flow through the aelidirect system. Let me analyze all the provided source code files and trace the 7 specified flows:

1. Main chat flow (user message → SSE stream → agent loop → response)
2. Tool call loop (LLM response → tool execution → result → next LLM call)
3. Memory system (long-term save/load, short-term conversation history)
4. Heartbeat/todo execution flow
5. Deployment flow (pod management)
6. Config and state management
7. Branch/prod sync flow

Let me trace through each file systematically:


- `backend/app.py` contains the FastAPI router registration and application setup
- `backend/state.py` manages the global config dictionary
- `backend/pipeline.py` implements the core streaming chat pipeline with the agent loop
- `backend/heartbeat.py` handles the scheduler, executor, and todo/heartbeat routes
- `backend/platform_routes.py` manages branch/prod operations and deployment
- `backend/history.py` persists conversation history
- `backend/td.py` provides TD (Technical Director) review endpoints
- `backend/docs.py` handles auto-documentation regeneration
- `backend/tools.py` defines the tools available to the agent
- `backend/direct_todo.py` manages the todo list and heartbeat system
- `backend/llm_client.py` handles LLM API calls
- `backend/pod.py` manages containerized pods
- `backend/test_agent.py` implements automated testing
- `backend/constants.py` contains all shared constants
- `frontend/index.html` is the user interface

Now I'm ready to trace through the complete data flow.
</think>

# aelidirect -- Data Flow

This document traces all major data flows through the aelidirect codebase, step by step with file names, function names, and line numbers.

---

## 1. Main Chat Flow

**Route:** `frontend/index.html` → `backend/pipeline.py` → `backend/llm_client.py` → SSE stream back to frontend

### Step 1 — User sends a message (frontend)

```
frontend/index.html
  → sendMessage()                     [~line 500]
    → POST /api/direct/start           { message, project_dir }
    → GET /api/direct/stream           (EventSource opens SSE stream)
```

The frontend POSTs to `create_or_select_project` to establish the project context, then opens an `EventSource` to the streaming endpoint.

### Step 2 — Project setup and streaming start

```
backend/pipeline.py
  → POST /api/direct/start
    create_or_select_project()         [~line 130]
      - Reads project metadata from project_env.md
      - Sets _direct_state["project_dir"], ["project_name"], ["port"]
      - Returns { stream_url } pointing to /api/direct/stream

  → GET /api/direct/stream
    run_chat_pipeline()                [~line 168]
      - Prov = _get_provider()          (reads config for API key)
      - For platform self-editing: redirects to BRANCH_ROOT if newer files exist
      - Calls event_generator() coroutine
```

### Step 3 — System prompt assembly (inside event_generator)

```
backend/pipeline.py
  → event_generator()                  [~line 183]
      System prompt is built from multiple sources in order:
      1. DIRECT_AGENT_PROMPT            (base instructions from state.py)
      2. SITE_MAP.md                    (file/function tree, PROD_ROOT / "SITE_MAP.md")
      3. SPEC.md                        (project specification, PROD_ROOT / "SPEC.md")
      4. Long-term memory               (MEMORY_DIR / project_name / "*.md" files)
      5. Recent conversation history    _load_conversation_history() from history.py

      messages = [
          {"role": "system", "content": system_prompt},
          {"role": "user",   "content": msg},
      ]
```

### Step 4 — Agent loop (coding phase)

```
backend/pipeline.py
  → while action_turns < max_turns       [~line 241]
      1. _trim_messages(messages)       (removes stale/redundant content)
      2. call_llm()                      via llm_client.py
         - Posts to OpenRouter/OpenAI endpoint
         - Passes trimmed messages + DIRECT_TOOL_DEFS
      3. extract_response(raw)           (parses tool_calls or text from LLM response)
      4. Yield SSE events to frontend:
         - sse_event("turn", {turn, action_turns, max})
         - sse_event("response", {content})      if text response
         - sse_event("thinking", {content})      if thinking content
         - sse_event("tool_call", {name, args})  per tool call
```

### Step 5 — SSE events to frontend

```
backend/state.py
  → sse_event(event_type, data)         [~line 8]
      return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"

backend/pipeline.py
  → yield sse_event(...)                (multiple call sites)
      StreamingResponse(event_generator(), media_type="text/event-stream")
```

The frontend `EventSource` receives these as `event.data` objects. Events flow in order:
`turn` → `phase` → `tool_call` → `tool_result` → `response` → `test_phase` → `td_review` → `done`

---

## 2. Tool Call Loop

**Route:** LLM decides to call a tool → tool executes → result appended to messages → LLM called again

### Step 1 — LLM responds with tool_calls

```
backend/llm_client.py
  → call_llm(..., tools=DIRECT_TOOL_DEFS)  [~line 36]
      - Sends messages + tools schema to LLM provider
      - LLM returns {"choices": [{"message": {"tool_calls": [...]}}]}
      - Returns raw API response dict

  → extract_response(raw)                [~line 67]
      - If tool_calls present: returns {"type": "tool_call", "tool_calls": [...]}
      - If text: returns {"type": "text", "content": "..."}
```

### Step 2 — Tool definitions (sent to LLM)

```
backend/state.py
  → DIRECT_TOOL_DEFS                    [~line 55]
      Copied from tools.py TOOL_DEFINITIONS (8 tools)

backend/tools.py
  → TOOL_DEFINITIONS                     [~line 135]
      list_files, read_file, edit_file, patch_file,
      read_file_tail, read_lines, grep_code, read_project
```

### Step 3 — Tool execution dispatch

```
backend/pipeline.py
  → for tc in parsed["tool_calls"]:      [~line 272]
      name = tc["function"]["name"]
      args = json.loads(tc["arguments"])

      if name in (hardcoded tools):
          execute hardcoded implementation (bash, git_status, git_diff,
                                            memory_save, memory_load, memory_list,
                                            test_agent, http_check)
      else:
          execute_tool(name, args, project_dir=project_path)
```

### Step 4 — Tool executors

```
backend/tools.py
  → execute_tool(name, arguments, project_dir)  [~line 280]
      Dispatches to individual tool functions:
      - _tool_list_files()     [~line 310]  → lists project directory
      - _tool_read_file()     [~line 325]  → reads file (with caching)
      - _tool_edit_file()     [~line 368]  → writes new file
      - _tool_patch_file()    [~line 385]  → targeted file edit (find/replace)
      - _tool_read_file_tail()[~line 445]  → last N lines
      - _tool_read_lines()    [~line 478]  → line range (with ±20 padding)
      - _tool_grep_code()     [~line 500]  → pattern search across files
      - _tool_read_project()  [~line 527]  → batch read (or file listing if over budget)

      File caching (for platform self-editing):
      → file_cache_get(project, path)     [~line 60]  — reads branch or main cache
      → file_cache_set(project, path, content) [~line 66] — updates branch cache
```

### Step 5 — Result fed back to LLM

```
backend/pipeline.py
  → messages.append({"role": "tool", "tool_call_id": tc["id"], "content": result})
      - Result is truncated to TRUNCATE_TOOL_RESULT (2000 chars)
      - Messages list grows: user → assistant(tool_calls) → tool → assistant(tool_calls) → tool → ...
      - Loop continues: next call_llm() gets updated messages
      - action_turns incremented (unless all tools are readonly)
```

### Step 6 — Loop termination

```
backend/pipeline.py
  → if parsed["type"] == "text":        [~line 252]
      yield sse_event("response", {content})  → break
      → Exit agent loop, proceed to test phase
```

---

## 3. Memory System

### Long-term memory (per-project, persistent `.md` files)

```
backend/pipeline.py
  → event_generator() builds system prompt:   [~line 207]
      mem_dir = MEMORY_DIR / project_path.name   (constants.py: MEMORY_DIR = backend/.direct_memory)
      for f in sorted(mem_dir.glob("*.md")):
          memories.append(f"[{f.stem}]: {f.read_text()[:500]}")
      system_prompt += "\n\n[LONG-TERM MEMORY]\n" + "\n".join(memories)

backend/pipeline.py
  → Tool "memory_save":                  [~line 318]
      key = args.get("key", "").replace("/", "_").replace("..", "")
      mem_dir = MEMORY_DIR / project_path.name
      mem_dir.mkdir(exist_ok=True)
      (mem_dir / f"{key}.md").write_text(content)
      → Stored as .direct_memory/{project_name}/{key}.md

  → Tool "memory_load":                  [~line 326]
      mem_path = MEMORY_DIR / project_path.name / f"{key}.md"
      → Returns file contents or "not found"

  → Tool "memory_list":                  [~line 333]
      mem_dir = MEMORY_DIR / project_path.name
      → Lists all .md files in the memory directory
```

### Short-term conversation history (persisted to disk after chat)

```
backend/history.py
  → _save_conversation(project_name, user_message, messages, test_evidence)  [~line 16]
      conv_dir = CONVERSATIONS_DIR / project_name    (backend/.direct_conversations/)
      - Strips system messages and tool call schemas
      - Saves as {timestamp}.json with format:
        { timestamp, user_message, messages: [{role, content, tools?, result?}], llm_summary }
      - test_evidence appended if available

  → _load_conversation_history(project_name, prov, selected)  [~line 55]
      - Loads last 5 conversation files
      - Converts each to text (llm_summary if available, else message summary)
      - Returns concatenated string for system prompt
      - Old conversations pruned to CONVERSATION_HISTORY_LIMIT (50)

  → Called in pipeline.py event_generator() before first LLM call  [~line 211]
      conv_history = await asyncio.to_thread(_load_conversation_history, ...)
      system_prompt += "\n\n[RECENT CONVERSATION HISTORY]\n" + conv_history
```

### Old conversation summarization (background)

```
backend/history.py
  → _summarize_old_conversations(conversations, prov, selected)  [~line 87]
      - Finds conversations without llm_summary (excluding last 10)
      - Batches first 10 unsummarized, sends to LLM with summarization prompt
      - LLM produces one-line summaries: bugs, fixes, features, deploy results
      - Writes llm_summary back to each .json file
      - Called from a background task (not in main chat path)
```

---

## 4. Heartbeat / Todo Execution Flow

### Todo CRUD (persistent task list)

```
backend/direct_todo.py
  → add_todo(project_name, task, category)       [~line 27]
      - Creates UUID[:8] for todo_id
      - Initial status: "pending"
      - Saved to TODOS_DIR / {safe_name}.json    (backend/.direct_todos/)

  → update_todo(project_name, todo_id, status, result)  [~line 51]
      - status = "attempted": sets started_at, increments attempts
      - status = "done": sets completed_at, computes duration_secs
      - result classified via _classify_result() → success/failure/partial

  → get_pending_todos(project_name)              [~line 97]
      - Returns todos with status in ("pending", "attempted")

  → _classify_result(result)                     [~line 41]
      - failure: contains error/failed/traceback/exception/...
      - partial: contains partially/issue/warning/but/...
      - else: success
```

### Heartbeat configuration

```
backend/direct_todo.py
  → get_heartbeat(project_name)                   [~line 108]
      - Reads HEARTBEATS_DIR / {safe_name}.json   (backend/.direct_heartbeats/)
      - Fields: enabled, interval_minutes, last_run, running, history[]

  → save_heartbeat(project_name, hb)             [~line 117]

  → record_heartbeat_run(project_name, todo_id, task, result)  [~line 120]
      - Appends to history[] (last 50)
      - Updates last_run timestamp
```

### Heartbeat scheduler (background loop)

```
backend/heartbeat.py
  → _heartbeat_scheduler()                        [~line 78]
      - Runs as asyncio task (started from app.py on server boot)
      - Every 30 seconds:
        1. Scans HEARTBEAT_DIR / "*.json" files
        2. Checks hb["enabled"] and hb["running"]
        3. Checks interval elapsed since last_run
        4. Gets pending todos via get_pending_todos()
        5. Calls _execute_todo_via_chat(project_dir, pending[0])
        6. On completion: updates last_run, sets running=False

  → _execute_todo_via_chat(project_dir, todo_item)  [~line 29]
      The core execution path — same pipeline as browser chat:
      1. POST /api/direct/start    → gets stream_url
      2. AsyncClient.stream("GET", stream_url)    → consumes SSE events
      3. Parses each SSE event type:
         - "turn": updates _heartbeat_progress["turn"]
         - "tool_call": increments total_steps, updates step preview
         - "tool_result": captures result preview
         - "response": saves result_text
         - "test_phase": updates step with test iteration info
         - "td_review": updates step
         - "done": exits loop
      4. On completion:
         - update_direct_todo(..., "done", result_text)
         - record_heartbeat_run(...)
         - _heartbeat_progress updated with result_status

  → trigger_heartbeat_now(project_dir)             [~line 185]
      - POST /api/direct/heartbeat/{project_dir}/run
      - Manual trigger (same as UI "Run Now" button)
      - Sets running=True, calls _execute_todo_via_chat(), finally sets running=False
```

---

## 5. Deployment Flow (Pod Management)

**Route:** User triggers deploy → source copied → cache synced → service restarted

### Pod lifecycle (build + run + health check)

```
backend/pod.py
  → spin_up_pod(project_dir, project_name, host_port, version)  [~line 140]
      The single entry point for all pod deployment:

      Phase 1 — DESTROY
      → _force_destroy_pod(pod_name)              [~line 105]
          podman pod rm -f {pod_name}
      → Wait up to 15s for port to free
      → If still occupied: _kill_pod_on_port()   [~line 175]

      Phase 2 — BUILD
      → detect_app_type(project_dir)              [~line 68]
          Scans .py files for FastAPI/Flask → "fastapi"/"flask"/"static"
      → generate_containerfile(project_dir, app_type)  [~line 82]
          Writes Containerfile to project_dir/Containerfile
      → build_image(project_dir, image_name)     [~line 98]
          podman build -t {image_name} -f Containerfile {project_dir}
          Timeout: 120s

      Phase 3 — START
      → _create_pod(pod_name, image_name, host_port)  [~line 113]
          podman pod create --name {pod_name} -p {host_port}:{INTERNAL_PORT}
          podman run -d --pod {pod_name} --name {pod_name}-app {image_name}
          Timeout: 60s

      Phase 4 — HEALTH CHECK
      → health_check(port, path="/health", retries=15, delay=2.0)  [~line 128]
          Polls http://localhost:{port}/health
          Waits for HTTP 200
          Returns on first success; fails after 15 attempts × 2s = 30s

      Returns: {success, pod_name, port, version, message, logs, phase}
      On failure: logs gathered via _get_logs(pod_name) [~line 200]
```

### Pod tool interface (for diagnostics)

```
backend/pod.py
  → POD_TOOL_DEFINITIONS                         [~line 237]
      list_project_files, read_project_file, edit_project_file,
      check_pod_status, get_container_logs

  → execute_pod_tool(name, arguments)           [~line 260]
      - check_pod_status: uses get_pod_status_by_name() + http_get()
      - get_container_logs: calls _get_logs(pod_name)
```

### Port allocation

```
backend/pod.py
  → get_available_port(project_name)              [~line 43]
      - Checks .ports.json file (in-memory dict + disk)
      - Cross-checks with podman pod ls
      - Verifies port is free at OS socket level via _is_port_free()
      - Returns first free port in POD_PORT_RANGE (11001–11098)
      - Saves allocation to .ports.json

  → release_port(project_name)                   [~line 60]
      - Removes entry from .ports.json
```

---

## 6. Config and State Management

### Global config (in-memory + disk persistence)

```
backend/state.py
  → config = {}                                  [~line 1]
      In-memory dict shared across all requests

  → _load_config()                              [~line 12]
      - Reads .config.json (backend/.config.json)
      - Sets default values for missing keys
      - Called at module import time

  → _save_config()                              [~line 20]
      - Writes config dict back to .config.json
      - Called after any config mutation

  Config keys:
    - selected: which provider is active ("openrouter", "minimax", ...)
    - providers[provider_name]: {api_key, base_url, model}
    - Other: platform_name, auto_test, td_review, etc.
```

### Provider selection

```
backend/state.py
  → _get_provider()                             [~line 27]
      - Returns config["providers"][config["selected"]]
      - Used by pipeline.py and heartbeat.py before every LLM call

  → _set_provider(name)                         [~line 33]
      - Sets config["selected"] = name
      - Saves config to disk
```

### Direct state (per-request, not persisted)

```
backend/state.py
  → _direct_state = {}                          [~line 42]
      Per-conversation in-memory state:
      - project_dir, project_name, port
      - Set in create_or_select_project() and run_chat_pipeline()

  → _heartbeat_progress = {}                    [~line 44]
      Global heartbeat execution status (used by platform_routes.py for deploy guards):
      - active, project, todo_id, task, step, turn, max_turns, total_steps
      - started_at, finished_at, result_status, result_message
```

### Constants (single source of truth)

```
backend/constants.py
  → All paths, ports, timeouts, limits, directory paths
  → PROD_ROOT = backend/../ (project root)
  → BRANCH_ROOT = /home/aeli/projects/aelidirect_branch
  → PROJECTS_ROOT = PROD_ROOT / "projects"
  → Storage dirs: MEMORY_DIR, CONVERSATIONS_DIR, TODOS_DIR, HEARTBEATS_DIR, TD_REPORTS_DIR
  → Platform files: PLATFORM_SOURCE_FILES (16 files)
  → Platform data: PLATFORM_DATA_DIRS (6 dirs), PLATFORM_DATA_FILES (5 files)
```

---

## 7. Branch / Prod Sync Flow

### Architecture overview

```
BRANCH_ROOT = /home/aeli/projects/aelidirect_branch
PROD_ROOT   = backend/../  (where the server runs)
BRANCH_PORT = 10101  (branch server)
PROD_PORT   = 10100  (prod server)

Two servers run simultaneously:
  - aelidirect.service      on port 10100 (uses PROD_ROOT)
  - aelidirect-branch.service on port 10101 (uses BRANCH_ROOT)
```

### Platform self-editing detection (in chat pipeline)

```
backend/pipeline.py
  → run_chat_pipeline()                         [~line 178]
      If project_dir == "aelidirect_platform":
          Compare MD5 + mtime of PLATFORM_SOURCE_FILES in prod vs branch
          If branch files are newer: work on BRANCH_ROOT
          Else: auto-wipe branch (copy prod → branch), then work on BRANCH_ROOT
      project_path = BRANCH_ROOT (not PROD_ROOT) for platform editing
```

### Branch status check

```
backend/platform_routes.py
  → GET /api/platform/branch-status              [~line 17]
      get_branch_status():
      - Compares MD5 hash of each file in PLATFORM_SOURCE_FILES
      - Returns: has_changes, changes[{file, status, branch_newer?, mtimes}]
      - If running on branch server: returns {has_changes: false, is_branch: true}
```

### Branch wipe (prod → branch)

```
backend/platform_routes.py
  → POST /api/platform/branch-wipe               [~line 52]
      wipe_branch():
      Blocked if: _heartbeat_progress["active"] && project == "aelidirect_platform"

      Step 1: Source files
      → shutil.copy2(prod_file, branch_file)    for each in PLATFORM_SOURCE_FILES

      Step 2: Data directories (full sync, preserve symlinks)
      → shutil.copytree(prod_dir, branch_dir, symlinks=True)  for each in PLATFORM_DATA_DIRS
         (directories: .direct_conversations, .direct_heartbeats, .direct_todos,
                       .direct_memory, .td_reports, projects/)

      Step 3: Data files
      → shutil.copy2(prod_file, branch_file)    for each in PLATFORM_DATA_FILES

      Step 4: Sync file caches
      → file_cache_wipe_branch()                (tools.py: clears branch cache, copies main→branch)

      Step 5: Restart branch server
      → systemctl --user restart aelidirect-branch.service
         (restart picks up new file content; clears in-process caches)
```

### Branch deploy (branch → prod)

```
backend/platform_routes.py
  → POST /api/platform/branch-deploy             [~line 95]
      deploy_branch():
      Blocked if:
        - Running on branch server itself (_IS_BRANCH)
        - _heartbeat_progress["active"]        (agent is running)
        - get_heartbeat("aelidirect_platform")["running"]  (branch agent is running)

      Step 1: Copy source files
      → shutil.copy2(branch_file, prod_file)    for each in PLATFORM_SOURCE_FILES

      Step 2: Sync file caches
      → file_cache_deploy_to_main()             (tools.py: copies branch cache → main cache)
         Only after successful file copy (guaranteed atomic-ish)

      Step 3: Restart prod server
      → systemctl --user restart aelidirect.service
         (prod server restarts, picks up new source files)

      Step 4: Prod server comes back up
      → Backend .config.json and .ports.json are NOT synced (intentional — runtime state)
```

### File cache dual-cache system (platform only)

```
backend/tools.py
  → _file_cache_main = {}                       [~line 42]
      Caches reads from PROD_ROOT files

  → _file_cache_branch = {}                     [~line 43]
      Caches edits made by the agent on BRANCH_ROOT files
      (Diverges from main cache during editing)

  → file_cache_wipe_branch()                   [~line 77]
      _file_cache_branch.clear()
      _file_cache_branch.update(_file_cache_main)
      Called on: branch wipe, pipeline auto-wipe

  → file_cache_deploy_to_main()                 [~line 81]
      For each entry in branch cache: copy to main cache
      Called on: successful deploy

  → _is_platform_project(project)               [~line 55]
      project.name == "aelidirect_platform" or project.resolve() == BRANCH_ROOT.resolve()

  → file_cache_get(project, path)               [~line 62]
      Returns from _file_cache_branch if platform project, else _file_cache_main

  → file_cache_set(project, path, content)      [~line 66]
      Updates branch cache if platform, else main cache
```

### SSE event flow summary (all phases)

```
backend/pipeline.py — event_generator() yields events in this order:

1. phase        → {"phase": "coding"}           (coding phase starts)
2. turn          → {"turn": N, "action_turns": N, "max": 150}  (per LLM call)
3. thinking      → {"content": "..."}            (if LLM outputs thinking)
4. tool_call     → {"name": "...", "args": {...}} (per tool invocation)
5. tool_result   → {"name": "...", "result": "..."}  (per tool completion)
   [... repeats steps 2-5 for each LLM turn ...]
6. phase         → {"phase": "testing"}          (test phase starts)
   test_phase    → {"status": "planning"|"running"|"all_passed"|"error", ...}
   test_feedback  → {"failed": N, "iteration": N, "total": N, "passed": N}
   [... fix loop: coding → testing → ...]
7. phase         → {"phase": "post_test"}
8. td_review     → {"status": "running"|"complete"|"error", "review": "..."}
9. done          → {"turns", "action_turns", "test_evidence", "td_review"}
   [pipeline saves conversation, regenerates docs, restarts branch if needed]
```