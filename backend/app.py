"""
aelidirect — Standalone direct-mode agent server.

Single agent, one conversation, all tools. No pipeline, no handoffs.
Completely standalone — no dependency on aelimini.
"""

import json
import asyncio
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse

from constants import PROD_PORT
from state import config, _save_config, _get_provider, _heartbeat_progress

from pipeline import router as pipeline_router
from heartbeat import router as heartbeat_router, _heartbeat_scheduler
from platform_routes import router as platform_router
from td import router as td_router
from history import router as history_router

app = FastAPI(title="aelidirect")

# Register all routers
app.include_router(pipeline_router)
app.include_router(heartbeat_router)
app.include_router(platform_router)
app.include_router(td_router)
app.include_router(history_router)


# ── Config endpoints ──────────────────────────────────────────────────

@app.get("/api/config")
async def get_config():
    safe = {}
    for pid, p in config["providers"].items():
        key = p.get("api_key", "")
        safe[pid] = {
            "name": p["name"], "model": p["model"],
            "base_url": p.get("base_url", ""),
            "api_key_masked": (key[:8] + "..." + key[-4:]) if len(key) > 12 else ("***" if key else ""),
            "has_key": bool(key),
        }
    return {"providers": safe, "selected": config["selected"], "pod_host": config["pod_host"]}


@app.post("/api/config")
async def save_config_endpoint(request: Request):
    data = await request.json()
    if "selected" in data:
        config["selected"] = data["selected"]
    if "api_key" in data and "provider" in data:
        pid = data["provider"]
        if pid in config["providers"]:
            config["providers"][pid]["api_key"] = data["api_key"]
    if "model" in data and "provider" in data:
        pid = data["provider"]
        if pid in config["providers"]:
            config["providers"][pid]["model"] = data["model"]
    if "pod_host" in data:
        config["pod_host"] = data["pod_host"].strip() or "localhost"
    _save_config()
    return {"ok": True}


@app.post("/api/config/provider")
async def save_provider(request: Request):
    data = await request.json()
    pid = data.get("id", "").strip()
    if not pid:
        return {"error": "Provider ID is required"}
    existing = config["providers"].get(pid, {})
    config["providers"][pid] = {
        "name": data.get("name", existing.get("name", pid)),
        "model": data.get("model", existing.get("model", "")),
        "base_url": data.get("base_url", existing.get("base_url", "")),
        "api_key": data.get("api_key", existing.get("api_key", "")),
    }
    _save_config()
    return {"ok": True}


@app.delete("/api/config/provider/{provider_id}")
async def delete_provider(provider_id: str):
    if provider_id not in config["providers"]:
        return {"error": "Provider not found"}
    if provider_id == config["selected"]:
        return {"error": "Cannot delete the active provider"}
    del config["providers"][provider_id]
    _save_config()
    return {"ok": True}


# ── Project routes ────────────────────────────────────────────────────

@app.get("/api/projects")
async def list_projects():
    from tools import PROJECTS_ROOT, read_project_env
    projects = []
    if PROJECTS_ROOT.exists():
        for d in sorted(PROJECTS_ROOT.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            if d.is_dir() and not d.name.startswith("."):
                env = read_project_env(d)
                file_count = sum(1 for f in d.rglob("*") if f.is_file() and not f.name.startswith("."))
                projects.append({
                    "dir_name": d.name,
                    "project_name": env.get("project_name", d.name),
                    "file_count": file_count,
                })
    return {"projects": projects}


@app.get("/api/projects/{dir_name}/docs")
async def get_project_docs(dir_name: str):
    from tools import PROJECTS_ROOT
    project_dir = PROJECTS_ROOT / dir_name
    docs = {}
    for name in ("SPEC.md", "CONTEXT_MAP.md", "DATA_FLOW.md"):
        path = project_dir / name
        docs[name] = path.read_text() if path.exists() else None
    return docs


@app.get("/api/platform/docs")
async def get_platform_docs():
    """Get the platform's own documentation (SPEC, CONTEXT_MAP, DATA_FLOW)."""
    platform_root = Path(__file__).parent.parent
    docs = {}
    for name in ("SPEC.md", "CONTEXT_MAP.md", "DATA_FLOW.md"):
        path = platform_root / name
        docs[name] = path.read_text() if path.exists() else None
    return docs


# ── Serve frontend ────────────────────────────────────────────────────
FRONTEND_DIR = Path(__file__).parent.parent / "frontend"


@app.get("/")
async def serve_index():
    return HTMLResponse((FRONTEND_DIR / "index.html").read_text())


# ── Startup ───────────────────────────────────────────────────────────

@app.on_event("startup")
async def _startup():
    import logging
    _log = logging.getLogger("uvicorn")
    _log.info("Starting heartbeat scheduler...")
    # Clear any stuck running flags from previous server process
    from direct_todo import HEARTBEAT_DIR
    if HEARTBEAT_DIR.exists():
        for hb_file in HEARTBEAT_DIR.glob("*.json"):
            try:
                hb = json.loads(hb_file.read_text())
                if hb.get("running"):
                    hb["running"] = False
                    hb_file.write_text(json.dumps(hb, indent=2))
                    _log.info(f"[startup] Cleared stuck running flag for {hb_file.stem}")
            except Exception:
                pass
    asyncio.create_task(_heartbeat_scheduler())


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PROD_PORT)
