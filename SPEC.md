<think>
The user wants me to generate a SPEC.md document for the aelidirect project based on the source code provided. Let me analyze the codebase to understand:

1. What the project is
2. How it works
3. Features organized by category
4. Tech stack
5. How to run it

Let me go through the code systematically.

The project appears to be called "aelidirect" (or "aelimini" in some places), which is a standalone AI agent platform. Let me analyze each component:

**Core Architecture:**
- Backend: FastAPI-based Python server
- Frontend: Single HTML file (index.html)


- Two-server setup with a production server on port 10100 and a branch server on port 10101 for development
- Branch protection mechanism where agents work on isolated copies before deploying changes to production

**Key Files:**
- `app.py`: Main FastAPI application with routes
- `pipeline.py`: The agent pipeline (main loop)
- `state.py`: State management
- `tools.py`: LLM tools (file operations, etc.)
- `direct_todo.py`: Todo list management
- `heartbeat.py`: Scheduled task execution
- `pod.py`: Container management (podman)
- `llm_client.py`: LLM API client
- `test_agent.py`: Testing system
- `docs.py`: Auto-documentation
- `td.py`: Technical Director review
- `history.py`: Conversation history
- `platform_routes.py`: Branch/prod management

**Features:**
The system has file and code tools for reading, editing, and searching files, system tools for bash commands and git operations, memory management for saving and loading data, project management capabilities, and a testing framework with planning and execution phases.

Now I'm looking at the pod system that handles containerized execution, the frontend interface with its sidebar and todo management, the test-driven review process, the platform self-editing setup with separate branch and production directories, and the heartbeat scheduler for automated task execution. I should also verify the configuration state and provider setup in state.py.

Looking at the prompt structure, I'm seeing the agent gets loaded with project specifications, context maps, data flows, site maps, and conversation history to guide its behavior. The frontend appears to be built with a dark theme and uses server-sent events to stream updates in real-time, which I should document in the spec before creating the markdown file.` blocks to 1-line summaries, replacing stale file reads with `(stale read — file patched later)`, trimming confirmatory bash output (`exit code: 0`), and truncating `old_text` in `patch_file` args |
| **Turn budget** | Coding phase caps at 150 tool-call turns; phase transitions happen automatically |
| **Context injection** | Every conversation receives SITE_MAP.md, SPEC.md, and long-term memories in the system prompt |

### File Tools

| Tool | Behavior |
|---|---|
| `read_file` | Returns full file content from an in-memory cache (cache invalidated by disk mtime). Files over 16k chars are truncated with a tail preview and a warning if the truncation looks like a truncation mid-tag or mid-statement |
| `patch_file` | Targeted edit: finds exact `old_text` and replaces it with `new_text` once. On no match, shows the nearby context to help the LLM recover. On multiple matches, asks for more context |
| `edit_file` | Full file overwrite or create-new-file. Use for creating files; `patch_file` for all modifications |
| `read_file_tail` | Shows the last N lines of a file with line numbers; detects and warns about truncation, missing closing tags, and mid-statement cuts |
| `read_lines` | Range read with ±20 lines of padding to reduce follow-up reads |
| `grep_code` | Case-insensitive pattern search across all project files, returns file:line:content |
| `read_project` | Reads all source files at once if under 100k chars budget; otherwise returns a size-sorted file listing plus auto-included SPEC.md/CONTEXT_MAP.md |
| `list_files` | Directory listing with file/dir kind and size |

### System Tools

| Tool | Behavior |
|---|---|
| `bash` | Runs shell commands with 60s timeout and cwd set to the project directory |
| `git_status`, `git_diff`, `git_log`, `git_commit` | Inline version control. Auto-initializes a git repo on first status call |
| `http_check` | Makes a GET request to the project's live pod URL and returns status + body preview |

### Memory

| Tool | Behavior |
|---|---|
| `memory_save` | Saves a named markdown note to `.direct_memory/{project}/{key}.md` |
| `memory_load` | Retrieves a named note by key |
| `memory_list` | Lists all saved note keys |

### Project Management

| Feature | Description |
|---|---|
| **Project init** | `init_project_dir()` creates README.md, main.py (FastAPI starter), and project_env.md |
| **project_env.md** | Per-project metadata: name, tech stack, OS, Python version, pod port, deploy version |
| `rename_project` | Updates project name in project_env.md |
| **Multi-project sidebar** | Frontend lists all projects in `.projects/`; switch between them via sidebar |
| **Auto-port allocation** | `get_available_port()` checks the JSON port registry, podman active ports, and OS socket availability before assigning |

