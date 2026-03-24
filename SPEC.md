# aelidirect -- Project Specification

aelidirect is a self-hosted AI coding agent that turns natural-language task descriptions into running applications. Unlike cloud-based agents (Claude Code, Cursor), it runs entirely on your own machine: the LLM generates code, the platform writes files, spins up containers, runs tests, and self-edits its own codebase through a managed branch/deploy workflow. The platform is built with FastAPI, serves a single HTML page, and communicates via Server-Sent Events (SSE) so the browser receives real-time streaming updates as the agent works.

At its core, the system is a chat pipeline that wraps an LLM with a set of tools (file read/write, bash, git, memory, HTTP checks) so the model can act on code the same way a developer would. The platform ships with its own source as a project, enabling it to modify and redeploy itself through a safe branch-then-deploy cycle.

---

## How It Works

### Message Flow

1. **User sends a task** — e.g., "Add a countdown timer to the heartbeat panel." The browser POSTs to `/api/direct/start`, which creates or selects a project directory and returns a stream URL.
2. **SSE stream begins** — The browser connects to `/api/direct/stream` and receives a real-time sequence of events as the agent works.
3. **Planning turn (no tools)** — The LLM receives the system prompt (site map, SPEC, memory, history) plus the user message and is forced to respond with plain text — no tool calls. This keeps it focused on architecture before it starts writing code.
4. **Coding phase (tools enabled)** — The LLM now has access to all tool definitions. It reads files, edits code, runs bash commands, checks HTTP endpoints, and saves memories. Each tool call is executed locally and the result is appended to the message history.
5. **Test phase** — After coding turns complete, the pipeline calls `test_agent` (an internal tool). The test agent runs a two-phase test: plan → run. If tests fail, failures are fed back to the LLM as a new user message, and coding resumes. This loop runs up to 2 fix iterations.
6. **TD review** — After testing (or if no tests ran), a Technical Director LLM call reviews the full arc: task → plan → code changes → test results. The review is saved to disk and shown in the UI.
7. **Done** — The SSE stream ends with a `done` event containing turn counts, test evidence, and the TD review snippet. Docs are regenerated in the background.

### Agent Loop Detail

The coding loop runs for up to 150 action turns. Each turn the LLM receives trimmed messages (stale reads removed, think blocks condensed, confirmatory bash output dropped) and returns either a text response (done) or tool calls (continue).

### Platform Deployment (Branch → Prod)

When editing the platform itself (`aelidirect_platform` project):

1. **All edits go to branch (10101)** — never prod (10100). The pipeline detects `aelidirect_platform` and redirects file operations to `/home/aeli/projects/aelidirect_branch/`.
2. **Auto-wipe** — Before each conversation, if branch files are not newer than prod, branch is wiped (prod copied to branch) so the agent starts from clean prod code.
3. **Agent codes on branch** — Edits, patches, restarts all happen on port 10101.
4. **Tests run on branch** — After coding, the test agent runs against 10101 (not 10100). Branch is restarted before tests so they hit the new code.
5. **Deploy to prod** — User clicks "Deploy" in the UI to copy branch files to prod and restart 10100. This is the only way changes reach prod.
6. **Prod is never modified directly** — The running conversation is on prod (10100). If prod restarted mid-conversation, the connection would die. All changes go through branch first.

Ports:
- **10100** — Production. Serves the UI. Runs the pipeline. Never edited directly.
- **10101** — Branch/testing. Agent edits here. Tests verify here. Deploy copies to prod.
- **11001-11099** — User project pods (containers deployed by the agent).