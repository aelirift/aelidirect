"""
Heartbeat scheduler, executor, and todo/heartbeat API routes.
"""

import json
import asyncio
from fastapi import APIRouter, Request

from constants import (
    PROD_PORT, MAX_ACTION_TURNS, LLM_STREAM_TIMEOUT,
)
from state import _heartbeat_progress, _get_provider
from direct_todo import (
    add_todo, update_todo as update_direct_todo, delete_todo,
    get_todos, get_pending_todos, get_todo, set_todo_review,
    get_heartbeat, save_heartbeat, record_heartbeat_run,
)

router = APIRouter()


# ── Internal executor ──────────────────────────────────────────────────

async def _execute_todo_via_chat(project_dir: str, todo_item: dict):
    """Execute a todo by calling the chat endpoints internally — same pipeline the browser uses."""
    import logging
    import httpx
    _log = logging.getLogger("uvicorn")
    from datetime import datetime, timezone

    todo_id = todo_item["id"]
    task = todo_item["task"]
    base_url = f"http://127.0.0.1:{PROD_PORT}"

    _heartbeat_progress.update({
        "active": True, "project": project_dir,
        "todo_id": todo_id, "task": task[:100],
        "step": "starting", "turn": 0, "max_turns": MAX_ACTION_TURNS, "total_steps": 0,
        "started_at": datetime.now(timezone.utc).isoformat()[:19],
        "finished_at": "", "result_status": "", "result_message": "",
    })

    update_direct_todo(project_dir, todo_id, "attempted")
    result_text = ""
    total_steps = 0

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(LLM_STREAM_TIMEOUT)) as client:
            # Step 1: POST /api/direct/start (same as browser sendMessage)
            start_resp = await client.post(f"{base_url}/api/direct/start", json={
                "message": task,
                "project_dir": project_dir,
            })
            start_data = start_resp.json()
            if start_data.get("error"):
                raise Exception(start_data["error"])

            stream_url = start_data["stream_url"]

            # Step 2: Consume SSE stream (same as browser EventSource)
            async with client.stream("GET", f"{base_url}{stream_url}") as stream:
                buffer = ""
                async for chunk in stream.aiter_text():
                    buffer += chunk
                    while "\n\n" in buffer:
                        event_text, buffer = buffer.split("\n\n", 1)
                        # Parse SSE event
                        event_type = ""
                        event_data = ""
                        for line in event_text.strip().split("\n"):
                            if line.startswith("event: "):
                                event_type = line[7:]
                            elif line.startswith("data: "):
                                event_data = line[6:]

                        if not event_type or not event_data:
                            continue

                        try:
                            d = json.loads(event_data)
                        except json.JSONDecodeError:
                            continue

                        if event_type == "turn":
                            _heartbeat_progress.update({
                                "turn": d.get("action_turns", 0),
                                "max_turns": d.get("max", MAX_ACTION_TURNS),
                            })
                        elif event_type == "tool_call":
                            total_steps += 1
                            name = d.get("name", "")
                            args = d.get("args", {})
                            arg_preview = args.get("path", args.get("pattern", args.get("command", "")))
                            step = f"{name}({arg_preview})" if arg_preview else name
                            _heartbeat_progress.update({"step": step, "total_steps": total_steps})
                        elif event_type == "tool_result":
                            name = d.get("name", "")
                            result_preview = (d.get("result", "") or "").strip().split('\n')[0][:60]
                            _heartbeat_progress.update({"step": f"{name} → {result_preview}"})
                        elif event_type == "response":
                            content = d.get("content", "")
                            if content:
                                result_text = content
                            _heartbeat_progress.update({"step": "completing"})
                        elif event_type == "thinking":
                            preview = (d.get("content", "") or "").strip()[:80]
                            _heartbeat_progress.update({"step": f"planning: {preview}" if preview else "thinking"})
                        elif event_type == "test_phase":
                            status = d.get("status", "")
                            iteration = d.get("iteration", 0)
                            if status == "planning":
                                _heartbeat_progress.update({"step": f"test: planning (iter {iteration})"})
                            elif status == "running":
                                tc = d.get("test_count", 0)
                                _heartbeat_progress.update({"step": f"test: running {tc} tests (iter {iteration})"})
                            elif status == "all_passed":
                                p = d.get("passed", 0)
                                _heartbeat_progress.update({"step": f"test: {p} tests passed"})
                            elif status == "error":
                                _heartbeat_progress.update({"step": f"test: error — {d.get('error', '')[:60]}"})
                        elif event_type == "test_feedback":
                            failed = d.get("failed", 0)
                            iteration = d.get("iteration", 0)
                            _heartbeat_progress.update({
                                "step": f"test: {failed} failures, fixing (iter {iteration})",
                                "turn": 0,  # Turns reset for fix attempt
                            })
                        elif event_type == "td_review":
                            status = d.get("status", "")
                            if status == "running":
                                _heartbeat_progress.update({"step": "TD review running"})
                            elif status == "complete":
                                _heartbeat_progress.update({"step": "TD review complete"})
                        elif event_type == "done":
                            break
                        elif event_type == "error":
                            raise Exception(d.get("message", "Stream error"))

        # Success — only heartbeat bookkeeping here.
        # TD review, tests, and docs regen already happened inside the pipeline.
        from direct_todo import _classify_result
        rs = _classify_result(result_text)
        _heartbeat_progress.update({
            "active": False, "step": "done", "result_status": rs,
            "result_message": result_text[:200],
            "finished_at": datetime.now(timezone.utc).isoformat()[:19],
        })
        update_direct_todo(project_dir, todo_id, "done", result_text)
        record_heartbeat_run(project_dir, todo_id, task, result_text)
        _log.info(f"[heartbeat] {project_dir}: todo {todo_id} completed ({rs})")

    except Exception as e:
        _log.error(f"[heartbeat] {project_dir}: todo {todo_id} failed: {e}")
        _heartbeat_progress.update({
            "active": False, "step": "error", "result_status": "failure",
            "result_message": str(e)[:200],
            "finished_at": datetime.now(timezone.utc).isoformat()[:19],
        })
        update_direct_todo(project_dir, todo_id, "attempted", str(e))
        record_heartbeat_run(project_dir, todo_id, task, f"ERROR: {e}")


