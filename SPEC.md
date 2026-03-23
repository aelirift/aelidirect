<think>
The user wants me to create a SPEC.md file for the aelidirect project based on the provided source code. Let me analyze the code to understand what this project does.

From the files provided:
1. `backend/tools.py` - File system tools for the LLM (list_files, read_file, edit_file, patch_file, grep_code, read_project, etc.) with caching
2. `backend/direct_todo.py` - Todo list and heartbeat management
3. `backend/llm_client.py` - LLM client supporting OpenRouter and MiniMax
4. `backend/pod.py` - Pod management for containerized deployments


5. `backend/test_agent.py` - Two-phase testing system (plan then run)
6. `backend/constants.py` - Configuration and constants
7. `frontend/index.html` - The UI

So aelidirect is an AI-driven development platform where an agent can build projects, run tests, deploy them as containers, and maintain a todo list with heartbeat monitoring. The system has file operations, AI agent capabilities, testing infrastructure, and deployment tools all integrated into a web frontend.

The test agent works in two phases—it plans tests based on the code and context, then executes them through a fix loop that handles failures. The platform supports branching for testing, can spin up containers with health checks, and includes a TD review system. It's built with FastAPI on the backend and a custom frontend, using OpenRouter and MiniMax for AI capabilities, and manages projects in isolated directories with version tracking.
</think>

```markdown
# aelidirect — Project Specification

## Overview

aelidirect is an autonomous AI-driven development platform that lets you build, test, and deploy software by conversing with an agent. You describe what you want in plain language; the agent reads your codebase, writes code, runs tests, fixes failures, and deploys the result to a live container. The platform is itself built on the same toolchain it offers to users — aelidirect can self-edit, self-test, and self-deploy.

The system operates in two distinct environments: **prod** (the live server at `aelidirect/`) and **branch** (a parallel workspace at `/home/aeli/projects/aelidirect_branch/`). Changes are developed on the branch, tested there, and only merged to prod on explicit deploy. This allows zero-risk experimentation on the platform's own source code.

---

## How It Works

### Agent Loop

The core loop is a tool-use LLM. The agent receives a user message, decides which tools to call (read files, write files, run commands), executes those tools locally, and feeds the results back into the LLM context. The loop repeats until the task is complete or a turn limit is reached (150 turns by default).

Tool calls are defined as JSON schemas sent to the LLM at each request. When the LLM responds with a tool call, the backend executes it and returns the output as a plain text result. This happens entirely on the local machine — the LLM never executes code itself.

### Branch/Prod Architecture

```
User → Frontend (index.html)
         ↓
      FastAPI backend (app.py)
         ↓
    ┌─────┴─────┐
 prod          branch
 (live)        (testing)
 aelidirect/   /home/aeli/projects/aelidirect_branch/
