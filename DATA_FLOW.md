<think>
The user wants me to produce a DATA_FLOW.md document tracing the data flow through the aelidirect system based on the provided source code. Let me analyze the code carefully and trace each flow.

Let me go through each of the 7 areas:

1. **Main chat flow (user message → SSE stream → agent loop → response)**
2. **Tool call loop (LLM response → tool execution → result → next LLM call)**
3. **Memory system (long-term save/load, short-term conversation history)**
4. **Heartbeat/todo execution flow**
5. **Deployment flow (pod management)**
6. **Config and state management**


7. **Branch/prod sync flow**

Now I'm mapping out the key files and entry points. The main FastAPI application runs on port 10100, with the chat streaming handled through `/api/chat/stream`, the SSE event formatting utility, and the core agent loop that orchestrates the LLM interactions. The tools module contains the file caching system and dual-cache strategy for handling both main and branch platform projects.

Now I'm looking at the remaining components: the direct todo and heartbeat system for scheduling and tracking tasks, the LLM client that wraps the API calls with retry logic and response parsing, and the pod management system for spinning up containers. The frontend appears to be a single-page application built with vanilla JavaScript and CSS.

Starting to trace through the main chat flow, I need to identify where the user message originates from the frontend and how it flows through the backend.

The user submits a message through an HTML form which triggers the `sendMessage()` function, which then calls `/api/chat/stream` as a streaming request. The backend endpoint extracts the project information, conversation history, and context before invoking the `_direct_agent_loop()` function to process the message.

Inside `_direct_agent_loop()`, the system first sends an initial SSE phase event, then loads any conversation history from memory and appends the user's new message to the conversation history. It constructs the system prompt and conversation messages before entering the main agent loop that processes the response.

Now I'm tracing through the tool execution flow—the LLM returns either text or a tool call, and if it's a tool call, the system executes it via `execute_tool()`, appends the result back to the conversation, and loops again until the LLM produces a final text response, which gets streamed back to the client via SSE events.

Then there's the memory system layered in—short-term conversation history gets loaded and saved per project, with automatic summarization when the token budget is exceeded, while long-term memory uses dedicated tools that let the agent save and retrieve information across sessions. There's also a file caching layer for the platform project itself.

Now looking at the heartbeat system, it runs as a background task that periodically checks for pending todos and executes them in sequence. The heartbeat state gets persisted to disk and monitored across server restarts, and there's TD review logic that evaluates todo execution results.

For the deployment flow, when the agent triggers a pod spin-up, it goes through port allocation, container image building, pod creation, and health checks before returning the result.

Config and state management uses JSON files for persistent settings, while branch and production sync maintain separate file caches that get synchronized through explicit API calls.

Now I'm mapping out the data flow through the platform's core endpoints and helper functions.

Tracing through the frontend JavaScript to understand how messages are sent and received via the streaming API, and how the conversation state is maintained across interactions.

Now I'm examining the file caching system that sits between the agent and the filesystem, which handles both main and branch versions of files separately.

I'm also looking at the heartbeat scheduler, which periodically checks for pending todos and executes them by calling into the agent loop through a task queue.

For the todo execution itself, the system passes the task as a user message and lets the agent handle it, while a separate TD review process runs asynchronously to provide feedback on the agent's work.

The pod deployment follows a predictable path: it detects the app type, generates a containerfile, builds the image, creates the pod, and runs a health check before returning the result to the agent.

I'm also tracking the state management through various context objects that maintain the agent's project, conversation history, heartbeat status, and platform-specific information like which port the branch is running on.

Now I'm mapping out the remaining state files and their purposes—port allocations, conversation history, long-term memory stores, TD reports, and platform sync tracking between production and branch environments. The branch/prod sync flows through three main endpoints that handle status checking, deployment, and cache synchronization.
</think>

# aelidirect -- Data Flow

## 1. Main Chat Flow

**Entry: `frontend/index.html` → `sendMessage()`**
```
User types message → textarea → "Send" button clicked
  → sendMessage() [index.html ~line 750]
    → messages.push({role:"user", content})
    → renderMessages()
    → fetch('/api/chat/stream', {method:"POST", body: JSON.stringify({message, project_name}), headers: {Content-Type:..., Accept:"text/event-stream"}})
```

