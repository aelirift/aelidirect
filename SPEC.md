<think>
The user wants me to write a SPEC.md file for the aelidirect project based on the source code provided. Let me analyze the codebase to understand what this project does, how it works, and its features.

Let me go through each file:

1. **backend/pipeline.py** - The core chat pipeline that handles direct mode conversations. It has:
   - A streaming API endpoint `/api/direct/stream`
   - Message trimming to save context window
   - Planning turn (disabled by default)
   - Coding phase with tool execution
   - Test phase with fix loop
   - TD Review phase
   - Branch/prod self-editing for the platform

2. **backend/heartbeat.py** - Todo execution scheduler and heartbeat:
   - `_execute_todo_via_chat()` - executes todos via the chat pipeline
   - `_heartbeat_scheduler()` - periodic scheduler
   - Todo CRUD API routes
   - Heartbeat configuration routes

3. **backend/platform_routes.py** - Branch/prod management:
   - Branch status check
   - Branch wipe (reset to prod)
   - Branch deploy (push to prod)

4. **backend/history.py** - Conversation persistence:
   - Save/load conversations
   - Summarize old conversations

5. **backend/td.py** - TD (Technical Director) review:
   - `run_td_analysis()` - cross-project analysis
   - TD reports storage

6. **backend/docs.py** - Auto-documentation:
   - Regenerates SPEC.md, CONTEXT_MAP.md, DATA_FLOW.md, SITE_MAP.md

7. **backend/tools.py** - LLM tool definitions and executors:
   - File operations (list, read, edit, patch, grep)
   - Project management utilities for creating, renaming, and managing project environments
   - File caching layer for performance optimization

8. **backend/direct_todo.py** - Todo list management:
   - CRUD operations for todos
   - Heartbeat configuration for periodic execution

9. **backend/llm_client.py** - LLM API client:
   - Supports OpenRouter and MiniMax
   - Tool use / function calling

10. **backend/pod.py** - Container management:
    - Podman pod lifecycle (build, run, health check)
    - Port allocation
    - App type detection

11. **backend/test_agent.py** - Automated testing:
    - Phase 1: Plan tests
    - Phase 2: Run tests (API, browser, unit)
    - Fix loop

12. **backend/constants.py** - All shared constants

13. **frontend/index.html** - Single HTML UI with chat, todo, heartbeat, config views, branch testing bar

