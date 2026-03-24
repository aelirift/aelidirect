<think>
The user wants me to produce a DATA_FLOW.md file documenting the data flow in the aelidirect system. I need to trace through the code carefully and document:

1. Main chat flow (user message → SSE stream → agent loop → response)
2. Tool call loop (LLM response → tool execution → result → next LLM call)
3. Memory system (long-term save/load, short-term conversation history)
4. Heartbeat/todo execution flow
5. Deployment flow (pod management)
6. Config and state management
7. Branch/prod sync flow

Let me trace through each of the source files carefully to produce accurate documentation.


Now I'm examining the key files to understand the system architecture: the constants and state management, the main application routes, the core chat pipeline with its SSE streaming and agent loop, the heartbeat scheduler, platform routes for branch management, conversation history handling, the technical debt review system, auto-documentation generation, tool definitions and execution, the todo and heartbeat management, LLM client interactions, pod/container management, the testing agent, and the frontend interface.

I need to trace through the actual execution flow in pipeline.py starting from the `/api/direct/start` endpoint, which takes a message and project directory, then redirects to the `/api/direct/stream` endpoint that returns an SSE response containing the system's primary prompt, site map, spec, long-term memory, recent conversation history, and an initial planning turn without tools. The agent loop follows a specific pattern where each turn trims messages, calls the LLM, and then handles any tool calls that are generated. The system prompt is loaded from the project directory and augmented with recent conversation history, giving the LLM context about what's happened before in this project.

Now I'm tracing through the execution phases: the planning turn generates a strategy without tools, then the coding phase runs where the LLM calls tools repeatedly until either the max turns are reached or no more tool calls are needed. After that comes the testing phase where automated tests are planned and executed, followed by a TD review that evaluates the overall output.

For tool execution, I need to track how the LLM response gets parsed and tools are called—each tool goes through `execute_tool()` in tools.py, and the pipeline handles built-in commands like bash, git operations, memory management, and test execution, returning results via SSE events back to the frontend.

Now I'm mapping out the memory system: there's short-term conversation history stored in JSON files under `CONVERSATIONS_DIR`, with recent messages capped at 5 files and old conversations auto-summarized to save space. Long-term memory lives in separate files organized by project and key in `MEMORY_DIR`.

For the heartbeat system, there's a scheduler running every 30 seconds that checks if any todo items are due, then executes them by calling the chat pipeline internally through HTTP. The heartbeat route can also be triggered manually, and it maintains progress tracking throughout execution.

Now I'm looking at the todo list management system itself—todos are stored in JSON files under `TODOS_DIR`, each with fields tracking status, attempts, results, and duration. There's a result classifier that determines success, partial, or failure based on error keywords in the output.

For the test agent, I'm seeing a two-phase approach where tests are first planned using the LLM, then executed through HTTP requests, potentially in a fix loop that cycles through up to 2 iterations.

Moving into pod management, the system allocates ports from a JSON file, detects the application type, generates a Containerfile, and builds the pod with podman before handling the deployment.

For config and state, I'm tracking how global configuration is stored in a JSON file, provider settings are retrieved, and the pod URL is dynamically constructed from constants.

The direct state module manages conversation context and active project state, while the pod agent state tracks project details and ports during execution.

On the branch and production sync side, I'm setting up a dual-file caching system where the main cache holds production files and the branch cache diverges from it, allowing selective deployment of platform-related entries back to main.

For the branch workflow, the system auto-wipes the branch by copying production files before starting the pipeline, making edits directly to branch files, then handles cleanup through platform route handlers that compare branch and production files using MD5 hashes, with separate endpoints for wiping the branch and deploying changes back.

The actual synchronization happens through file cache functions that copy the main cache to branch cache on wipe, then deploy by copying the branch cache back to main cache, with the deployed content being what the LLM agent edited in the branch files.