**Step 1 — Backend receives stream request: `POST /api/chat/stream`**
```
@app.post("/api/chat/stream")           [main.py:line ~360]
  → project_name = body.get("project_name")
  → project_dir  = PROJECTS_ROOT / project_name
  → history      = _load_conversation_history(project_name)   [memory system]
  → return StreamingResponse(_stream_chat(...), media_type="text/event-stream")
```

**Step 2 — `_stream_chat()` generator starts**
```
_stream_chat(project_name, user_message)   [main.py:line ~290]
  → _direct_state["project_dir"]   = project_dir
  → _direct_state["project_name"]  = project_name
  → session_id = project_name
  → set_active_project(project_dir)   [tools.py:file_cache]
  → set_agent_state(project_dir, session_id, port, project_name)  [pod.py]
  → yield sse_event("phase", {"phase": "thinking", ...})
  → yield sse_event("turn", {"turn": 1, "max_turns": 15, "step": "loading history"})
```

**Step 3 — History is loaded and message is appended**
```
→ messages = [{"role":"system","content":DIRECT_AGENT_PROMPT}, ...prior...]
→ messages.append({"role":"user","content":user_message})
→ if history: messages.insert(1, {"role":"system","content":f"CONVERSATION HISTORY:\n{history}"})
```

**Step 4 — Agent loop begins**
```
→ for turn 1..max_turns (15):
    → sse_event("turn", {"turn": t, "max_turns": 15, "step": "calling LLM"})
    → prov = _get_provider()
    → result = call_llm(selected, api_key, base_url, model, messages, TOOL_DEFINITIONS)  [llm_client.py:35]
    → parsed = extract_response(result)    [llm_client.py:88]
```

**Step 5 — LLM response parsed and SSE-ed**
```
→ if parsed["type"] == "text":
    → yield sse_event("message", {"content": text, "done": True})
    → _save_conversation(project_name, user_message, messages)
    → yield sse_event("done", {})
    → break
```

**Step 6 — Frontend EventSource receives SSE events**
```
→ source = new EventSource('/api/chat/stream?...')
→ source.addEventListener('phase', e => {...})   [index.html ~line 800]
→ source.addEventListener('message', e => { render assistant bubble })
→ source.addEventListener('turn', e => { update turn counter })
→ source.addEventListener('done', e => { hide spinner; scrollBottom() })
```

---

## 2. Tool Call Loop

**LLM decides to call a tool → `parsed["type"] == "tool_call"`**

**Step 1 — Tool calls extracted from LLM response**
```python
# main.py line ~330
tool_calls = parsed["tool_calls"]  # list of {id, function_name, arguments}
```

**Step 2 — Each tool call is executed in sequence**
```python
for tc in tool_calls:
    name = tc["function_name"]
    args = tc["arguments"]
    
    # Read-only check (no turn cost)
    if _is_readonly_tool_call(tc):
        result = execute_tool(name, args, project_dir)  [tools.py:200]
    else:
        # Send tool call event to frontend
        yield sse_event("tool_call", {"name": name, "args": args})
        # Execute
        result = execute_tool(name, args, project_dir)  [tools.py:200]
        # Send result
        yield sse_event("tool_result", {"name": name, "result": result[:5000]})
```

**Step 3 — Tool result appended to messages for next LLM call**
```python
# main.py line ~345
messages.append({
    "role": "assistant",
    "content": parsed.get("content", "") or "",
    "tool_calls": [
        {"id": tc["id"], "function": {"name": tc["function_name"], "arguments": json.dumps(tc["arguments"])}}
        for tc in tool_calls
    ]
})
messages.append({
    "role": "tool",
    "tool_call_id": tool_calls[0]["id"],   # only first (loop over tools below)
    "name": tool_name,
    "content": result,
})
```

**Wait — the code actually appends each tool result separately. Corrected:**
```python
for tc in tool_calls:
    result = execute_tool(name, args, project_dir)
    messages.append({"role": "tool", "tool_call_id": tc["id"], "name": name, "content": result})
    # Then call LLM again with accumulated messages
```

**Step 4 — LLM called again with tool result, loop continues**
```python
# back to top of for loop → call_llm again → extract_response
# LLM may return: more tools, or final text
```

**Key file functions:**
| Tool | Executor | File | Lines |
|------|----------|------|-------|
| `read_file` | `_tool_read_file` | `tools.py` | 265–282 |
| `patch_file` | `_tool_patch_file` | `tools.py` | 290–340 |
| `edit_file` | `_tool_edit_file` | `tools.py` | 258–263 |
| `grep_code` | `_tool_grep_code` | `tools.py` | 358–374 |
| `read_project` | `_tool_read_project` | `tools.py` | 377–420 |
| `deploy_pod` | (defined in main.py, calls `spin_up_pod`) | `main.py` | ~510 |

