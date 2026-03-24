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