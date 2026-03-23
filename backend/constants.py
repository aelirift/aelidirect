"""
Single source of truth for all shared constants across the platform.

Every module imports from here. No hardcoded duplicates anywhere else.
If you need to change a value, change it here once.
"""

from pathlib import Path

# ── Paths ────────────────────────────────────────────────────────────
BACKEND_DIR = Path(__file__).parent
PROD_ROOT = BACKEND_DIR.parent
BRANCH_ROOT = Path("/home/aeli/projects/aelidirect_branch")
PROJECTS_ROOT = PROD_ROOT / "projects"

# Storage directories (all under backend/)
CONFIG_FILE = BACKEND_DIR / ".config.json"
PORTS_FILE = BACKEND_DIR / ".ports.json"
MEMORY_DIR = BACKEND_DIR / ".direct_memory"
CONVERSATIONS_DIR = BACKEND_DIR / ".direct_conversations"
TODOS_DIR = BACKEND_DIR / ".direct_todos"
HEARTBEATS_DIR = BACKEND_DIR / ".direct_heartbeats"
TD_REPORTS_DIR = BACKEND_DIR / ".td_reports"

# Ensure directories exist
for _d in (PROJECTS_ROOT, MEMORY_DIR, CONVERSATIONS_DIR, TODOS_DIR, HEARTBEATS_DIR, TD_REPORTS_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# ── Ports ────────────────────────────────────────────────────────────
PROD_PORT = 10100
BRANCH_PORT = 10101
POD_PORT_RANGE = range(11001, 11099)
CONTAINER_INTERNAL_PORT = 8000  # All containers listen on this internally

# ── Platform project ─────────────────────────────────────────────────
PLATFORM_PROJECT_NAME = "aelidirect_platform"

PLATFORM_SOURCE_FILES = [
    "frontend/index.html",
    "backend/app.py",
    "backend/state.py",
    "backend/pipeline.py",
    "backend/heartbeat.py",
    "backend/platform_routes.py",
    "backend/history.py",
    "backend/td.py",
    "backend/docs.py",
    "backend/tools.py",
    "backend/direct_todo.py",
    "backend/llm_client.py",
    "backend/pod.py",
    "backend/test_agent.py",
    "backend/constants.py",
]

PLATFORM_DATA_DIRS = [
    "backend/.direct_conversations",
    "backend/.direct_heartbeats",
    "backend/.direct_todos",
    "backend/.direct_memory",
    "backend/.td_reports",
    "projects",
]

PLATFORM_DATA_FILES = [
    "backend/.config.json",
    "backend/.ports.json",
    "SPEC.md",
    "CONTEXT_MAP.md",
    "DATA_FLOW.md",
]

# ── Agent limits ─────────────────────────────────────────────────────
MAX_ACTION_TURNS = 150
MAX_TEST_FIX_ITERATIONS = 2

# ── Conversation history ─────────────────────────────────────────────
CONVERSATION_HISTORY_LIMIT = 50   # Max conversations kept per project
CONVERSATION_TOKEN_BUDGET = 50_000
CHARS_PER_TOKEN = 4
SUMMARIZE_BATCH_SIZE = 10         # Conversations summarized at once
TD_ANALYSIS_RECENT_COUNT = 30     # Conversations included in TD analysis

# ── Timeouts (seconds) ──────────────────────────────────────────────
SUBPROCESS_TIMEOUT = 10           # Default for git, systemctl, etc.
SUBPROCESS_TIMEOUT_LONG = 60      # bash tool, longer commands
CONTAINER_BUILD_TIMEOUT = 120     # Podman build
HEALTH_CHECK_TIMEOUT = 5          # Quick HTTP checks
LLM_STREAM_TIMEOUT = 600.0       # Long LLM streaming (10 min)

# ── Health checks ────────────────────────────────────────────────────
HEALTH_CHECK_RETRIES = 15
HEALTH_CHECK_DELAY = 2.0

# ── Container ────────────────────────────────────────────────────────
CONTAINER_BASE_IMAGE = "python:3.13-slim"

# ── Naming ───────────────────────────────────────────────────────────
SAFE_NAME_MAX_LENGTH = 40

# ── LLM client ───────────────────────────────────────────────────────
LLM_TIMEOUT = 180.0
LLM_RETRYABLE_CODES = {429, 502, 503, 504}
LLM_MAX_RETRIES = 3
LLM_RETRY_DELAY = 3.0
LLM_MAX_TOKENS = 16000

# ── File reading ─────────────────────────────────────────────────────
READ_PROJECT_BUDGET = 100_000     # Max chars for read_project tool
READ_FILE_TRUNCATE = 16000        # Truncate files larger than this
FILE_TAIL_LINES = 20              # Lines shown at end of truncated files

CODE_EXTENSIONS = {
    ".py", ".html", ".htm", ".js", ".ts", ".css", ".yaml", ".yml",
    ".json", ".toml", ".cfg", ".ini", ".sh", ".sql", ".md", ".txt",
    ".jsx", ".tsx", ".vue", ".svelte", ".go", ".rs", ".java",
}

SKIP_DIRS = {
    "venv", "node_modules", "__pycache__", ".git", ".td_reports",
    ".td_cross_reports", "dist", "build", ".next",
}

# ── String truncation (for UI, logs, API responses) ──────────────────
TRUNCATE_TOOL_RESULT = 2000       # Tool results sent back to LLM
TRUNCATE_STDOUT = 3000            # bash stdout
TRUNCATE_STDERR = 1000            # bash stderr
TRUNCATE_GIT_DIFF = 5000          # git diff output
TRUNCATE_RESULT_PREVIEW = 200     # Short previews in progress/errors
TRUNCATE_RESPONSE_PREVIEW = 500   # Response previews in done events
TRUNCATE_TODO_RESULT = 10000      # Todo result storage
TRUNCATE_TD_INPUT = 12000         # Input to TD review LLM
TRUNCATE_TD_CONTEXT = 400_000     # Full TD analysis context cap