Now I'm looking at the system prompts to understand how the LLM agent is configured.blocks → 1-line summaries
    │     removes file reads followed by patches to same file
    │     trims confirmatory bash output (git commit, pip install, etc.)
    │     never trims last 6 messages
    │
    ├─ call_llm(selected, api_key, base_url, model,
    │           _trimmed_messages, DIRECT_TOOL_DEFS, temperature=0.3)
    │     tools=DIRECT_TOOL_DEFS → LLM can emit tool_calls
    │
    ├─ extract_response(raw)              (llm_client.py:79)
    │     parses message.tool_calls into {id, function_name, arguments}
    │     JSON-decodes function.arguments
    │
    └─ if tool_calls:
         for each tool_call:
             yield sse_event("tool_call", {name, args})
             execute_tool(name, args, project_dir=project_path)
               ├─ Built-in tools: bash, git_status, git_diff, git_log,
               │                   git_commit, memory_save, memory_load,
               │                   memory_list, http_check, restart_branch,
               │                   test_agent
               │   (pipeline.py:304-425)
               │
               ├─ Standard tools: list_files, read_file, edit_file,
               │                   patch_file, read_file_tail, read_lines,
               │                   grep_code, read_project
               │   (tools.py:245-360 via execute_tool at tools.py:235)
               │
               └─ For platform project: edits go to BRANCH_ROOT
                    (file_cache_set writes to branch_cache)

             yield sse_event("tool_result", {name, result})
             messages.append({"role": "tool", "tool_call_id": id, "content": result})

         if any non-readonly tool called:
             action_turns += 1

       else (no tool_calls → plain text response):
         yield sse_event("response", {"content": text})
         _last_response_text = text
         break  → exit coding loop
```

### 1.6 Test Phase (`pipeline.py:398-470`)

```
yield sse_event("phase", {"phase": "testing"})

test_agent.handle_test_agent(args={
    "scope": "auto",
    "context": "…",
    "project_dir": project_dir,
    "phase": "full",
    "fix_loop": True,
})
  → test_agent.py:plan_tests()           (Phase 1: LLM generates test plan)
  → test_agent.py:run_tests(plan)       (Phase 2: httpx API + Playwright browser)
  → if failures && _test_fix_iteration < MAX_TEST_FIX_ITERATIONS (2):
        _test_fix_iteration += 1
        yield sse_event("test_feedback", {failed, iteration})
        send failures back as user message → loop to next LLM call
        (test_agent.py:run_test_and_fix_loop → send_to_chat_pipeline)

For each test iteration:
    yield sse_event("test_phase", {status, iteration, test_count, passed, failed})
    collect _test_evidence.append({iteration, passed, failed, details})

After all tests:
    yield sse_event("phase", {"phase": "post_test"})
    → if _made_code_changes:
         systemctl --user restart aelidirect-branch.service
         (branch server restarts with edited files)
```

### 1.7 TD Review Phase (`pipeline.py:475-535`)

```
yield sse_event("td_review", {"status": "running"})

_build review input: original task, plan, code changes, final response,
                    test_evidence summary

