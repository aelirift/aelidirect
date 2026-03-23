"""
Direct mode todo list and heartbeat auto-executor.

Todo: persistent task list per project.
Heartbeat: scheduled auto-execution of todo items via the Direct agent.
"""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

TODO_DIR = Path(__file__).parent / ".direct_todos"
TODO_DIR.mkdir(exist_ok=True)


def _now():
    return datetime.now(timezone.utc).isoformat()[:19]


def _todo_path(project_name: str) -> Path:
    safe = project_name.replace("/", "_").replace("..", "")
    return TODO_DIR / f"{safe}.json"


def _load_todos(project_name: str) -> list[dict]:
    path = _todo_path(project_name)
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            pass
    return []


def _save_todos(project_name: str, todos: list[dict]):
    _todo_path(project_name).write_text(json.dumps(todos, indent=2))


def add_todo(project_name: str, task: str, category: str = "feature") -> dict:
    """Add a todo item. Category: feature, debug, question, refactor."""
    todos = _load_todos(project_name)
    item = {
        "id": str(uuid.uuid4())[:8],
        "task": task,
        "category": category,
        "status": "pending",
        "created_at": _now(),
        "started_at": None,
        "completed_at": None,
        "duration_secs": None,
        "attempts": 0,
        "result_status": None,   # success, failure, partial
        "last_result": None,
        "td_review": None,
    }
    todos.append(item)
    _save_todos(project_name, todos)
    return item


def _classify_result(result: str) -> str:
    """Classify a result as success, failure, or partial."""
    if not result:
        return "success"
    lower = result.lower()
    fail_signals = ["error", "failed", "traceback", "exception", "cannot access",
                    "could not", "unable to", "crash", "fatal"]
    partial_signals = ["partially", "issue", "warning", "but ", "however",
                       "not fully", "incomplete", "workaround"]
    has_fail = any(s in lower for s in fail_signals)
    has_partial = any(s in lower for s in partial_signals)
    if has_fail and not any(s in lower for s in ["fixed", "resolved", "done"]):
        return "failure"
    if has_partial:
        return "partial"
    return "success"


def update_todo(project_name: str, todo_id: str, status: str, result: str = "") -> dict | None:
    """Update a todo item's status."""
    todos = _load_todos(project_name)
    for t in todos:
        if t["id"] == todo_id:
            t["status"] = status
            if status == "attempted":
                if not t.get("started_at"):
                    t["started_at"] = _now()
                t["attempts"] = t.get("attempts", 0) + 1
                if result:
                    t["last_result"] = result[:10000]
                    t["result_status"] = _classify_result(result)
            elif status == "done":
                now = _now()
                t["completed_at"] = now
                t["last_result"] = result[:10000]
                t["result_status"] = _classify_result(result)
                # Compute duration from started_at
                started = t.get("started_at")
                if started:
                    try:
                        s = datetime.fromisoformat(started)
                        e = datetime.fromisoformat(now)
                        t["duration_secs"] = int((e - s).total_seconds())
                    except Exception:
                        pass
            _save_todos(project_name, todos)
            return t
    return None


def delete_todo(project_name: str, todo_id: str) -> bool:
    todos = _load_todos(project_name)
    before = len(todos)
    todos = [t for t in todos if t["id"] != todo_id]
    if len(todos) < before:
        _save_todos(project_name, todos)
        return True
    return False


def get_todos(project_name: str) -> list[dict]:
    return _load_todos(project_name)


def get_pending_todos(project_name: str) -> list[dict]:
    """Get todos that haven't been completed."""
    return [t for t in _load_todos(project_name) if t["status"] in ("pending", "attempted")]


# ── Heartbeat config ──

HEARTBEAT_DIR = Path(__file__).parent / ".direct_heartbeats"
HEARTBEAT_DIR.mkdir(exist_ok=True)


def _hb_path(project_name: str) -> Path:
    safe = project_name.replace("/", "_").replace("..", "")
    return HEARTBEAT_DIR / f"{safe}.json"


def get_heartbeat(project_name: str) -> dict:
    path = _hb_path(project_name)
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            pass
    return {
        "enabled": False,
        "interval_minutes": 30,
        "last_run": None,
        "next_run": None,
        "running": False,
        "history": [],
    }


def save_heartbeat(project_name: str, hb: dict):
    _hb_path(project_name).write_text(json.dumps(hb, indent=2))


def record_heartbeat_run(project_name: str, todo_id: str, task: str, result: str):
    hb = get_heartbeat(project_name)
    hb["last_run"] = _now()
    hb["history"].append({
        "timestamp": _now(),
        "todo_id": todo_id,
        "task": task,
        "result": result[:10000],
    })
    # Keep last 50 runs
    hb["history"] = hb["history"][-50:]
    save_heartbeat(project_name, hb)


def set_todo_review(project_name: str, todo_id: str, td_review: str, td_status: str = "") -> bool:
    """Set the TD review and authoritative result_status for a completed todo."""
    todos = _load_todos(project_name)
    for t in todos:
        if t["id"] == todo_id:
            t["td_review"] = td_review
            if td_status:
                t["result_status"] = td_status
            _save_todos(project_name, todos)
            return True
    return False


def get_todo(project_name: str, todo_id: str) -> dict | None:
    """Get a single todo by ID."""
    for t in _load_todos(project_name):
        if t["id"] == todo_id:
            return t
    return None