### Testing

aelidirect has a **two-phase automated test system** driven by `test_agent.py`:

**Phase 1 — Plan:** The test agent reads all platform source files in one batch (~37k chars), sends them to the LLM with a scope and context, and receives a structured JSON test plan. The plan includes `setup` arrays (precondition creation via API calls) and `steps` arrays for each test case. Test types: `api` (httpx HTTP calls), `browser` (Playwright DOM interaction), `unit` (Python import + function call).

**Phase 2 — Run:** Each test case executes in order:
1. Setup steps run first (create todos, enable heartbeat, set config)
2. Test steps run and assertions are evaluated
3. Results are collected: `{id, name, type, status, details[], assertions[]}`

**Test-fix loop:** If any tests fail, failures are formatted as a message and sent back through the chat pipeline. The agent receives: which test failed, what the assertion expected, and the actual response. It fixes the code and tests are re-run. This loops up to **2 times** by default, or until all tests pass.

### Deployment

| Feature | Description |
|---|---|
| **Pod deployment** | `spin_up_pod()` manages the full container lifecycle: force-destroy old pod → build image (Containerfile auto-generated per app type) → create podman pod → health-check until HTTP 200 |
| **Auto Containerfile** | `generate_containerfile()` detects app type (FastAPI, Flask, static) and produces a matching Dockerfile with appropriate base image and CMD |
| **App type detection** | `detect_app_type()` reads project files to classify as fastapi, flask, python-http, or static |
| **Port allocation** | Pods run on host ports in range 11001–11099. `get_available_port()` uses three-layer checking: JSON registry, podman `pod ls`, OS socket bind |
| **Pod naming** | Pods are named `aelimini-{project_name}` (stable across deploys — old pod is always destroyed before new one starts) |
| **Health check** | Polls `GET /health` up to 15 times with 2s delay before declaring the pod healthy |
| **Crash detection** | On health failure, container logs and `podman inspect` state are captured for diagnosis |

### Frontend (index.html)

| Feature | Description |
|---|---|
| **Sidebar project list** | Lists all projects from `.projects/`; click to switch active project |
| **Chat view** | SSE-powered real-time stream; shows planning output, thinking, tool calls, tool results, final response |
| **Pod URL bar** | When a project is deployed, shows the pod URL with an "Open" button |
| **Right panel** | Tabbed: Todo list + Heartbeat scheduler |
| **Config view** | LLM provider selection (OpenRouter / MiniMax), per-provider API key + base URL + model selection |
| **Branch testing bar** | Shows branch vs. prod status, changed files, and Wipe/Deploy/Test buttons |
| **Heartbeat progress** | Live polling of `/api/platform/heartbeat-progress` shows current todo, step name, turn count, elapsed time |
| **Todo detail modal** | Click any todo to see: status, result badge, timeline, schedule info, extracted issues, TD review |
| **Markdown rendering** | `renderMarkdownSimple()` converts bold, code blocks, headings, lists, and inline code in agent responses and TD reviews |
| **Auto-scroll** | Messages area scrolls to bottom on new content |

### TD Review (Technical Director)

After every conversation that used tools, the pipeline runs a **TD review** that synthesizes evidence from the full arc:

1. **Input:** Original task → agent's plan → final response → test evidence (iteration count, per-test status, failure details)
2. **LLM call:** A separate LLM call with the `TODO_TD_REVIEW_PROMPT` analyzes the agent's work
3. **Output:** A `STATUS: PASS / PARTIAL / FAIL / INCOMPLETE` verdict with structured sections: Bugs Found, Bugs Fixed, Bugs Missed, Features Built, Agent Behavior, Patterns, Recommendations
4. **Storage:** Reports are saved to `.td_reports/{timestamp}.md` and available via the TD analysis API

The TD review is fed **test evidence** from the test agent: if tests failed and the agent fixed them, that chain is visible to the reviewer. If tests still fail after max iterations, the reviewer sees the exact assertion failures.

### Todo & Heartbeat Scheduler

