"""
Branch/prod management routes — branch status, wipe, deploy.
"""

import json
from fastapi import APIRouter

from constants import (
    PROD_ROOT, BRANCH_ROOT,
    PLATFORM_SOURCE_FILES, PLATFORM_DATA_DIRS, PLATFORM_DATA_FILES,
    SUBPROCESS_TIMEOUT,
)
from state import _heartbeat_progress
from direct_todo import get_heartbeat

router = APIRouter()

_IS_BRANCH = PROD_ROOT.resolve() == BRANCH_ROOT.resolve()


@router.get("/api/platform/branch-status")
async def get_branch_status():
    """Compare branch (10101) vs prod (10100) source files."""
    if _IS_BRANCH:
        return {"has_changes": False, "is_branch": True}
    if not BRANCH_ROOT.exists():
        return {"has_changes": False, "error": "Branch directory not found"}

    import hashlib
    changes = []
    for rel in PLATFORM_SOURCE_FILES:
        prod_file = PROD_ROOT / rel
        branch_file = BRANCH_ROOT / rel
        prod_exists = prod_file.exists()
        branch_exists = branch_file.exists()

        if not prod_exists and not branch_exists:
            continue
        if prod_exists != branch_exists:
            changes.append({"file": rel, "status": "added" if branch_exists else "removed"})
            continue

        prod_hash = hashlib.md5(prod_file.read_bytes()).hexdigest()
        branch_hash = hashlib.md5(branch_file.read_bytes()).hexdigest()
        if prod_hash != branch_hash:
            prod_mtime = prod_file.stat().st_mtime
            branch_mtime = branch_file.stat().st_mtime
            changes.append({
                "file": rel,
                "status": "modified",
                "branch_newer": branch_mtime > prod_mtime,
                "prod_mtime": prod_mtime,
                "branch_mtime": branch_mtime,
            })

    return {
        "has_changes": len(changes) > 0,
        "changes": changes,
        "branch_path": str(BRANCH_ROOT),
    }


@router.post("/api/platform/branch-wipe")
async def wipe_branch():
    """Reset branch to match prod — copies source, data, and config."""
    if _IS_BRANCH:
        return {"ok": False, "error": "Cannot wipe from branch server — use prod (10100)"}
    if not BRANCH_ROOT.exists():
        return {"ok": False, "error": "Branch directory not found"}
    # Block wipe while main is actively editing branch files
    if _heartbeat_progress.get("active") and _heartbeat_progress.get("project") == "aelidirect_platform":
        return {"ok": False, "error": "Agent is actively editing branch files — wait for completion"}

    import shutil
    wiped = []
    errors = []

    # Full sync: copy EVERYTHING from prod → branch (except .git)
    # Delete branch contents first, then copy prod entirely
    try:
        # Remove all branch contents (except .git if it exists)
        for item in BRANCH_ROOT.iterdir():
            if item.name == ".git":
                continue
            try:
                if item.is_dir():
                    shutil.rmtree(str(item))
                else:
                    item.unlink()
            except Exception as e:
                errors.append(f"remove {item.name}: {e}")

        # Copy all prod contents to branch
        for item in PROD_ROOT.iterdir():
            if item.name == ".git" or item.name == ".claude":
                continue
            try:
                dest = BRANCH_ROOT / item.name
                if item.is_dir():
                    shutil.copytree(str(item), str(dest), symlinks=True)
                else:
                    shutil.copy2(str(item), str(dest))
                wiped.append(item.name)
            except Exception as e:
                errors.append(f"copy {item.name}: {e}")
    except Exception as e:
        errors.append(f"sync: {e}")

    # Sync file caches: main → branch
    from tools import file_cache_wipe_branch
    file_cache_wipe_branch()

    # Restart branch server so its file cache is cleared
    import subprocess
    try:
        subprocess.run(
            ["systemctl", "--user", "restart", "aelidirect-branch.service"],
            check=True, timeout=SUBPROCESS_TIMEOUT,
        )
    except Exception as e:
        errors.append(f"branch restart: {e}")

    return {"ok": len(errors) == 0, "wiped": wiped, "errors": errors}


@router.post("/api/platform/branch-deploy")
async def deploy_branch():
    """Deploy branch source files to prod and restart the prod server."""
    if _IS_BRANCH:
        return {"ok": False, "error": "Cannot deploy from branch server — use prod (10100)"}
    # Block deploy while main is updating or branch is being tested
    if _heartbeat_progress.get("active"):
        return {"ok": False, "error": "Agent is running — wait for completion before deploying"}
    # Also check branch server's heartbeat
    hb = get_heartbeat("aelidirect_platform")
    if hb.get("running"):
        return {"ok": False, "error": "Branch is running a task — wait for completion before deploying"}
    if not BRANCH_ROOT.exists():
        return {"ok": False, "error": "Branch directory not found"}

    import shutil, subprocess
    deployed = []
    errors = []

    # Copy source files + docs from branch → prod
    _deploy_files = list(PLATFORM_SOURCE_FILES) + [
        "SPEC.md", "CONTEXT_MAP.md", "DATA_FLOW.md", "SITE_MAP.md",
    ]
    for rel in _deploy_files:
        try:
            branch_file = BRANCH_ROOT / rel
            prod_file = PROD_ROOT / rel
            if branch_file.exists():
                prod_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(branch_file), str(prod_file))
                deployed.append(rel)
        except Exception as e:
            errors.append(f"{rel}: {e}")

    if errors:
        return {"ok": False, "deployed": deployed, "errors": errors}

    # Sync file caches: branch → main (only after successful file copy)
    from tools import file_cache_deploy_to_main
    file_cache_deploy_to_main()

    # Restart prod server to pick up changes
    try:
        subprocess.run(
            ["systemctl", "--user", "restart", "aelidirect.service"],
            check=True, timeout=SUBPROCESS_TIMEOUT,
        )
    except Exception as e:
        return {"ok": False, "deployed": deployed, "errors": [f"restart failed: {e}"]}

    return {"ok": True, "deployed": deployed}