```

- **Prod** serves the live UI and runs the agent for all projects.
- **Branch** is a mirror of the prod source files (platform source code only) plus per-project data (todos, conversations, memory). Platform source edits go to branch; project data lives in both.
- `branch-wipe` copies prod source files into branch, resetting the branch to match prod.
- `branch-deploy` copies changed platform source files from branch back to prod, then restarts the server.

### Dual File Cache

The tools module maintains two in-memory caches per platform file:

- **main cache** — reflects prod files (source of truth)
- **branch cache** — reflects branch edits (diverges from prod)

For non-platform projects, only the main cache is used. On successful deploy, the branch cache is copied into the main cache. On wipe, the main cache is copied into the branch cache. This lets the agent see its own edits while keeping prod and branch logically separate.

### Todo List and Heartbeat

Every project has a persistent todo list stored as JSON in `backend/.direct_todos/{project_name}.json`. Users (or the agent) can add tasks, mark them attempted or done, and attach results. The heartbeat system periodically wakes up, picks the next pending todo, and runs it through the agent pipeline automatically — turning the platform into a background autopilot.

Heartbeat is configurable per project: interval (minutes), enable/disable, and a history of the last 50 runs with results and timestamps.

### TD Review

When a todo completes, a Test-Driven Review step analyzes the task, the agent's result, and the recent conversation history (last 30 conversations, up to 400k characters). The LLM produces a structured review that gets stored back into the todo record. This provides an auditable quality gate on every completed task.

---

## Features

### Core Agent

- **Chat pipeline** — User message → agent loop → streaming SSE response. The agent calls tools in a loop until done or turn limit.
- **Tool-use LLM** — All agent capabilities are exposed as tools defined in JSON schemas. The LLM chooses which to call based on the current context.
- **Turn tracking** — Each conversation tracks how many agent turns have been used, with a configurable maximum (default 150).
- **Provider selection** — Supports OpenRouter and MiniMax. Users pick the active provider via the config UI.

### File Tools

| Tool | What it does |
|------|-------------|
| `list_files` | Lists all files and directories in a path with sizes. |
| `read_file` | Reads a file from disk. Returns from cache if the file hasn't changed on disk. Large files are truncated with the last 20 lines appended. |
| `edit_file` | Creates a new file or fully rewrites an existing file. |
| `patch_file` | Finds an exact string in an existing file and replaces it. The old text must match byte-for-byte; the tool provides helpful error messages (whitespace mismatch, ambiguous match, missing text) to guide the LLM toward correct usage. |
| `read_file_tail` | Reads the last N lines of a file. Detects truncation signs: HTML files missing closing tags, code files ending mid-statement. |
| `read_lines` | Reads a specific line range (1-indexed, inclusive). Automatically adds ±20 lines of padding to reduce follow-up reads. |
| `grep_code` | Case-insensitive search across all project files. Returns file:line:content for each match, capped at 30 results. |
| `read_project` | Reads all source files in one call. If the total fits within the budget (100k chars), it returns everything concatenated. If over budget, it returns a size-sorted file listing so the agent can choose specific files. |

### System Tools

- **Safe path enforcement** — All file tools reject access to paths outside the project directory or known safe symlink roots. This prevents the agent from accidentally writing outside the project.
- **Path normalization** — Symlinks are resolved only on the target side, not the project side, so that symlinked project directories (like `aelidirect_platform`) are accessible without triggering the safe-path guard.
- **File caching** — A dual cache (main + branch) with mtime tracking avoids redundant disk reads. Cache entries are cleared on project wipe/deploy.

### Memory

- **Conversation history** — Stored per project in `backend/.direct_conversations/`. Capped at 50 conversations, with a token budget of 50,000 characters. Older conversations are summarized in batches of 10.
- **Long-term memory** — Stored in `backend/.direct_memory/{project_name}/`. The agent can write and read memory entries that persist across sessions.
- **Todo results** — Completed todos store their full result (up to 10,000 chars) and a `result_status` (success, failure, partial) that is computed by keyword analysis of the output.

### Project Management

- **Multi-project** — All projects live under `aelidirect/projects/`. Each project has its own directory, `project_env.md` metadata file, todo list, conversation history, and memory.
- **Project init** — New projects are scaffolded with a `README.md`, a FastAPI starter (`main.py`), and a `project_env.md` with project identity and tech stack.
- **Project rename** — Updates the project name in `project_env.md` and the project directory.
- **Project env metadata** — `project_env.md` records project name, directory, tech stack, OS, and Python version. Can include arbitrary extra key-value pairs.

### Testing

aelidirect includes a built-in Test Agent with a **two-phase** automated testing system:

#### Phase 1 — Plan

The Test Agent loads all platform source files as a single concatenated batch (bypassing dozens of individual read calls). It sends this batch, the test scope, and conversation context to the LLM and asks for a structured JSON test plan. Each test case includes:

- `id` — unique identifier
- `name` — human-readable description
- `type` — `api`, `browser`, or `unit`
- `setup` — array of steps that create preconditions before the test runs (e.g., create a todo via API before testing the heartbeat countdown)
- `steps` — actual test actions (HTTP calls, Playwright actions, direct Python imports)
- `expected` — what correct behavior looks like
- `assertions` — specific checks to verify

**Important:** Setup steps are separate from test steps. The Test Agent will not assume state exists — it creates it via the API first. For example, to test the heartbeat countdown UI, it first POSTs to create a todo and enables the heartbeat, then checks the UI.

#### Phase 2 — Run

The Test Agent executes each test case:

- **API tests** — Uses `httpx.AsyncClient` to make HTTP requests. Checks status codes and specific JSON fields (including special matchers like `__exists__`, `__gt_zero__`, and type checking).
- **Browser tests** — Uses Playwright to drive a real browser. Supports click, fill, wait_for_selector, check_text, check_visible, check_count, screenshot, and JavaScript `evaluate`. Screenshots are saved to `backend/.test_screenshots/`.
- **Unit tests** — Directly imports Python modules and calls functions with provided arguments. Supports special matchers (`__truthy__`, `__falsy__`, `__not_none__`, `__contains__`, `__type__`).

#### Test-Fix Loop

When tests fail, the Test Agent formats the failures as a structured message and **sends them back through the chat pipeline** — the same flow as if a user pasted the error. The agent reads the failures, fixes the code, and the tests run again. This repeats up to 3 times (configurable).

The loop preserves full context across iterations: the original test plan, all failure details, the agent's fix response, and the updated source batch for re-testing.

#### TD Review Integration

TD review incorporates test evidence by analyzing the last 30 conversations (up to 400k characters of context). The review evaluates whether the agent's result matches the original intent, whether failures were addressed, and provides a structured verdict on the completed work.

### Deployment (Pods)

aelidirect deploys generated projects as **podman containers** managed as pods. The deployment lifecycle is:

1. **Destroy** — Force-kill any existing pod for this project, wait up to 20s for the port to be released, then fall back to a targeted kill if the port is still held.
2. **Build** — Auto-detect the app type (FastAPI, Flask, static HTML, or generic Python HTTP) and generate a `Containerfile`. Run `podman build`. A `requirements.txt` in the project is automatically installed.
3. **Start** — Create a podman pod with the port mapped, then run the container inside it.
4. **Health check** — Poll the container's `/health` endpoint up to 15 times with 2s delays, waiting for HTTP 200. If the container crashes immediately, the error is captured.
5. **Return** — On success: pod name, port, and version. On failure: the phase where it failed, the container logs, and the container state.

**Port allocation** — Ports are allocated from `11001–11098`. The system tracks allocations in `.ports.json`, checks what podman is actually using, and verifies the port is free at the OS socket level before assigning.

**Pod naming** — Pods are named `aelimini-{project_name}` (project name sanitized to `[a-zA-Z0-9_-]`, max 40 chars). This means the same project always gets the same pod — redeploying an existing project simply destroys and recreates that pod.

### Frontend

The UI is a single self-contained `index.html` with no build step. Key views:

- **Chat view** — Message bubbles (user, assistant, system, tool, error, success), a sticky progress bar with pulsing dot and elapsed time, a chat input, and a pod URL bar that shows when a project is live.
- **Right panel** — Tabbed between Todo list and Heartbeat controls. Shows pending/completed todos with status icons, durations, attempt counts, and result previews. Clicking a todo opens a detail modal with timeline, schedule info, agent result, extracted issues, and TD review.
- **Config view** — LLM provider configuration (API key, base URL, model) with per-provider sections. Active provider is highlighted.
- **Project sidebar** — Lists all projects. Clicking one switches the chat context to that project. New project button scaffolds a fresh project.
- **Branch testing bar** — When on prod, shows whether the branch has changes newer than prod. Provides "Run tests", "Deploy to prod", and "Wipe branch" buttons. During heartbeat execution, this bar shows real-time progress (todo ID, current step, turn count, elapsed time).

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend runtime | Python 3.13, FastAPI |
| AI providers | OpenRouter, MiniMax (via HTTP API) |
| Container runtime | podman (pods + containers) |
| Container base image | `python:3.13-slim` |
| Frontend | Vanilla JS + CSS, no build step |
| HTTP client (server-side) | `httpx` (async) |
| Browser automation | Playwright |
| File caching | In-memory dict with mtime tracking |
| Todo/heartbeat storage | JSON files (`backend/.direct_todos/`, `backend/.direct_heartbeats/`) |
| Conversation storage | JSON files (`backend/.direct_conversations/`) |
| Memory storage | JSON files (`backend/.direct_memory/`) |
| TD reports | JSON files (`backend/.td_reports/`) |
| Port tracking | JSON file (`backend/.ports.json`) |
| Config | JSON file (`backend/.config.json`) |

---

## How to Run

### Prerequisites

- Python 3.13+
- podman installed and the podman socket enabled (`systemctl --user enable --now podman.socket`)
- An OpenRouter or MiniMax API key

### Start the server

```bash
cd aelidirect
python -m uvicorn backend.app:app --host 0.0.0.0 --port 10100 --reload
```

- **Prod** serves on port `10100` (default).
- **Branch** serves on port `10101` (if started separately on the branch checkout).

### First-time setup

1. Open the UI at `http://localhost:10100`
2. Click the **Config** button in the sidebar
3. Select a provider (OpenRouter or MiniMax)
4. Enter your API key, base URL, and model name
5. Click **Activate** — this becomes the active provider for all agent calls