| Feature | Description |
|---|---|
| **Todo CRUD** | Add, update, delete, get individual todos per project in `.direct_todos/` |
| **Todo categories** | `feature`, `debug`, `question`, `refactor` |
| **Status lifecycle** | `pending` → `attempted` → `done` (with result classification: success/failure/partial) |
| **Duration tracking** | Start time recorded on first attempt; completed-at and duration_secs computed |
| **Heartbeat scheduler** | Background asyncio task runs every 30s; checks heartbeat config per project |
| **Auto-execution** | `heartbeat.enabled = true` + interval triggers `_execute_todo_via_chat()` — same chat pipeline the browser uses |
| **Run Now** | Manual trigger via `/api/direct/heartbeat/{project}/run` — executes the next pending todo immediately |
| **Queue position** | Pending todos show estimated run time based on queue position and heartbeat interval |
| **Result classification** | `_classify_result()` scans output for `error`, `failed`, `traceback`, `exception` → failure; `partial`, `warning`, `but` → partial |

### Documentation Regeneration

After every conversation, `docs.py` runs four parallel LLM calls to regenerate documentation from the current source:

| Doc | Content |
|---|---|
| `SPEC.md` | Project overview, feature list, tech stack, run instructions |
| `CONTEXT_MAP.md` | File structure, API endpoints (method/path/handler), tool definitions, data formats |
| `DATA_FLOW.md` | Chat flow, tool loop, memory system, heartbeat, deployment, branch/prod sync |
| `SITE_MAP.md` | Compact file tree with per-function descriptions — compact enough to fit in every system prompt |

Regeneration runs as a background task via `loop.create_task(_regenerate_docs())`.

### Diagnostics & Logging

| Feature | Description |
|---|---|
| **Conversation history** | All sessions saved to `.direct_conversations/{project}/{timestamp}.json` |
| **History API** | `GET /api/direct/history/{project_dir}` returns last 50 conversations with tool usage summaries |
| **History erase** | `DELETE /api/direct/history/{project_dir}` wipes all conversations for a project |
| **Conversation summarizer** | Old conversations (beyond last 10) are batch-summarized by an LLM into one-line summaries stored in the JSON file |
| **Pod logs** | `get_container_logs()` streams podman logs via the diagnostics tool interface |
| **Platform routes** | Branch status, wipe, and deploy are exposed as REST endpoints |

---

## 4. Tech Stack

| Layer | Technology |
|---|---|
| **Backend framework** | FastAPI (Python 3.13) |
| **LLM client** | httpx → OpenRouter / MiniMax API |
| **Frontend** | Vanilla JS, single `index.html`, CSS |
| **Real-time** | Server-Sent Events (SSE) |
| **Testing** | httpx (API), Playwright (browser), importlib (unit) |
| **Container runtime** | podman + podman pods |
| **Persistent storage** | JSON files on disk (`.direct_*` directories) |
| **Platform self-editing** | Dual-server: prod (10100) + branch (10101) |
| **Config** | `.config.json` (API keys, model selection) |

---

## 5. How to Run

### Prerequisites

```bash
# System
python3 --version   # 3.13 or compatible
pip install fastapi uvicorn httpx
podman --version

# Python dependencies (see requirements.txt or install manually)
fastapi, uvicorn, httpx, playwright (for test agent browser tests)
playwright install chromium  # if using browser tests
```

### Project Layout

```
aelidirect/
├── backend/
│   ├── app.py              # FastAPI app + all route registration
│   ├── pipeline.py         # Agent loop: plan → code → test → TD review
│   ├── tools.py            # LLM tool definitions + executors
│   ├── test_agent.py       # Two-phase test system
│   ├── heartbeat.py        # Todo scheduler + executor
│   ├── direct_todo.py      # Todo CRUD + heartbeat config
│   ├── pod.py              # Container build + run + health check
│   ├── state.py            # Global config + provider state
│   ├── llm_client.py       # Raw LLM API calls
│   ├── docs.py             # Auto-documentation regeneration
│   ├── td.py               # Technical Director analysis
│   ├── history.py          # Conversation persistence
│   ├── platform_routes.py  # Branch/prod management
│   ├── constants.py        # All shared constants
│   └── ...
├── frontend/
│   └── index.html          # Full SPA frontend
├── projects/               # User project directories
├── SPEC.md, CONTEXT_MAP.md, DATA_FLOW.md, SITE_MAP.md  # Auto-generated
└── .config.json            # API keys, model selection
```

### Running the Production Server

```bash
cd backend
uvicorn app:app --host 0.0.0.0 --port 10100 --reload
```

Then open `http://localhost:10100` in a browser.

### Running the Branch Server

```bash
# In a separate terminal
cd backend
uvicorn app:app --host 0.0.0.0 --port 10101
```

The branch server (10101) and prod server (10100) can run simultaneously. The frontend's branch bar automatically detects which server it's talking to.

### Configuration

On first load, go to **Config** in the frontend sidebar and enter:

- **Provider:** `openrouter` or `minimax`
- **API Key:** Your key
- **Base URL:** `https://openrouter.ai/api/v1` or `https://api.minimax.chat`
- **Model:** e.g. `anthropic/claude-3.5-sonnet`

Click a provider's **Select** button to activate it.

### Running a Project

1. Type a message in the chat (e.g. "Build a REST API for a todo list")
2. The agent plans, writes code, and deploys it into a podman pod
3. Watch the live SSE stream: planning → thinking → tool calls → results → pod URL
4. Click **Open** to see your running app
5. After the conversation, testing runs automatically and TD review is generated

### Running the Test Agent (CLI)

```bash
cd backend
python test_agent.py "heartbeat countdown" --context "User reported countdown doesn't update"

# Or just generate the test plan without running:
python test_agent.py "chat pipeline" --plan-only
```

### Running Todo / Heartbeat (scheduled)

Heartbeat runs automatically when `enabled = true` on a project's heartbeat config. To trigger manually:

```bash
curl -X POST http://localhost:10100/api/direct/heartbeat/{project_dir}/run
```

### Deploying Branch to Production

In the frontend's branch bar (visible when branch has newer files):
1. Click **Test** to run the automated test suite against the branch
2. If tests pass, click **Deploy** to copy branch files → prod and restart the production server
3. Click **Wipe** to reset the branch to match production (no changes deployed)

---

*SPEC.md is auto-generated by the platform itself after every conversation. Last regenerated: after the most recent chat session.*
```
</think>

```markdown
# aelidirect -- Project Specification

## 1. Overview

aelidirect is a self-hostable AI coding agent platform that lets you describe what you want to build in plain English and watch it happen — code written, tested, and deployed into a live podman container, all in one session. It runs as a FastAPI backend with a single HTML frontend and communicates with any OpenRouter- or MiniMax-compatible LLM via a clean REST/tool-call interface. Unlike generic chat assistants, every aelidirect conversation operates inside a real project directory with full file-system access, persistent memory, scheduled task queues, and an automated test-fix loop that catches regressions before they ship.

The platform also edits *itself*: the aelidirect branch server (port 10101) is a fully isolated copy of the platform that the agent modifies directly. When you deploy the branch to production (port 10100), the same pipeline that builds your projects deploys your own infrastructure.

---

## 2. How It Works

### The Message Flow

A user types a message in the frontend. The browser POSTs it to `/api/direct/start`, which creates or resumes a project directory, then returns an SSE (Server-Sent Events) stream URL. The browser opens that URL with `EventSource` and receives a real-time firehose of structured events:

```
planning → turn → thinking → tool_call → tool_result → ... → response → test_phase → td_review → done
```

### The Agent Loop

The backend pipeline runs in three phases per conversation:

**Planning phase** — The LLM receives the user's message with **no tools enabled** and must respond with a text plan. This forces structured thinking before any code is touched.

**Coding phase** — The LLM receives the full tool definition set and operates in a tool-call loop (up to 150 turns):
1. LLM decides: respond in text, or call a tool?
2. If tool: the backend executes it and appends the result to the message history
3. Loop continues until the LLM gives a final text response

**Post-test phase** — After the final response, the pipeline transitions to testing automatically (see Test Agent below).

### Platform Self-Editing

When the active project is `aelidirect_platform`, the pipeline redirects file writes from the prod path to `BRANCH_ROOT` (the branch server's working directory). The agent edits a live copy of the platform without touching production. After the conversation, docs are regenerated and the branch server is restarted so it reflects the new edits immediately.

### Dual-Server Architecture

| Server | Port | Role |
|---|---|---|
| Production | 10100 | Live aelidirect instance — stable |
| Branch | 10101 | Isolated dev copy — agent's workspace |

Branch status is visible in the frontend. You can wipe the branch back to prod state, or deploy branch changes to production through explicit UI actions.

---

## 3. Features

### Core Agent

| Feature | Description |
|---|---|
| **Planning turn** | First LLM call has zero tools — forces a text plan that is shown to the user and appended to context |
| **Tool-call loop** | LLM alternates between text responses and tool calls; each result feeds back into the next LLM call |
| **Long-term memory** | `memory_save` / `memory_load` / `memory_list` tools persist named notes across sessions in `.direct_memory/` |
| **Conversation history** | Last 5 conversations are injected into the system prompt; older ones are summarized and stored on disk |
| **Stale-context trimmer** | `_trim_messages()` compresses message history by: stripping `