**File cache hit path (read_file for platform project):**
```
_tool_read_file(project, path)
  → file_cache_get(project, path)   [tools.py:83] — checks branch cache for platform
  → if cache hit AND mtime matches: return cached content
  → else: read from disk → file_cache_set → return
```

---

## 3. Memory System

### Short-Term Memory (Conversation History)

**Save flow:**
```python
_save_conversation(project_name, user_message, messages)  [main.py:line ~175]
  → conv_dir = _DIRECT_CONVERSATIONS_DIR / project_name   # .direct_conversations/{project}/
  → full_messages = []  (strip system, keep user/assistant/tool)
  → for each tool_call: format as "function_name(args)"
  → write JSON: {timestamp, user_message, messages, llm_summary: None}
  → file: {conv_dir}/{YYYY-MM-DDTHH-MM-SS}.json
```

**Load flow:**
```python
_load_conversation_history(project_name)   [main.py:line ~190]
  → conv_dir = _DIRECT_CONVERSATIONS_DIR / project_name
  → glob("*.json") → sort → keep last _CONVERSATION_HISTORY_LIMIT (50)
  → _conv_to_text(conv): 
      if llm_summary → "[timestamp] {summary}"
      else: "[timestamp] User: {msg}\n  Assistant: {content}\n  Tools: {tools}"
  → total_text = join all conversations with "\n\n"
  → if total_tokens > _CONVERSATION_TOKEN_BUDGET (50k):
      → _summarize_old_conversations(conversations, prov, selected)  [main.py:line ~210]
      → saves summaries back to conv["llm_summary"]
  → return total_text (inserted as system message at index 1)
```

**Summarization flow:**
```python
_summarize_old_conversations(conversations, prov, selected)  [main.py:line ~210]
  → unsummarized = conversations[:-10] without llm_summary
  → batch_text = concatenate last 10 conversations
  → call_llm(provider, summarization_prompt, temperature=0.2)
  → for each conv: conv["llm_summary"] = parsed summary line
  → write summaries back to JSON files
```

### Long-Term Memory (Persistent Key-Value Store)

**Storage location:** `_DIRECT_MEMORY_DIR / {project_name} / {key}.md`
```python
_MEMORY_DIR = Path(__file__).parent / ".direct_memory"   [main.py:line ~120]
```

**`memory_save(key, content)` tool:**
```python
# Defined in TOOL_DEFINITIONS (main.py, tools list)
# Executor: _tool_memory_save in main.py (not shown in excerpt but in TOOL_DEFINITIONS)
→ memory_dir = _DIRECT_MEMORY_DIR / project_name
→ (memory_dir / "{key}.md").write_text(content)
```

**`memory_load(key)` tool:**
```python
→ memory_dir = _DIRECT_MEMORY_DIR / project_name
→ return (memory_dir / "{key}.md").read_text()
```

**`memory_list()` tool:**
```python
→ memory_dir = _DIRECT_MEMORY_DIR / project_name
→ return "\n".join(f.name for f in memory_dir.glob("*.md"))
```

**Memory auto-loaded at conversation start:** The `DIRECT_AGENT_PROMPT` at line ~95 tells the LLM that long-term memory is loaded automatically, but the actual loading is done by `memory_load` being called as a tool by the LLM itself at conversation start (or the results are pre-inserted as system context — the prompt says "shown below if any exist").

### Memory Endpoints

| Endpoint | Handler | Line | Purpose |
|----------|---------|------|---------|
| `GET /api/memory/{project}` | `get_memory()` | ~620 | List memory keys |
| `GET /api/memory/{project}/{key}` | `get_memory()` | ~620 | Load specific memory |
| `POST /api/memory/{project}/{key}` | `save_memory()` | ~635 | Save memory key-value |
| `DELETE /api/memory/{project}/{key}` | `delete_memory()` | ~650 | Delete memory key |

---

## 4. Heartbeat / Todo Execution Flow

### Todo State Machine

```
add_todo(project_name, task)           [direct_todo.py:30]
  → uuid[:8] → status: "pending"
  → _save_todos(project_name, todos) → TODO_DIR/{project}.json

update_todo(..., status="attempted")    [direct_todo.py:60]
  → sets started_at, increments attempts, saves last_result

update_todo(..., status="done")         [direct_todo.py:60]
  → sets completed_at, duration_secs, result_status
```