### Create a project

1. Click **+ New Project** in the sidebar
2. Enter a project name (e.g., `my-api`)
3. The project is scaffolded with `main.py` (FastAPI) and `README.md`
4. The chat context switches to the new project

### Build something

Type in the chat, e.g.:

```
Create a REST API for managing a todo list with SQLite persistence.
Include CRUD operations: create, read all, read one, update, delete.
Add a /health endpoint.
```

The agent will read the project files, write the code, and respond with a summary. To deploy:

```
Deploy this project
```

The server will build a container, start a pod, allocate a port, and the pod URL will appear in the UI.

### Run tests manually

```bash
cd backend
python test_agent.py "heartbeat countdown" --context "user reported the countdown shows 0 instead of the actual time"
```

Options:
- `--phase plan` — only generate the test plan (no execution)
- `--no-fix` — run tests once without the fix loop
- `--project <name>` — test a specific project (default: `aelidirect_platform`)

### Test-fix loop

By default, if tests fail, the Test Agent sends the failures through the chat pipeline (the same pipeline a user uses). The agent reads the failures, attempts a fix, and the tests run again. This happens up to 3 times before giving up.

```bash
# See what the full loop produces
python test_agent.py "chat pipeline" --no-fix  # one-shot
python test_agent.py "chat pipeline"          # with fix loop
```