async def _heartbeat_scheduler():
    from tools import PROJECTS_ROOT
    import logging
    _log = logging.getLogger("uvicorn")
    _log.info("[heartbeat] Scheduler started")
    while True:
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            _log.info("[heartbeat] Scheduler cancelled")
            return
        except Exception as e:
            _log.error(f"[heartbeat] Sleep error: {e}")
            continue
        try:
            from direct_todo import HEARTBEAT_DIR
            if not HEARTBEAT_DIR.exists():
                continue
            for hb_file in HEARTBEAT_DIR.glob("*.json"):
                try:
                    hb = json.loads(hb_file.read_text())
                    if not hb.get("enabled") or hb.get("running"):
                        continue
                    interval = hb.get("interval_minutes", 1)
                    last_run = hb.get("last_run")
                    if last_run:
                        from datetime import datetime, timezone
                        last_dt = datetime.fromisoformat(last_run)
                        if last_dt.tzinfo is None:
                            last_dt = last_dt.replace(tzinfo=timezone.utc)
                        if (datetime.now(timezone.utc) - last_dt).total_seconds() < interval * 60:
                            continue
                    project_dir = hb_file.stem
                    project_path = PROJECTS_ROOT / project_dir
                    if not project_path.exists():
                        continue
                    pending = get_pending_todos(project_dir)
                    if not pending:
                        continue
                    prov = _get_provider()
                    if not prov["api_key"]:
                        continue
                    _log.info(f"[heartbeat] {project_dir}: EXECUTING todo '{pending[0]['task'][:50]}'")
                    hb["running"] = True
                    save_heartbeat(project_dir, hb)

                    try:
                        await _execute_todo_via_chat(project_dir, pending[0])
                    finally:
                        from datetime import datetime, timezone
                        hb = get_heartbeat(project_dir)
                        hb["running"] = False
                        hb["last_run"] = datetime.now(timezone.utc).isoformat()[:19]
                        save_heartbeat(project_dir, hb)

                except Exception:
                    try:
                        hb = get_heartbeat(hb_file.stem)
                        hb["running"] = False
                        save_heartbeat(hb_file.stem, hb)
                    except Exception:
                        pass
        except Exception as e:
            _log.error(f"[heartbeat] Outer error: {e}")


# ── Todo Routes ────────────────────────────────────────────────────────

@router.get("/api/direct/todos/{project_dir}")
async def api_get_todos(project_dir: str):
    return {"todos": get_todos(project_dir)}


@router.post("/api/direct/todos/{project_dir}")
async def api_add_todo(project_dir: str, request: Request):
    data = await request.json()
    return {"ok": True, "todo": add_todo(project_dir, data.get("task", ""), data.get("category", "feature"))}


@router.put("/api/direct/todos/{project_dir}/{todo_id}")
async def api_update_todo(project_dir: str, todo_id: str, request: Request):
    data = await request.json()
    item = update_direct_todo(project_dir, todo_id, data.get("status", "done"), data.get("result", ""))
    return {"ok": bool(item), "todo": item}