### Heartbeat Scheduler

**Startup registration:**
```python
@app.on_event("startup")               [main.py:line ~700]
  → asyncio.create_task(_heartbeat_scheduler())
  → Clear stuck "running" flags from previous server process
```

**Main scheduler loop:**
```python
_heartbeat_scheduler()                  [main.py:line ~670]
  → while True:
      → for each hb_file in HEARTBEAT_DIR.glob("*.json"):
          → hb = json.loads(read)
          → if not hb["enabled"]: continue
          → if hb["running"]: continue  # skip if already running
          → Compute next_run from interval_minutes
          → if now >= next_run:
              → pending = get_pending_todos(project_name)
              → if pending:
                  → hb["running"] = True
                  → save_heartbeat(project_name, hb)
                  → await _execute_todo_via_chat(project_dir, pending[0])
                  → hb["running"] = False
                  → save_heartbeat(project_name, hb)
      → await asyncio.sleep(60)  # check every minute
```

### Todo Execution via Chat

```python
_execute_todo_via_chat(project_dir, todo)  [main.py:line ~560]
  → _update_heartbeat_progress(project_dir, {"active": True, "todo_id": todo["id"], "task": todo["task"]})
  → update_todo(project_name, todo["id"], "attempted")
  → Build messages:
      system_prompt = DIRECT_AGENT_PROMPT + todo_task_context
      messages = [system, history, user: task]
  → Call LLM in a loop (max_turns=20 for todo execution)
  → Final result = accumulated assistant text
  → update_todo(project_name, todo["id"], "done", result)
  → _update_heartbeat_progress(project_dir, {"active": False, "result_status": ...})
  → _save_conversation(project_name, task, messages)
  → _run_td_review_for_todo(project_dir, todo["id"], task, result)  [async, non-blocking]
```

### TD Review (Technical Director)

```python
_run_td_review_for_todo(project_name, todo_id, task, result)  [main.py:line ~760]
  → call_llm(provider, TODO_TD_REVIEW_PROMPT, temperature=0.3)
  → review_text = parsed["content"]
  → td_status = _parse_td_verdict(review_text)   # extracts STATUS: PASS|PARTIAL|FAIL|INCOMPLETE
  → set_todo_review(project_name, todo_id, review_text, td_status)  [direct_todo.py]
      → updates t["td_review"] and t["result_status"] in TODO file
```

### Heartbeat Progress Tracking (for frontend polling)

```python
_update_heartbeat_progress(project_dir, updates)  [main.py:line ~545]
  → HEARTBEAT_DIR / {project}.json updated with:
      active, project, todo_id, task, step, turn, max_turns, 
      total_steps, started_at, finished_at, result_status, result_message
```

**Frontend polls via:**
```
GET /api/platform/heartbeat-progress     [main.py:line ~560]
  → returns _heartbeat_progress dict
  → polled every 5s by pollHeartbeatProgress() [index.html]
```

---

## 5. Deployment Flow (Pod Management)

**Entry: `deploy_pod(project_name, project_dir, pod_port)` tool called by agent**

**Defined in main.py (not shown in tools.py):**
```python
# TOOL_DEFINITIONS includes deploy_pod with schema
# Executor: _tool_deploy_pod (defined inline in main.py, calls spin_up_pod from pod.py)
```

**Full lifecycle through `spin_up_pod()`:**

```python
spin_up_pod(project_dir, project_name, host_port, version)  [pod.py:line ~130]

Phase 1 — DESTROY:
  → pod_name = _safe_pod_name(project_name)   # "aelimini-{safe_name}"
  → _force_destroy_pod(pod_name)              # podman pod rm -f
  → Wait up to 15s for port to be freed
  → if port still occupied: _kill_pod_on_port(port) → podman pod rm -f

Phase 2 — BUILD:
  → detect_app_type(project_dir)             [pod.py:70] — scans for FastAPI/Flask/static
  → generate_containerfile(project_dir, app_type)  [pod.py:85]
  → podman build -t {image_name} -f Containerfile {project_dir}
  → if failed: return {success: False, phase:"build", message: stderr}

Phase 3 — CREATE POD:
  → podman pod create --name {pod_name} -p {host_port}:8000
  → podman run -d --pod {pod_name} --name {pod_name}-app {image_name}
  → if failed: return {success: False, phase:"start", logs: _get_logs(pod_name)}

Phase 4 — HEALTH CHECK:
  → health_check(host_port, "/health", retries=15, delay=2.0)  [pod.py:155]
      → urllib.request.urlopen(f"http://localhost:{port}/health")
      → polls every 2s, up to 15 attempts (30s total)
  → if HTTP 200: return {success: True, message: "Health OK"}
  → if failed: _get_logs(pod_name), inspect container state
  → return {success: False, phase:"health", logs: ..., message: ...}
```