call_llm(selected, api_key, base_url, model,
         [{"role": "system", "content": TODO_TD_REVIEW_PROMPT},
          {"role": "user",  blocks and hallucinated [TOOL_CALL] blocks from output

yield sse_event("td_review", {
    "status": "complete",
    "review": td_review_text,
})
```

### 1.8 Completion (`pipeline.py:538-560`)

```
yield sse_event("done", {
    turns, action_turns, test_evidence, td_review,
})
│
├─ _save_conversation(project_dir, msg, messages, test_evidence)
│     (history.py:27 — writes CONVERSATIONS_DIR/{project_dir}/{ts}.json)
│
├─ loop.create_task(_regenerate_docs())
│     (docs.py:77 — regenerates SPEC.md, CONTEXT_MAP.md,
│      DATA_FLOW.md, SITE_MAP.md in parallel)
│
└─ if branch editing + made code changes + no test phase ran:
      systemctl --user restart aelidirect-branch.service
```

---

## 2. Tool Call Loop

```
LLM call (with DIRECT_TOOL_DEFS)
  │
  ├─ LLM returns tool_calls[]
  │    └─ each tool_call: {id, function: {name, arguments}}
  │
  ├─ extract_response() parses arguments as JSON  (llm_client.py:79-114)
  │    repairs malformed JSON (unterminated strings, trailing commas)
  │
  └─ For each tool_call:
       │
       ├─ Built-in tools handled in pipeline.py:304-425:
       │    bash              → subprocess.run() with 60s timeout
       │    git_status        → git status (inits repo if needed)
       │    git_diff          → git diff (max 5000 chars)
       │    git_log           → git log --oneline
       │    git_commit        → git add . && git commit
       │    memory_save       → MEMORY_DIR/{project}/{key}.md
       │    memory_load       → read from MEMORY_DIR/{project}/{key}.md
       │    memory_list       → list MEMORY_DIR/{project}/ *.md
       │    http_check        → http_get(port, path) on pod
       │    restart_branch    → systemctl restart aelidirect-branch.service
       │    test_agent        → test_agent.handle_test_agent(args)
       │
       └─ Standard tools via execute_tool()  (tools.py:225-244):
            │
            ├─ list_files    → iterate project_path, skip hidden files
            ├─ read_file     → file_cache_get/set (with mtime invalidation)
            │                  truncate at READ_FILE_TRUNCATE (16000)
            ├─ edit_file     → write + update cache
            ├─ patch_file    → find old_text, replace with new_text
            │                  exact match required; helpful error if not found
            ├─ read_file_tail→ last N lines with line numbers + truncation warnings
            ├─ read_lines    → range read with ±20 line padding
            ├─ grep_code     → case-insensitive rglob search across all files
            └─ read_project  → if total_size <= READ_PROJECT_BUDGET (100k):
                                   return all files concatenated
                               else: return file listing + sizes

       SSE events emitted:
         tool_call   → frontend displays tool name
         tool_result → frontend shows result (truncated to 2000)
       
       messages.append({"role": "tool", "tool_call_id": id, "content": result})
       
       → Next iteration of while loop: call_llm again with updated messages
```

**Loop termination**: LLM returns a plain text response (no `tool_calls` in message) → coding loop exits.

---

## 3. Memory System

### 3.1 Long-Term Memory (explicit, key-value)

```
memory_save(key, content):
    MEMORY_DIR / {project_name} / {key}.md
    └─ created by LLM calling memory_save tool
    └─ written by pipeline.py:390-392

memory_load(key):
    read MEMORY_DIR / {project_name} / {key}.md
    └─ returned to LLM as tool result

memory_list(key):
    list all *.md in MEMORY_DIR / {project_name}
    └─ returned to LLM as tool result

Loaded into system prompt at pipeline.py:214-220:
    for f in sorted(mem_dir.glob("*.md")):
        memories.append(f"[{f.stem}]: {f.read_text()[:500]}")
    system_prompt += "\n\n[LONG-TERM MEMORY]\n" + "\n".join(memories)
```

### 3.2 Short-Term Conversation History

```
_load_conversation_history(project_name, prov, selected)  (history.py:47)
  │
  ├─ list all CONVERSATIONS_DIR/{project_name}/*.json
  ├─ delete files beyond CONVERSATION_HISTORY_LIMIT (50)
  ├─ load last 5 JSON files
  ├─ each conversation:
  │    if llm_summary exists → use it
  │    else → convert messages to readable text (first 300 chars per response)
  └─ return concatenated text, capped at 40,000 chars

Loaded into system prompt at pipeline.py:225-231:
    system_prompt += "\n\n[RECENT CONVERSATION HISTORY]\n" + conv_history
```

### 3.3 Save After Each Conversation

```
_save_conversation(project_name, user_message, messages, test_evidence)
    (history.py:27)
  │
  ├─ CONVERSATIONS_DIR / {project_name} / {ts}.json
  │    format: {timestamp, user_message, messages: [...], llm_summary: null, test_evidence}
  │    strips system messages, normalizes tool_calls to string summaries
  │
  └─ Called after every chat completion (pipeline.py:542)
```

### 3.4 Auto-Summarization

```
_summarize_old_conversations()  (history.py:87)
  triggered by: GET /api/direct/history/{project_dir}
  │
  ├─ finds conversations older than last 10 without llm_summary
  ├─ batches up to 10 at a time (SUMMARIZE_BATCH_SIZE)
  ├─ calls call_llm with summarization prompt
  │    → each summary: bugs found, fixes applied, features, deploy/test results
  ├─ writes llm_summary field back to each JSON file
  └─ future _load_conversation_history reads use the summary instead of full messages
```

---

## 4. Heartbeat / Todo Execution Flow

```
_heartbeat_scheduler()  (heartbeat.py:79)
  └─ infinite loop, sleeps 30s between checks
       │
       ├─ for each HEARTBEATS_DIR/*.json heartbeat config:
       │    ├─ skip if not enabled or already running
       │    ├─ check interval vs last_run timestamp
       │    ├─ get_pending_todos(project_dir)
       │    │    → reads TODOS_DIR/{project}.json
       │    │    → filters by status IN ("pending", "attempted")
       │    │    └─ returns first item (queue order)
       │    │
       │    └─ if pending todos exist:
       │         hb["running"] = True; save_heartbeat()
       │         await _execute_todo_via_chat(project_dir, pending[0])
       │         hb["running"] = False; hb["last_run"] = now; save_heartbeat()
       │
       └─ on any error: reset running flag, continue
```

### 4.1 `_execute_todo_via_chat` (heartbeat.py:23)

```
Entrypoint: POST /api/direct/heartbeat/{project_dir}/run
            (also called by _heartbeat_scheduler)

Step 1: POST http://127.0.0.1:{PROD_PORT}/api/direct/start
        {message: task, project_dir: project_dir}
        → returns stream_url

Step 2: SSE stream consumer (same event types as browser EventSource)
        async with client.stream("GET", f"/api/direct/stream?…") as stream:
            for each SSE event:
                event_type = line starting "event: "
                event_data = line starting "data: "

                turn          → update _heartbeat_progress["turn"]
                tool_call     → update _heartbeat_progress["step"], total_steps++
                tool_result   → update _heartbeat_progress["step"]
                thinking      → update _heartbeat_progress["step"]
                test_phase    → update _heartbeat_progress["step"]
                td_review     → update _heartbeat_progress["step"]
                response      → capture result_text
                done          → break
                error         → raise Exception

Step 3: On completion:
        _classify_result(result_text)  → "success" | "partial" | "failure"
        _heartbeat_progress.update({
            active=False, step="done",
            result_status: rs, result_message: result_text[:200],
            finished_at: now,
        })
        update_direct_todo(project_dir, todo_id, "done", result_text)
        record_heartbeat_run(project_dir, todo_id, task, result_text)
        → writes to HEARTBEATS_DIR/{project}.json
        → updates TODOS_DIR/{project}.json
```

### 4.2 Todo State Machine

```
add_todo(project_name, task, category)
  → TODOS_DIR/{project}.json
  → status="pending", created_at=now, attempts=0

update_direct_todo(project_name, todo_id, status, result="")
  "attempted" → started_at set, attempts++
  "done"      → completed_at, duration_secs computed from started_at

statuses: "pending" → "attempted" → "done" | deleted
```

### 4.3 Heartbeat Config

```
get_heartbeat / save_heartbeat(project_name, hb)
  → HEARTBEATS_DIR/{project}.json
  → fields: enabled, interval_minutes, last_run, running, history[]

record_heartbeat_run(project_name, todo_id, task, result)
  → appends to hb["history"], keeps last 50 entries
```

---

## 5. Deployment Flow (Pod Management)

```
spin_up_pod(project_dir, project_name, host_port, version)
    (pod.py:148)
  │
  ├─ Phase 1: DESTROY  (pod.py:166)
  │    _force_destroy_pod(pod_name)
  │    waits up to 20s for port to be released
  │    if still occupied → _kill_pod_on_port(port)
  │
  ├─ Phase 2: BUILD  (pod.py:175)
  │    detect_app_type(project_dir) → "fastapi" | "flask" | "static" | "python-http"
  │    generate_containerfile() → writes Containerfile to project_dir
  │    podman build -t {image_name} -f Containerfile {project_dir}
  │    timeout: 120s
  │
  ├─ Phase 3: START  (pod.py:181)
  │    podman pod create --name {pod_name} -p {host_port}:{INTERNAL_PORT}
  │    podman run -d --pod {pod_name} --name {pod_name}-app {image_name}
  │    timeout: 60s
  │
  └─ Phase 4: HEALTH CHECK  (pod.py:191)
       health_check(port, path="/health", retries=15, delay=2.0)
       → urllib.request.urlopen until HTTP 200
       → returns success + body preview, or failure + last_error

Returns: {success, pod_name, port, version, message, logs, phase}
         phase indicates which phase failed
```

### 5.1 Port Allocation

```
get_available_port(project_name)  (pod.py:59)
  ├─ load .ports.json (JSON file mapping name → port)
  ├─ check podman pod ls for used ports
  ├─ check OS socket with _is_port_free() (socket.bind test)
  ├─ scan POD_PORT_RANGE (11001-11099)
  ├─ assign first free port
  └─ save to .ports.json
```

### 5.2 App Type Detection

```
detect_app_type(project_dir)  (pod.py:93)
  ├─ check .py files for "FastAPI" or "flask" string
  ├─ check for index.html → "static"
  └─ default → "python-http"
```

### 5.3 Containerfile Generation

```
generate_containerfile(project_dir, app_type, port=8000)
  ├─ fastapi: pip install fastapi uvicorn; CMD uvicorn {main}:app
  ├─ flask:   pip install flask; CMD flask --app {main} run
  ├─ static:  python3 -m http.server {port}
  └─ base image: python:3.13-slim
```

---

## 6. Config and State Management

### 6.1 Global Config (`state.py`)

```
config (global dict)
  ├─ "selected"         → provider name, e.g. "openrouter"
  ├─ "providers": {name: {api_key, base_url, model, enabled}}
  └─ persisted to .config.json via load_config() / save_config()

_load_config()  → reads .config.json on startup (app.py:__init__)
_save_config()  → writes .config.json on provider add/update
```

### 6.2 Provider Resolution

```
_get_provider()  (state.py)
  → returns config["providers"][config["selected"]]
  → api_key, base_url, model used by every LLM call
```

### 6.3 Direct State (`_direct_state`)

```
_direct_state = {
    "project_dir": None,     # set by create_or_select_project and run_chat_pipeline
    "project_name": None,   # set by create_or_select_project
    "port": None,           # pod port for this project
}
  └─ used by built-in tools (bash, git_*, memory_*, http_check, restart_branch)
     to know which project context to operate in
```

### 6.4 File Caches (`tools.py:36-68`)

```
_file_cache_main   {(resolved_project, rel_path) → content}
_file_cache_branch {(resolved_project, rel_path) → content}
_file_cache_mtime  {(resolved_project, rel_path) → disk_mtime}

file_cache_get(project, path):
    if _is_platform_project(project):
        return _file_cache_branch[key]
    return _file_cache_main[key]

file_cache_set(project, path, content):
    if _is_platform_project(project):
        _file_cache_branch[key] = content
    else:
        _file_cache_main[key] = content

read_file tool: checks mtime → returns cached content if unchanged
patch_file tool: writes file + updates cache
```

### 6.5 Pod Agent State (`pod.py`)

```
_agent_state = {
    "project_dir": None,
    "project_name": None,
    "session_id": None,
    "host_port": None,
}
  └─ set by set_agent_state() for Diagnostics agent tool execution
```

### 6.6 Heartbeat Progress

```
_heartbeat_progress = {
    "active": False,
    "project": "",
    "todo_id": "",
    "task": "",
    "step": "",
    "turn": 0,
    "max_turns": 150,
    "total_steps": 0,
    "started_at": "",
    "finished_at": "",
    "result_status": "",
    "result_message": "",
}
  └─ updated every SSE event in _execute_todo_via_chat
  └─ read by GET /api/platform/heartbeat-progress
  └─ displayed in frontend branch bar
```

---

## 7. Branch / Prod Sync Flow

### 7.1 Architecture Overview

```
PROD_ROOT  = /home/aeli/projects/aelidirect/          (port 10100)
BRANCH_ROOT = /home/aeli/projects/aelidirect_branch/  (port 10101)

Dual caches in tools.py:
  _file_cache_main   ← prod files (source of truth)
  _file_cache_branch ← LLM edits diverge from prod

File cache operations:
  file_cache_wipe_branch()     → copy main → branch (on wipe)
  file_cache_deploy_to_main()  → copy branch → main (on deploy)
```

### 7.2 Pre-Session Auto-Wipe (`pipeline.py:175-185`)

```
On every /api/direct/stream request for aelidirect_platform:

if BRANCH_ROOT exists:
    for rel in PLATFORM_SOURCE_FILES:
        compare MD5 hashes: prod_file vs branch_file
        if branch_file mtime > prod_file mtime AND hash differs:
            branch_has_newer = True; break

if not branch_has_newer:
    for rel in PLATFORM_SOURCE_FILES:
        shutil.copy2(prod_file, branch_file)   # prod → branch
    file_cache_wipe_branch()                   # sync cache
    INFO log: "[platform] Auto-wiped branch from prod"

project_path = BRANCH_ROOT  # agent edits go to branch
```

### 7.3 During Session (Agent Edits Branch Files)

```
LLM calls edit_file/patch_file on platform project
  → tools.py: execute_tool()
  → tools.py: file_cache_set() → writes to _file_cache_branch
  → tools.py: _tool_edit_file() / _tool_patch_file()
      → actual file write to BRANCH_ROOT/{path}

Frontend polls GET /api/platform/branch-status every 30s:
  → compares MD5 hashes of PLATFORM_SOURCE_FILES
  → if branch newer: shows "Ready to test" bar with changed file names
```

### 7.4 Branch Wipe (`platform_routes.py:26` — `wipe_branch`)

```
POST /api/platform/branch-wipe
  ├─ Blocked if _heartbeat_progress["active"] and project == "aelidirect_platform"
  │    (agent is actively editing branch files)
  │
  ├─ 1. Source files: shutil.copy2 prod → branch
  │        for rel in PLATFORM_SOURCE_FILES
  │
  ├─ 2. Data directories: shutil.copytree with symlinks preserved
  │        for rel in PLATFORM_DATA_DIRS
  │        (conversations, todos, heartbeats, memory, reports, projects/)
  │
  ├─ 3. Data files: shutil.copy2 prod → branch
  │        for rel in PLATFORM_DATA_FILES
  │        (.config.json, .ports.json, SPEC.md, CONTEXT_MAP.md, DATA_FLOW.md)
  │
  ├─ file_cache_wipe_branch()  (tools.py:67)
  │        clears branch cache, copies main → branch
  │
  └─ systemctl --user restart aelidirect-branch.service
        branch server restarts, reloads files from disk
```

### 7.5 Branch Deploy (`platform_routes.py:72` — `deploy_branch`)

```
POST /api/platform/branch-deploy
  ├─ Blocked if _heartbeat_progress["active"]
  ├─ Blocked if get_heartbeat("aelidirect_platform")["running"]
  │
  ├─ for rel in PLATFORM_SOURCE_FILES:
  │    shutil.copy2(branch_file, prod_file)  # branch → prod
  │
  ├─ file_cache_deploy_to_main()  (tools.py:72)
  │        copies branch cache entries → main cache
  │        (only platform-related entries)
  │
  └─ systemctl --user restart aelidirect.service
        prod server restarts, picks up new source files

After restart: new code is live on port 10100 (prod)
```

### 7.6 Test Phase Restart (`pipeline.py:467-472`)

```
In the test phase, after running automated tests:
  if _made_code_changes and _test_fix_iteration == 0:
      systemctl --user restart aelidirect-branch.service

  → restarts branch so it loads the edited files
  → tests then run against the updated branch server
```

### 7.7 Sync State Machine

```
prod (10100)        branch (10101)        agent
    │                    │                  │
    ├─ auto-wipe ────────►│                  │  (at session start, if branch not newer)
    │                    │                  │
    │                    │◄─── edits ────────┤  (during coding loop)
    │                    │                  │
    │◄─── deploy ────────│                  │  (manual trigger in UI)
    │                    │                  │
    └─ restart ──────────┘                  │  (after deploy or test phase)
    │                    │                  │
```
```
</think>

```markdown
# aelidirect -- Data Flow

## 1. Main Chat Flow

```
User sends message
  → /api/direct/start (pipeline.py:157)
    validates project_dir, sets active project
    returns stream_url pointing to /api/direct/stream
  → /api/direct/stream (pipeline.py:162)
    StreamingResponse with text/event-stream media type
```

### 1.1 Request Initiation (`pipeline.py:157` — `create_or_select_project`)

```
POST /api/direct/start
  data = {message, project_dir?, project_name?}
  │
  ├─ project_dir provided?
  │    YES → read project_env.md from PROJECTS_ROOT/project_dir
  │    NO  → derive safe_name from message, call init_project_dir()
  │           write project_env.md with project_name
  │
  └─ set_active_project(project_path)  (tools.py:89)
     _direct_state["project_dir"]  = project_path
     _direct_state["project_name"] = project_name
     _direct_state["port"]         = port
     └─ returns {project_dir, project_name, port, stream_url}
        stream_url = /api/direct/stream?message=…&project_dir=…
```

### 1.2 SSE Stream Start (`pipeline.py:162` — `run_chat_pipeline` / `event_generator`)

```
GET /api/direct/stream
  prov = _get_provider()                    (state.py)
  selected = config["selected"]              (state.py)
  │
  ├─ Platform self-editing check:
  │    if project_dir == "aelidirect_platform" and BRANCH_ROOT exists:
  │        compare MD5 hashes of PLATFORM_SOURCE_FILES
  │        if branch not newer than prod:
  │            auto-wipe: shutil.copy2 prod → branch  (pipeline.py:175-185)
  │            file_cache_wipe_branch()               (tools.py:67)
  │        project_path = BRANCH_ROOT  (agent edits branch files)
  │
  └─ event_generator() async generator starts yielding SSE events
```

### 1.3 System Prompt Assembly (`pipeline.py:195-240`)

```
system_prompt = DIRECT_AGENT_PROMPT  (state.py)
  │
  ├─ [SITE_MAP]     ← PROD_ROOT / "SITE_MAP.md"      (exists → appended)
  ├─ [SPEC]         ← PROD_ROOT / "SPEC.md"           (exists → appended)
  ├─ [LONG-TERM MEMORY]
  │       ← MEMORY_DIR / project_path.name / "*.md"
  │       each memory file's first 500 chars appended
  └─ [RECENT CONVERSATION HISTORY]
          ← _load_conversation_history()  (history.py:47)
          last 5 JSON conversations converted to text
          capped at 40,000 chars

messages = [
  {"role": "system", "content": system_prompt},
  {"role": "user",   "content": msg},
]
```

### 1.4 Planning Turn (`pipeline.py:244-255`)

```
yield sse_event("phase", {"phase": "planning"})
yield sse_event("turn",  {"turn": 1, "action_turns": 0, "max": MAX_ACTION_TURNS})

call_llm(selected, api_key, base_url, model,
         messages, tools=None, temperature=0.3)
  → LLM returns TEXT ONLY (no tools)
  → _plan_text = parsed["content"]

yield sse_event("thinking", {"content": _plan_text})
messages.append({"role": "assistant", "content": _plan_text})
messages.append({"role": "user", "content": "Good plan. Execute it now."})
```

### 1.5 Coding Loop — Agent Turns (`pipeline.py:258-395`)

```
yield sse_event("phase", {"phase": "coding"})

while action_turns < MAX_ACTION_TURNS (150):
    │
    ├─ yield sse_event("turn", {"turn": N, "action_turns": M, "max": 150})
    │
    ├─ _trim_messages(messages)           (pipeline.py:45-149)
    │     strips "content": review_input}],
         tools=None, temperature=0.3)
  → strip