Now I need to synthesize this into a comprehensive SPEC.md covering the project overview, how it works (the big picture with message flow, agent loop, tool execution), features organized by category, a tech stack table, and how to run it. Let me identify the core components and their interactions to create a clear, specific document.` blocks → 1-line summary; file reads followed by patches → stale; confirmatory bash output → trimmed. Never touches last 6 messages |
| **Action turn counter** | Tracks how many tool-call rounds have run; capped at MAX_ACTION_TURNS (150) |
| **Planning turn** | Disabled by default (model hallucinates tool calls in practice) |

### File Tools
| Tool | Description |
|------|-------------|
| `list_files` | List files/dirs in a subdirectory with sizes |
| `read_file` | Read a file (cached by disk mtime). Large files truncated with last-20-lines preview |
| `edit_file` | Create a new file or fully rewrite an existing file |
| `patch_file` | Targeted edit — find `old_text`, replace with `new_text`. Handles ambiguous or missing matches with diagnostic messages |
| `read_file_tail` | Read the last N lines of a file. Warns about truncation (missing closing tags, mid-statement endings) |
| `read_lines` | Read a specific line range (1-indexed, inclusive). Adds ±20-line padding to reduce follow-up reads |
| `grep_code` | Case-insensitive search across all project files, returns file:line:content |
| `read_project` | Read all source files at once if under budget (100k chars). If over budget, returns a sorted file listing with sizes so the agent can choose specific files |

### System Tools
| Tool | Description |
|------|-------------|
| `bash` | Run shell commands (60s timeout, output truncated to 3k/1k chars for stdout/stderr) |
| `git_status`, `git_diff`, `git_log`, `git_commit` | Git operations scoped to the project directory |
| `http_check` | GET request against the project's running pod |
| `restart_branch` | Restart the branch server via systemctl (for platform self-editing) |

### Memory
| Tool | Description |
|------|-------------|
| `memory_save` | Persist a named note to disk (survives restarts) |
| `memory_load` | Retrieve a named note |
| `memory_list` | List all saved memory keys |
| **Long-term memory** | Files under `backend/.direct_memory/{project_name}/` — prepended to every system prompt |
| **Conversation history** | Last 5 conversations (trimmed to 40k chars) prepended to every system prompt |

### Project Management
| Feature | Description |
|---------|-------------|
| **Auto project creation** | If no project_dir is specified, derives a safe name from the message and creates the directory with `main.py`, `README.md`, and `project_env.md` |
| `project_env.md` | Per-project metadata: name, tech stack, OS, Python version |
| `rename_project` | Update project name in env file |

### Todo & Heartbeat
| Feature | Description |
|---------|-------------|
| **Todo list** | Per-project persistent task list. Fields: task, category (feature/debug/question/refactor), status (pending/attempted/done), attempts, duration_secs, result_status (success/failure/partial), last_result, td_review |
| **Heartbeat scheduler** | Background asyncio loop that runs every 30s, checks heartbeat config, and auto-executes the next pending todo via the same chat pipeline the browser uses |
| **Heartbeat config** | Per-project: enabled flag, interval in minutes, last_run, running flag, history (last 50 runs) |
| **Run Now** | Manually trigger the next pending todo via `/api/direct/heartbeat/{project_dir}/run` |
| **Queue position** | Pending todos show their position in the queue and estimated run time |

### Testing (test_agent.py)
| Feature | Description |
|---------|-------------|
| **Two-phase system** | Phase 1 (Plan): LLM reads all source files in batch, receives scope + context, produces structured JSON test plan. Phase 2 (Run): executes the plan |
| **Test types** | API (httpx), Browser (Playwright with CSS selectors from actual HTML), Unit (Python import + direct function call) |
| **Setup steps** | Every test case includes a `setup` array — API calls that run first to create preconditions (e.g., create a todo, enable heartbeat) |
| **Assertions** | Each test step specifies expected status codes, response field values, DOM text/visibility/count, JS evaluation results, or function return values |
| **Screenshots** | Browser tests can capture screenshots on failure or on demand |
| **Test-fix loop** | On failure: formats failures as a detailed message → sends through chat pipeline → LLM attempts a fix → tests re-run. Loops up to 2 times by default. Context preserved: what failed, what was expected, what the agent's prior attempt was |
| **CLI** | Run directly: `python test_agent.py "heartbeat countdown" --context "..."` |

### Deployment (Pod Management)
| Feature | Description |
|---------|-------------|
| `spin_up_pod()` | Full container lifecycle: destroy old pod → build image → create pod on assigned port → health check (polls until HTTP 200) → return status |
| **App type detection** | Detects FastAPI, Flask, or static site and generates the correct Containerfile + startup command |
| **Port allocation** | Finds free port in range 11001–11099, checks podman + OS socket |
| **Pod naming** | `aelimini-{safe_project_name}` — stable per project, not per session |
| **Health check** | 15 retries × 2s delay against `/health` endpoint |
| **Crash diagnosis** | On health failure, container logs are captured and returned |

### TD Review
| Feature | Description |
|---------|-------------|
| **Post-conversation review** | After every tool-using conversation, a TD review is generated from: original task → agent plan → code changes made → final response → all test evidence |
| **STATUS verdict** | Output includes `STATUS: PASS`, `PARTIAL`, `FAIL`, or `INCOMPLETE` |
| **Verdict classification** | Results classified as success/failure/partial based on keywords |
| **Per-todo display** | TD review text + status badge shown in the todo detail modal |
| **Cross-project analysis** | Separate `/api/td-analysis` endpoint reviews all conversations across all projects, produces a report covering: bugs found, bugs fixed, bugs missed, features built, agent behavior patterns, recommendations |

### Branch/Prod Workflow
| Feature | Description |
|---------|-------------|
| **Auto-wipe on start** | When working on `aelidirect_platform`, the branch directory is wiped from prod before the agent starts (if no testing is in progress) |
| **Branch redirect** | All file tool calls target `BRANCH_ROOT` instead of `PROD_ROOT` for the platform project |
| **Dual file cache** | Separate caches for main and branch; wipe copies main→branch; deploy copies branch→main |
| **Branch status bar** | UI shows whether branch has newer changes, what files changed, and action buttons |
| **Wipe** | Copies prod source + data + config → branch, clears file cache, restarts branch server |
| **Deploy** | Copies branch source → prod, syncs file cache, restarts prod server. Blocked if agent is running |
| **Safety blocks** | Deploy blocked while heartbeat is active or branch is running a task |

### Documentation Auto-Regeneration
| Feature | Description |
|---------|-------------|
| **Triggers** | Runs in background after every chat completion |
| **Outputs** | `SPEC.md`, `CONTEXT_MAP.md`, `DATA_FLOW.md`, `SITE_MAP.md` — all regenerated from current source by the LLM |
| **Parallel generation** | All four docs generated concurrently via asyncio |
| **Source truncation** | Large files truncated to 15k chars top + 15k chars bottom before sending to LLM |

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Runtime** | Python 3.13, FastAPI, Starlette |
| **Frontend** | Single-file HTML/JS (no build step) — CSS variables, SSE via `EventSource`, `fetch` for API calls |
| **Container runtime** | Podman (pods + containers) |
| **LLM providers** | OpenRouter, MiniMax (via REST API, function calling / tool use) |
| **HTTP client** | httpx (async for LLM calls and pod health checks) |
| **Browser automation** | Playwright (for browser-level test cases) |
| **Storage** | JSON files on disk — conversations, todos, heartbeats, memory, TD reports |
| **Process supervision** | systemd (prod + branch servers as user-level services) |
| **File caching** | In-memory dict keyed by `(resolved_project_path, rel_path)` with mtime-based invalidation |

---

## How to Run

### Prerequisites

- Python 3.13
- Podman installed and working
- API key for OpenRouter or MiniMax in `backend/.config.json`
- systemd user services configured (or start servers manually)

### Directory Structure

```
aelidirect/               ← PROD_ROOT (10100)
├── backend/
│   ├── app.py            ← FastAPI app entry point
│   ├── pipeline.py       ← Core chat pipeline + SSE streaming
│   ├── heartbeat.py      ← Todo scheduler + heartbeat executor
│   ├── platform_routes.py← Branch/prod management
│   ├── history.py        ← Conversation persistence
│   ├── td.py             ← TD review + cross-project analysis
│   ├── docs.py           ← Auto-documentation regeneration
│   ├── tools.py          ← LLM tool definitions + executors
│   ├── direct_todo.py    ← Todo + heartbeat data layer
│   ├── llm_client.py     ← OpenRouter / MiniMax API client
│   ├── pod.py            ← Podman pod management
│   ├── test_agent.py     ← Two-phase test planner + executor
│   ├── constants.py      ← All shared constants
│   └── .direct_*         ← Data directories (created at startup)
├── frontend/
│   └── index.html        ← Full standalone UI
├── projects/             ← Generated project directories
└── SPEC.md               ← Auto-generated project spec