### Deploy branch changes to prod

On the prod server, the branch testing bar will show when `aelidirect_branch/` has source changes newer than prod. Click **Deploy to prod** to copy those changes into the prod directory and restart the server.

Click **Wipe branch** to discard branch changes and sync from prod (useful after a failed experiment).

### Heartbeat / autopilot

1. In the right panel's **Heartbeat** tab, set the interval (minutes)
2. Toggle the switch to **ON**
3. Add todos to the **Todo** tab
4. The heartbeat will automatically pick up pending todos and run them through the agent in the background. Progress appears in the branch testing bar at the top of the chat.

---

## Key Constants (from `constants.py`)

| Constant | Value | Purpose |
|----------|-------|---------|
| `PROD_PORT` | `10100` | Prod server port |
| `BRANCH_PORT` | `10101` | Branch server port |
| `POD_PORT_RANGE` | `11001–11098` | Dynamic pod port allocation |
| `CONTAINER_INTERNAL_PORT` | `8000` | Container internal port (all pods) |
| `MAX_ACTION_TURNS` | `150` | Max agent turns per conversation |
| `MAX_TEST_FIX_ITERATIONS` | `3` | Max test-fix loop iterations |
| `READ_PROJECT_BUDGET` | `100,000 chars` | Budget for full project reads |
| `LLM_TIMEOUT` | `180s` | Per-call LLM timeout |
| `LLM_STREAM_TIMEOUT` | `600s` | Max streaming session |
| `HEALTH_CHECK_RETRIES` | `15` | Health check polling attempts |
| `HEALTH_CHECK_DELAY` | `2.0s` | Delay between health checks |
| `CONTAINER_BUILD_TIMEOUT` | `120s` | Podman build timeout |
```