**Port allocation:**
```python
get_available_port(project_name)        [pod.py:45]
  → Load .ports.json
  → Check podman pod ls for occupied ports
  → Check OS socket with _is_port_free(port)  [pod.py:35]
  → First free port in range 11001–11099 is allocated
  → Saves {project_name: port} to .ports.json
```

**Tool result returned to agent:**
```
"Pod aelimini-{project} running on port {port}\n
Health OK (attempt N): HTTP 200\n
Body preview: {body}"
```

---

## 6. Config and State Management

### Config File

**Location:** `backend/.config.json`

**Load on startup** (lines ~25–40):
```python
CONFIG_FILE = Path(__file__).parent / ".config.json"
# If exists: merge saved providers, selected, pod_host into config dict
```

**Runtime save** (line ~42):
```python
_save_config()  # writes entire config dict back to .config.json
# Called by: /api/config PUT handler
```

### Provider Config

```python
config = {
    "providers": {
        "openrouter": {"name": "OpenRouter", "api_key": "", "base_url": "...", "model": "..."},
        "minimax":    {"name": "MiniMax",    "api_key": "", "base_url": "...", "model": "..."},
    },
    "selected": "minimax",
    "pod_host": "100.92.245.67",
}
```

**API endpoints:**
| Endpoint | Handler | Purpose |
|----------|---------|---------|
| `GET /api/config` | `get_config()` | Return config (masked API keys) |
| `PUT /api/config` | `save_config()` | Update and persist config |

### Runtime State Variables

| Variable | Type | Scope | Purpose |
|----------|------|-------|---------|
| `_direct_state` | dict | per-request via closure | project_dir, project_name, port for current stream |
| `_active_project_dir` | dict | global | Current project for tool execution (legacy path) |
| `TOOL_DEFINITIONS` | list | global | Sent to LLM on every call — available tools |
| `POD_TOOL_DEFINITIONS` | list | global | Tools for Diagnostics agent |
| `_heartbeat_progress` | dict | global | Live progress of current heartbeat run |

### Persistent State Files

| File | Format | Location | Purpose |
|------|--------|----------|---------|
| `.config.json` | JSON | `backend/` | Provider API keys, selected provider, pod_host |
| `.ports.json` | JSON | `backend/` | Project name → port number mapping |
| `{project}.json` | JSON | `backend/.direct_todos/` | Todo list per project |
| `{project}.json` | JSON | `backend/.direct_heartbeats/` | Heartbeat config per project |
| `*.json` | JSON | `backend/.direct_conversations/{project}/` | Conversation history per project |
| `*.md` | Markdown | `backend/.direct_memory/{project}/` | Long-term memory key-value |
| `*.md` | Markdown | `backend/.td_reports/` | TD analysis reports |

### Platform Self-Editing State

**`restart_platform()` flow:**
```python
# Defined in main.py (tool executor)
  → bash('python3 -m py_compile backend/main.py')   # syntax check
  → if platform project: copy files to _BRANCH_ROOT (/home/aeli/projects/aelidirect_branch)
  → bash('systemctl restart aelidirect-branch')   # restart branch server on 10101
  → http_check(10101, "/health")                   # verify branch is up
```

---

## 7. Branch / Prod Sync Flow

### File Cache Architecture

**Two-cache system** (tools.py, lines ~55–80):

```
_file_cache_main     → reflects PROD files (source of truth)
_file_cache_branch   → reflects BRANCH files (agent's edits diverge from prod)
_cache_key = (resolved_project_path, rel_path)
```

**Cache behavior by project type:**
```python
_is_platform_project(project)  [tools.py:62]
  → project.name == "aelidirect_platform" OR
  → project.resolve() == /home/aeli/projects/aelidirect_branch.resolve()

file_cache_get(project, path):
  → if platform: return _file_cache_branch[key]
  → else: return _file_cache_main[key]

file_cache_set(project, path, content):
  → if platform: _file_cache_branch[key] = content
  → else: _file_cache_main[key] = content
```

### Sync Endpoints

