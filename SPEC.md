# aelidirect -- Project Specification

## What Is This?

aelidirect is an **AI-powered coding agent** that you talk to through a web chat interface. You describe what you want to build, and the agent writes code, creates files, deploys your project to a live server, and fixes bugs -- all by itself.

Think of it like having a programmer on the other end of a chat window. You say "build me a todo app" and it actually writes the code, creates the files, deploys it to a container, and gives you a URL where you can see it running.

The key thing that makes this an "agent" rather than just a chatbot: it has **tools**. It can read files, write files, run shell commands, search code, deploy containers, and remember things across conversations. The AI model (the LLM) does not do these things directly. Instead, it *asks* your server to do them, and your server runs the tools and sends the results back. This loop of "think, call a tool, read the result, think again" is what makes it an agent.

## How It Works (The Big Picture)

1. You open a web page and type a message like "build me a weather API."
2. The frontend sends your message to the backend server.
3. The backend sends your message (plus a system prompt and available tools) to an LLM (like MiniMax or a model on OpenRouter).
4. The LLM thinks about your request and decides what to do. Instead of just replying with text, it can say "call the `edit_file` tool with this code."
5. The backend sees the tool call, runs it on your machine, and sends the result back to the LLM.
6. The LLM looks at the result and decides what to do next -- maybe call another tool, or finally reply with text.
7. This loop continues (up to 80 action turns) until the LLM sends a final text response.
8. Everything streams back to the frontend in real time using Server-Sent Events (SSE), so you can watch the agent work.

## Features

### Core Agent Loop
- **Tool-use loop**: The LLM can call tools repeatedly until the task is done. Read-only tool calls (like reading files) do not count toward the turn limit, so the agent can explore freely without wasting its action budget.
- **Streaming**: All tool calls and results stream to the browser in real time as Server-Sent Events. You see every step the agent takes, not just the final answer.
- **Multiple LLM providers**: Supports OpenRouter and MiniMax out of the box, and you can add custom providers through the config UI.

### File Tools
- **list_files**: See what files exist in the project.
- **read_file**: Read a file's contents (truncates large files and shows last 20 lines).
- **read_file_tail**: Read the last N lines of a file.
- **read_lines**: Read a specific line range from a file.
- **edit_file**: Create a new file or completely rewrite an existing one.
- **patch_file**: Make a targeted edit to an existing file by finding and replacing specific text. Safer than rewriting the whole file.
- **grep_code**: Search all project files for a pattern.
- **read_project**: Read all source code at once (for small projects) or get a file listing (for large ones).

### System Tools
- **bash**: Run any shell command. The agent uses this for installing packages, running tests, compiling code, and anything the file tools cannot do.
- **deploy_pod**: Build and deploy the project as a live container using Podman. Handles the full lifecycle: destroy old container, build image, start new container, health check.
- **http_check**: Test a live endpoint on the deployed pod.
- **git_status / git_diff / git_log / git_commit**: Full git integration. The agent initializes a repo if one does not exist and commits after changes.

### Memory System
- **Long-term memory** (`memory_save`, `memory_load`, `memory_list`): The agent saves important facts to disk as small `.md` files. These are loaded into the system prompt at the start of every conversation, so the agent remembers what it learned last time.
- **Short-term memory**: Recent conversation history is saved as JSON files and loaded automatically. Old conversations are summarized by the LLM to save token space.

### Project Management
- **Multiple projects**: The sidebar lists all your projects. Click one to switch context.
- **Project environment**: Each project has a `project_env.md` file with metadata (name, tech stack, OS, deploy version, pod port).
- **Todo list**: Add tasks for the agent to work on. Tasks have categories (feature, debug, question, refactor) and status tracking.
- **Heartbeat auto-executor**: Enable a timer that periodically picks up pending todo items and runs the agent on them automatically. You can set the interval (minimum 5 minutes).
- **Conversation history**: Browse previous conversations in the chat view. The system keeps the last 50 and summarizes older ones.

### Deployment
- **Container-based**: Projects are deployed as Podman containers. The system detects whether your code is FastAPI, Flask, or static HTML and generates the right Containerfile.
- **Health checks**: After deployment, the system polls `/health` until it gets HTTP 200 or gives up after 15 attempts.
- **Port management**: Each project gets a unique port in the 11001-11098 range. Ports are tracked in a JSON file and verified at the OS level.

### Frontend
- Single-page web app (one HTML file with embedded CSS and JavaScript).
- Dark theme with a sidebar for project navigation and a main chat area.
- Real-time streaming display of agent thinking, tool calls, tool results, and final responses.
- Config page for managing LLM providers and API keys.
- Todo panel and heartbeat controls per project.

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Backend | Python, FastAPI, Uvicorn |
| Frontend | Vanilla HTML/CSS/JavaScript (single file) |
| LLM Communication | HTTP POST to OpenAI-compatible chat/completions API |
| Streaming | Server-Sent Events (SSE) |
| Containers | Podman (pods and containers) |
| Storage | JSON files on disk (config, memory, conversations, todos) |

## Running It

```bash
cd backend
python main.py
```

This starts the server on `http://localhost:10100`. Open that URL in a browser. You will need at least one LLM API key configured (OpenRouter or MiniMax) before the agent can do anything.