@router.get("/api/direct/todos/{project_dir}/{todo_id}")
async def api_get_todo(project_dir: str, todo_id: str):
    todo = get_todo(project_dir, todo_id)
    if not todo:
        return {"ok": False, "error": "Todo not found"}

    # Enrich with schedule info for pending/attempted items
    schedule = {}
    if todo["status"] in ("pending", "attempted"):
        hb = get_heartbeat(project_dir)
        schedule["heartbeat_enabled"] = hb.get("enabled", False)
        schedule["heartbeat_interval"] = hb.get("interval_minutes", 30)
        pending = get_pending_todos(project_dir)
        # Find position in queue
        for i, p in enumerate(pending):
            if p["id"] == todo_id:
                schedule["queue_position"] = i + 1
                break
        # Estimate next run for this item
        if hb.get("enabled") and not hb.get("running"):
            from datetime import datetime, timezone, timedelta
            try:
                last = hb.get("last_run")
                interval = hb.get("interval_minutes", 30)
                if last:
                    last_dt = datetime.fromisoformat(last)
                    base_next = last_dt + timedelta(minutes=interval)
                else:
                    base_next = datetime.now(timezone.utc)
                # Add interval for each item ahead in queue
                pos = schedule.get("queue_position", 1) - 1
                est = base_next + timedelta(minutes=interval * pos)
                remaining = (est - datetime.now(timezone.utc)).total_seconds()
                schedule["est_run_secs"] = max(0, int(remaining))
                schedule["est_run_at"] = est.isoformat()[:19]
            except Exception:
                pass

    return {"ok": True, "todo": todo, "schedule": schedule}


@router.delete("/api/direct/todos/{project_dir}/{todo_id}")
async def api_delete_todo(project_dir: str, todo_id: str):
    return {"ok": delete_todo(project_dir, todo_id)}


# ── Heartbeat Routes ──────────────────────────────────────────────────

@router.get("/api/direct/heartbeat/{project_dir}")
async def api_get_heartbeat(project_dir: str):
    hb = get_heartbeat(project_dir)
    # Add next_run estimate
    if hb.get("enabled") and hb.get("last_run") and not hb.get("running"):
        from datetime import datetime, timezone, timedelta
        try:
            last = datetime.fromisoformat(hb["last_run"])
            next_run = last + timedelta(minutes=hb.get("interval_minutes", 30))
            hb["next_run_est"] = next_run.isoformat()[:19]
            remaining = (next_run - datetime.now(timezone.utc)).total_seconds()
            hb["next_run_secs"] = max(0, int(remaining))
        except Exception:
            pass
    # Add pending todo count + currently running todo
    pending = get_pending_todos(project_dir)
    hb["pending_count"] = len(pending)
    if pending:
        hb["next_todo"] = pending[0].get("task", "")[:80]
    return hb


@router.post("/api/direct/heartbeat/{project_dir}")
async def update_heartbeat_config(project_dir: str, request: Request):
    data = await request.json()
    hb = get_heartbeat(project_dir)
    if "enabled" in data:
        hb["enabled"] = bool(data["enabled"])
    if "interval_minutes" in data:
        hb["interval_minutes"] = max(1, int(data["interval_minutes"]))
    save_heartbeat(project_dir, hb)
    return {"ok": True, "heartbeat": hb}


@router.post("/api/direct/heartbeat/{project_dir}/run")
async def trigger_heartbeat_now(project_dir: str):
    """Run next pending todo via the chat pipeline — same as clicking Run in the UI."""
    from tools import PROJECTS_ROOT
    project_path = PROJECTS_ROOT / project_dir
    if not project_path.exists():
        return {"error": "Project not found"}
    prov = _get_provider()
    if not prov["api_key"]:
        return {"error": "No API key configured"}
    pending = get_pending_todos(project_dir)
    if not pending:
        return {"ok": True, "message": "No pending todos"}

    todo_item = pending[0]
    hb = get_heartbeat(project_dir)
    hb["running"] = True
    save_heartbeat(project_dir, hb)

    try:
        await _execute_todo_via_chat(project_dir, todo_item)
        return {"ok": True, "todo_id": todo_item["id"]}
    finally:
        from datetime import datetime, timezone
        hb = get_heartbeat(project_dir)
        hb["running"] = False
        hb["last_run"] = datetime.now(timezone.utc).isoformat()[:19]
        save_heartbeat(project_dir, hb)


# ── Heartbeat progress route ──────────────────────────────────────────

@router.get("/api/platform/heartbeat-progress")
async def get_heartbeat_progress():
    return _heartbeat_progress