aelidirect_branch/         ← BRANCH_ROOT (10101) — testing copy of the platform
```

### Starting the Servers

```bash
# Start prod server (port 10100)
systemctl --user start aelidirect.service

# Start branch server (port 10101) — for platform self-editing
systemctl --user start aelidirect-branch.service
```

Or manually:

```bash
cd backend
uvicorn app:app --host 0.0.0.0 --port 10100
```

### Running the Test Agent Directly

```bash
cd backend
python test_agent.py "heartbeat countdown" \
  --context "User reported that heartbeat shows the wrong next run time" \
  --project aelidirect_platform \
  --phase full
```

### API Quick Reference

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/direct/start` | POST | Create or select a project, returns stream URL |
| `/api/direct/stream` | GET | SSE stream — full chat pipeline |
| `/api/direct/todos/{project}` | GET/POST | List or add todos |
| `/api/direct/todos/{project}/{id}` | PUT/DELETE | Update or delete a todo |
| `/api/direct/heartbeat/{project}` | GET/POST | Get or configure heartbeat |
| `/api/direct/heartbeat/{project}/run` | POST | Run next pending todo now |
| `/api/platform/branch-status` | GET | Check if branch has changes vs prod |
| `/api/platform/branch-wipe` | POST | Reset branch to match prod |
| `/api/platform/branch-deploy` | POST | Deploy branch to prod |
| `/api/td-analysis` | GET/POST | Run or retrieve TD cross-project analysis |
| `/api/config` | GET | Get/set LLM provider + API key |
| `/api/direct/history/{project}` | GET | List past conversations |
</think>