**`POST /api/platform/branch-status`** (check what needs syncing):
```
→ Compares file listings in _BRANCH_ROOT vs _PROD_ROOT
→ For each file: compares mtime
→ Returns: {is_branch, has_changes, changes: [{file, mtime_prod, mtime_branch, branch_newer}]}
```

**`POST /api/platform/branch-wipe`** (reset branch to prod):
```
→ for each file in branch listing:
    → read from prod → write to branch
    → update _file_cache_branch to match
→ file_cache_wipe_branch()         [tools.py:line ~77]
    → _file_cache_branch.clear()
    → _file_cache_branch.update(_file_cache_main)
→ Returns: {ok: True, wiped: [list of files], errors: []}
```

**`POST /api/platform/branch-deploy`** (push branch to prod):
```
→ for each changed file in branch:
    → read from branch → write to prod
→ file_cache_deploy_to_main()      [tools.py:line ~79]
    → for key, content in _file_cache_branch:
        → _file_cache_main[key] = content
→ bash('systemctl restart aelidirect')  # restart prod on 10100
→ Returns: {ok: True, deployed: [files], errors: []}
```

**`POST /api/platform/restart-branch`** (restart branch server):
```
→ bash('systemctl restart aelidirect-branch')
→ http_check(10101, "/health")
→ Returns: {ok: True, message: "Branch restarted on port 10101"}
```

### Frontend Sync UI

```
checkBranchStatus()          [index.html ~line 880]
  → GET /api/platform/branch-status
  → shows branch bar if has_changes
  → if branch_newer: shows [Test] [Deploy to Prod] [Wipe Branch]

pollHeartbeatProgress()      [index.html ~line 920]
  → GET /api/platform/heartbeat-progress
  → Overrides branch bar while heartbeat is active (blue spinner)
  → After 8s post-completion: returns to branch status view
```

---

## Summary: All Key Functions and Line Numbers

| Component | Function | File | Line |
|-----------|----------|------|------|
| Chat stream | `POST /api/chat/stream` | `main.py` | ~360 |
| Chat stream | `_stream_chat()` | `main.py` | ~290 |
| Agent loop | `_direct_agent_loop()` | `main.py` | ~310 |
| Tool execution | `execute_tool()` | `tools.py` | ~200 |
| File cache get | `file_cache_get()` | `tools.py` | ~83 |
| File cache set | `file_cache_set()` | `tools.py` | ~88 |
| Pod lifecycle | `spin_up_pod()` | `pod.py` | ~130 |
| Health check | `health_check()` | `pod.py` | ~155 |
| LLM call | `call_llm()` | `llm_client.py` | ~35 |
| LLM parse | `extract_response()` | `llm_client.py` | ~88 |
| Todo add | `add_todo()` | `direct_todo.py` | ~30 |
| Todo update | `update_todo()` | `direct_todo.py` | ~60 |
| Heartbeat scheduler | `_heartbeat_scheduler()` | `main.py` | ~670 |
| Todo execution | `_execute_todo_via_chat()` | `main.py` | ~560 |
| TD review | `_run_td_review_for_todo()` | `main.py` | ~760 |
| Config load | `if CONFIG_FILE.exists()` | `main.py` | ~25 |
| Config save | `_save_config()` | `main.py` | ~42 |
| Branch status | `POST /api/platform/branch-status` | `main.py` | ~580 |
| Branch wipe | `POST /api/platform/branch-wipe` | `main.py` | ~595 |
| Branch deploy | `POST /api/platform/branch-deploy` | `main.py` | ~610 |
| Memory save | `POST /api/memory/{project}/{key}` | `main.py` | ~635 |
| Memory load | `GET /api/memory/{project}/{key}` | `main.py` | ~620 |
| Conv save | `_save_conversation()` | `main.py` | ~175 |
| Conv load | `_load_conversation_history()` | `main.py` | ~190 |
| Conv summarize | `_summarize_old_conversations()` | `main.py` | ~210 |
| Docs regenerate | `_regenerate_docs()` | `main.py` | ~810 |
| TD analysis | `POST /api/td-analysis` | `main.py` | ~820 |
| Frontend send | `sendMessage()` | `index.html` | ~750 |
| Frontend SSE | `EventSource('/api/chat/stream')` | `index.html` | ~800 |
| Heartbeat poll | `pollHeartbeatProgress()` | `index.html` | ~920 |
| Branch status | `checkBranchStatus()` | `index.html` | ~880 |