# aelidirect -- Project Specification

aelidirect is a standalone AI coding agent that runs entirely on your local machine. It communicates with an LLM (via OpenRouter or MiniMax), gives the model file-system access and command execution tools, and streams its reasoning and actions back to you in real time via SSE (Server-Sent Events). The agent can create new projects from scratch, edit existing code, run tests, deploy containers, manage todos, and review its own work through a Technical Director loop.

The platform is self-hosting: aelidirect's own source code lives under its management, and the agent can edit the platform itself via a branch/prod workflow (edits go to a testing branch on port 10101; when verified, they deploy to the live server on port 10100).

---

## How It Works

### Message Flow

1. **User sends a message** through the browser UI (or the `/api/direct/start` → `/api/direct/stream` endpoints).
2. **The pipeline builds a system prompt** from: the agent instructions, SITE_MAP.md (compact file tree), SPEC.md (what the project does), long-term memory, and recent conversation history.
3. **The LLM receives the full context** and responds — either with text or a request to call a tool.
4. **Tool results are appended back to the message history** and sent to the LLM again. This repeats until the agent produces a final text response.
5. **SSE events stream back to the browser** throughout: thinking, tool calls, tool results, test phases, and the final response.
6. **The conversation is saved** to disk and the docs are regenerated in the background.

### Agent Loop (Action Turns)

Each trip through the LLM that results in a tool call counts as one "action turn." The loop runs for up to `MAX_ACTION_TURNS` (150 by default). Tools execute locally — the LLM never runs code; it just asks your machine to run things and reads the results.

### Three Phases

**1. Coding Phase** — The LLM uses tools to read files, edit code, run bash commands, check git status, manage memory, and invoke the test agent. This continues until the agent says it is done (returns text instead of tool calls).

**2. Test Phase** (triggered automatically when code was changed) — The pipeline calls `test_agent.handle_test_agent()` which runs a two-phase automated test system:
- **Plan**: reads the codebase in batch, sends it plus scope/context to the LLM, which produces a structured JSON test plan covering API, browser, and unit test cases with setup steps and assertions.
- **Run**: executes each test case (API via httpx, browser via Playwright, unit via direct Python import). If any test fails, failures are fed back to the chat pipeline with context preserved (what failed, what the agent tried, what the correct behavior should be). The LLM attempts a fix and tests re-run. This loops up to `MAX_TEST_FIX_ITERATIONS` times (2 by default).

**3. TD Review Phase** — After tests complete (or if no tests ran), a Technical Director review is generated: the LLM receives the full task → changes made → agent's final response → all test evidence, and produces a structured verdict (PASS/PARTIAL/FAIL) plus detailed feedback. TD reviews are saved and displayed per-todo in the UI.

### Self-Editing the Platform

When the active project is `aelidirect_platform`, the pipeline redirects file operations to `BRANCH_ROOT` (a separate working directory). Before starting work, it auto-wipes the branch from prod (copying source files over) so the agent always works on a clean testing copy. After code changes, the branch server (port 10101) is restarted. The UI's Branch Testing Bar shows status and provides Wipe (reset branch to prod), Test, and Deploy buttons.

---

## Features

### Core Agent
| Feature | Description |
|---------|-------------|
| **Streaming chat** | Full duplex via SSE — the browser receives thinking, tool calls, tool results, phase changes, and the final response in real time |
| **Context assembly** | System prompt built from agent instructions + SITE_MAP.md + SPEC.md + long-term memory + recent conversation history |
| **Message trimming** | Stale content is trimmed between LLM calls: `