"""
Pod management — build, run, health-check containers from generated code.

Central function: spin_up_pod() handles the full lifecycle:
  1. Force-destroy existing pod for this project
  2. Build new image
  3. Create pod on assigned port
  4. Health check — only returns success after confirmed HTTP 200
  5. On failure: returns detailed error info for Diagnostics agent

Pods are named after projects (aelimini-{project_name}), not session IDs.
Version tracking via project_env.md.
"""

import os
import re
import socket
import subprocess
import time
import json
import urllib.request
import urllib.error
from pathlib import Path

# ── Port allocation ──────────────────────────────────────────────────
PORT_RANGE = range(11001, 11099)
PORT_FILE = Path(__file__).parent / ".ports.json"
INTERNAL_PORT = 8000  # All containers listen on 8000 internally


def _load_ports() -> dict:
    if PORT_FILE.exists():
        try:
            return json.loads(PORT_FILE.read_text())
        except Exception:
            pass
    return {}


def _save_ports(data: dict):
    PORT_FILE.write_text(json.dumps(data, indent=2))


def _is_port_free(port: int) -> bool:
    """Check if a port is actually free at the OS level."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            s.bind(("0.0.0.0", port))
            return True
    except OSError:
        return False


def _safe_pod_name(project_name: str) -> str:
    """Convert project name to a safe podman pod name."""
    safe = re.sub(r'[^a-zA-Z0-9_-]', '_', project_name.lower())[:40]
    return f"aelimini-{safe}" if safe else "aelimini-project"


def get_available_port(project_name: str = "") -> int | None:
    """Find an unused port in the range. Checks JSON file, podman, AND OS socket."""
    ports = _load_ports()
    used = set(int(v) for v in ports.values())
    # Also check what podman is actually using
    try:
        result = subprocess.run(
            ["podman", "pod", "ls", "--format", "{{.Ports}}"],
            capture_output=True, text=True, timeout=10,
        )
        for line in result.stdout.splitlines():
            for part in line.split(","):
                part = part.strip()
                if "->" in part:
                    host_part = part.split("->")[0]
                    port_num = host_part.split(":")[-1]
                    if port_num.isdigit():
                        used.add(int(port_num))
    except Exception:
        pass

    for port in PORT_RANGE:
        if port not in used and _is_port_free(port):
            if project_name:
                ports[project_name] = port
                _save_ports(ports)
            return port
    return None


def release_port(project_name: str):
    """Release a port allocation."""
    ports = _load_ports()
    ports.pop(project_name, None)
    _save_ports(ports)


# ── App type detection ───────────────────────────────────────────────

def detect_app_type(project_dir: Path) -> str:
    """Detect what kind of app was generated."""
    files = {f.name for f in project_dir.rglob("*") if f.is_file()}

    for py_file in project_dir.glob("*.py"):
        try:
            content = py_file.read_text()
            if "FastAPI" in content or "fastapi" in content:
                return "fastapi"
            if "Flask" in content or "flask" in content:
                return "flask"
        except Exception:
            continue

    if "index.html" in files:
        return "static"
    if any(f.endswith(".py") for f in files):
        return "python-http"
    return "static"


# ── Containerfile generation ─────────────────────────────────────────

def generate_containerfile(project_dir: Path, app_type: str, port: int = INTERNAL_PORT) -> str:
    """Generate a Containerfile for the detected app type."""
    has_requirements = (project_dir / "requirements.txt").exists()
    req_install = f"RUN pip install --no-cache-dir -r requirements.txt\n" if has_requirements else ""

    if app_type == "fastapi":
        main_module = "main"
        for name in ["main.py", "app.py", "server.py"]:
            if (project_dir / name).exists():
                main_module = name[:-3]
                break
        req_install_base = "RUN pip install --no-cache-dir fastapi uvicorn\n"
        return (
            f"FROM python:3.13-slim\n"
            f"WORKDIR /app\n"
            f"COPY . /app/\n"
            f"{req_install_base}"
            f"{req_install}"
            f"EXPOSE {port}\n"
            f'CMD ["python", "-m", "uvicorn", "{main_module}:app", "--host", "0.0.0.0", "--port", "{port}"]\n'
        )

    elif app_type == "flask":
        main_module = "main"
        for name in ["main.py", "app.py", "server.py"]:
            if (project_dir / name).exists():
                main_module = name[:-3]
                break
        req_install_base = "RUN pip install --no-cache-dir flask\n"
        return (
            f"FROM python:3.13-slim\n"
            f"WORKDIR /app\n"
            f"COPY . /app/\n"
            f"{req_install_base}"
            f"{req_install}"
            f"EXPOSE {port}\n"
            f'CMD ["python", "-m", "flask", "--app", "{main_module}", "run", "--host", "0.0.0.0", "--port", "{port}"]\n'
        )

    elif app_type == "static":
        return (
            f"FROM python:3.13-slim\n"
            f"WORKDIR /app\n"
            f"COPY . /app/\n"
            f"EXPOSE {port}\n"
            f'CMD ["python3", "-m", "http.server", "{port}", "--directory", "/app"]\n'
        )

    else:
        return (
            f"FROM python:3.13-slim\n"
            f"WORKDIR /app\n"
            f"COPY . /app/\n"
            f"{req_install}"
            f"EXPOSE {port}\n"
            f'CMD ["python3", "-m", "http.server", "{port}", "--directory", "/app"]\n'
        )


# ── Build & Run ──────────────────────────────────────────────────────

def build_image(project_dir: Path, image_name: str) -> tuple[bool, str]:
    """Build a container image from the project directory."""
    app_type = detect_app_type(project_dir)
    containerfile_content = generate_containerfile(project_dir, app_type)

    cf_path = project_dir / "Containerfile"
    cf_path.write_text(containerfile_content)

    try:
        result = subprocess.run(
            ["podman", "build", "-t", image_name, "-f", str(cf_path), str(project_dir)],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            return False, f"Build failed:\n{result.stderr}\n{result.stdout}"
        return True, f"Built {image_name} (app_type={app_type})"
    except subprocess.TimeoutExpired:
        return False, "Build timed out (120s)"
    except Exception as e:
        return False, f"Build error: {e}"


def _force_destroy_pod(pod_name: str):
    """Force-destroy a pod by name. Guaranteed immediate."""
    subprocess.run(
        ["podman", "pod", "rm", "-f", pod_name],
        capture_output=True, timeout=15, check=False,
    )


def _create_pod(pod_name: str, image_name: str, host_port: int) -> tuple[bool, str]:
    """Create a podman pod and run the container in it."""
    try:
        result = subprocess.run(
            ["podman", "pod", "create", "--name", pod_name,
             "-p", f"{host_port}:{INTERNAL_PORT}"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            return False, f"Pod create failed: {result.stderr}"

        result = subprocess.run(
            ["podman", "run", "-d", "--pod", pod_name,
             "--name", f"{pod_name}-app", image_name],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            return False, f"Container run failed: {result.stderr}"

        return True, f"Pod {pod_name} running on port {host_port}"

    except subprocess.TimeoutExpired:
        return False, "Pod creation timed out (60s)"
    except Exception as e:
        return False, f"Pod error: {e}"


def health_check(port: int, path: str = "/", retries: int = 15, delay: float = 2.0) -> tuple[bool, str]:
    """Poll the pod until it responds with HTTP 200."""
    url = f"http://localhost:{port}{path}"
    last_error = ""

    for attempt in range(retries):
        time.sleep(delay)
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status == 200:
                    body = resp.read(500).decode("utf-8", errors="replace")
                    return True, f"Health OK (attempt {attempt + 1}): HTTP 200\nBody preview: {body[:200]}"
        except urllib.error.HTTPError as e:
            last_error = f"HTTP {e.code}"
        except urllib.error.URLError as e:
            last_error = f"Connection: {e.reason}"
        except Exception as e:
            last_error = str(e)

    return False, f"Health check failed after {retries} attempts: {last_error}"


# ═════════════════════════════════════════════════════════════════════
# spin_up_pod() — THE SINGLE DEPLOY FUNCTION
# ═════════════════════════════════════════════════════════════════════

def spin_up_pod(
    project_dir: Path,
    project_name: str,
    host_port: int,
    version: int = 1,
) -> dict:
    """Full pod lifecycle: destroy old → build → create → health check.

    Returns:
        {
            "success": True/False,
            "pod_name": "aelimini-spin_up_the_site",
            "port": 11002,
            "version": 3,
            "message": "...",
            "logs": "..." (container logs on failure),
            "phase": "destroy" | "build" | "start" | "health" (where it failed),
        }
    """
    pod_name = _safe_pod_name(project_name)
    image_name = f"{pod_name}:v{version}"
    result = {
        "success": False,
        "pod_name": pod_name,
        "port": host_port,
        "version": version,
        "message": "",
        "logs": "",
        "phase": "",
    }

    # ── 1. DESTROY existing pod for this project ──
    result["phase"] = "destroy"
    try:
        _force_destroy_pod(pod_name)
        # Wait for port to be released by the OS (up to 15s)
        for _ in range(15):
            if _is_port_free(host_port):
                break
            time.sleep(1)
        else:
            # Port still occupied — find and kill whatever is using it
            if not _is_port_free(host_port):
                _kill_pod_on_port(host_port)
                # Wait another 5s after killing
                for _ in range(5):
                    if _is_port_free(host_port):
                        break
                    time.sleep(1)
                if not _is_port_free(host_port):
                    result["message"] = f"Port {host_port} still occupied after destroying pod and waiting 20s"
                    return result
    except Exception as e:
        result["message"] = f"Failed to destroy old pod: {e}"
        return result

    # ── 2. BUILD image ──
    result["phase"] = "build"
    ok, msg = build_image(project_dir, image_name)
    if not ok:
        result["message"] = msg
        return result

    # ── 3. START pod ──
    result["phase"] = "start"
    ok, msg = _create_pod(pod_name, image_name, host_port)
    if not ok:
        result["message"] = msg
        # Try to get logs even if start failed
        result["logs"] = _get_logs(pod_name)
        return result

    # ── 4. HEALTH CHECK ──
    result["phase"] = "health"
    ok, msg = health_check(host_port, "/health", retries=15, delay=2.0)
    if ok:
        result["success"] = True
        result["message"] = msg
        return result

    # Health failed — get logs and container status for diagnosis
    result["message"] = msg
    result["logs"] = _get_logs(pod_name)

    # Check if container crashed immediately
    try:
        inspect = subprocess.run(
            ["podman", "inspect", f"{pod_name}-app", "--format", "{{.State.Status}}"],
            capture_output=True, text=True, timeout=5,
        )
        container_state = inspect.stdout.strip()
        if container_state == "exited":
            result["message"] += f"\nContainer exited immediately. Crash detected."
    except Exception:
        pass

    return result


def _kill_pod_on_port(port: int):
    """Find and destroy any aelimini pod using a specific port."""
    try:
        result = subprocess.run(
            ["podman", "pod", "ls", "--format", "json"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return
        pods = json.loads(result.stdout)
        for p in pods:
            name = p.get("Name", "")
            if not name.startswith("aelimini-"):
                continue
            # Check if this pod uses the target port
            try:
                inspect = subprocess.run(
                    ["podman", "pod", "inspect", name],
                    capture_output=True, text=True, timeout=5,
                )
                if str(port) in inspect.stdout:
                    _force_destroy_pod(name)
            except Exception:
                continue
    except Exception:
        pass


def _get_logs(pod_name: str, tail: int = 80) -> str:
    """Get container logs for a pod."""
    container_name = f"{pod_name}-app"
    try:
        result = subprocess.run(
            ["podman", "logs", "--tail", str(tail), container_name],
            capture_output=True, text=True, timeout=10,
        )
        logs = result.stdout + result.stderr
        return logs if logs.strip() else "(no logs)"
    except Exception as e:
        return f"Could not read logs: {e}"


# ═════════════════════════════════════════════════════════════════════
# Legacy functions — still used by Diagnostics agent tools
# ═════════════════════════════════════════════════════════════════════

def destroy_pod(session_id: str) -> bool:
    """Stop and remove a pod (legacy — by session ID)."""
    pod_name = f"aelimini-{session_id}"
    try:
        _force_destroy_pod(pod_name)
        release_port(session_id)
        return True
    except Exception:
        return False


def get_pod_status(session_id: str) -> dict:
    """Get the status of a pod (legacy — by session ID)."""
    pod_name = f"aelimini-{session_id}"
    return get_pod_status_by_name(pod_name)


def get_pod_status_by_name(pod_name: str) -> dict:
    """Get the status of a pod by its name."""
    try:
        result = subprocess.run(
            ["podman", "pod", "inspect", pod_name],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            info = json.loads(result.stdout)
            state = info.get("State", "unknown")
            return {"exists": True, "state": state, "pod_name": pod_name}
    except Exception:
        pass
    return {"exists": False, "state": "not found", "pod_name": pod_name}


def list_pods() -> list[dict]:
    """List all aelimini pods."""
    try:
        result = subprocess.run(
            ["podman", "pod", "ls", "--format", "json"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            pods = json.loads(result.stdout)
            return [
                {"name": p["Name"], "status": p.get("Status", "unknown"),
                 "id": p.get("Id", "")[:12]}
                for p in pods if p["Name"].startswith("aelimini-")
            ]
    except Exception:
        pass
    return []


def get_pod_logs(session_id: str, tail: int = 50) -> str:
    """Get container logs for debugging (legacy — by session ID)."""
    pod_name = f"aelimini-{session_id}"
    return _get_logs(pod_name, tail)


def get_pod_logs_by_name(pod_name: str, tail: int = 50) -> str:
    """Get container logs by pod name."""
    return _get_logs(pod_name, tail)


def http_get(port: int, path: str = "/") -> str:
    """Make an HTTP GET request and return status + body."""
    url = f"http://localhost:{port}{path}"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read(4000).decode("utf-8", errors="replace")
            return f"HTTP {resp.status}\n\n{body}"
    except urllib.error.HTTPError as e:
        try:
            body = e.read(2000).decode("utf-8", errors="replace")
        except Exception:
            body = ""
        return f"HTTP {e.code}: {e.reason}\n\n{body}"
    except urllib.error.URLError as e:
        return f"Connection failed: {e.reason}"
    except Exception as e:
        return f"Error: {e}"


# ═════════════════════════════════════════════════════════════════════
# TOOL DEFINITIONS — used by Diagnostics agent for investigation
# ═════════════════════════════════════════════════════════════════════

_agent_state = {
    "project_dir": None,
    "project_name": None,
    "session_id": None,
    "host_port": None,
}


def set_agent_state(project_dir: Path, session_id: str, host_port: int, project_name: str = ""):
    """Set state for the agent's tool executors."""
    _agent_state["project_dir"] = project_dir
    _agent_state["session_id"] = session_id
    _agent_state["host_port"] = host_port
    _agent_state["project_name"] = project_name


def get_agent_port() -> int | None:
    return _agent_state["host_port"]


POD_TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "list_project_files",
            "description": "List all files in the generated project directory with sizes.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_project_file",
            "description": "Read the contents of a file in the generated project.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path relative to project root"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_project_file",
            "description": "Create or overwrite a file in the project.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path relative to project root"},
                    "content": {"type": "string", "description": "Complete new file content"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_pod_status",
            "description": "Check if the project's pod is running. Returns status and port.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_container_logs",
            "description": "Read the container's stdout/stderr logs for debugging.",
            "parameters": {
                "type": "object",
                "properties": {
                    "tail": {"type": "integer", "description": "Number of recent log lines (default: 80)"},
                },
                "required": [],
            },
        },
    },
]


def execute_pod_tool(name: str, arguments: dict) -> str:
    """Execute a pod tool by name. Called by agent loops."""
    project_dir = _agent_state["project_dir"]
    project_name = _agent_state["project_name"] or _agent_state.get("session_id", "")
    host_port = _agent_state["host_port"]

    if not project_dir:
        return "Error: agent state not initialized"

    try:
        if name == "list_project_files":
            return _pt_list_files(project_dir)
        elif name == "read_project_file":
            return _pt_read_file(project_dir, arguments.get("path", ""))
        elif name == "edit_project_file":
            return _pt_edit_file(project_dir, arguments.get("path", ""), arguments.get("content", ""))
        elif name == "check_pod_status":
            pod_name = _safe_pod_name(project_name) if project_name else f"aelimini-{_agent_state.get('session_id', '')}"
            status = get_pod_status_by_name(pod_name)
            if status["exists"] and status["state"] == "Running":
                resp = http_get(host_port, "/health") if host_port else "No port"
                if resp.startswith("HTTP 200"):
                    return f"POD_RUNNING: {pod_name} is up and healthy on port {host_port}."
                else:
                    return f"POD_UNHEALTHY: {pod_name} exists on port {host_port} but health check failed: {resp[:300]}"
            elif status["exists"]:
                return f"POD_STOPPED: {pod_name} exists but state is '{status['state']}'."
            else:
                return f"POD_NOT_FOUND: No pod named {pod_name}."
        elif name == "get_container_logs":
            pod_name = _safe_pod_name(project_name) if project_name else f"aelimini-{_agent_state.get('session_id', '')}"
            return get_pod_logs_by_name(pod_name, arguments.get("tail", 80))
        else:
            return f"Unknown tool: {name}"
    except Exception as e:
        return f"Error executing {name}: {e}"


# ── Tool executor implementations ────────────────────────────────────

def _pt_list_files(project_dir: Path) -> str:
    files = []
    for item in sorted(project_dir.rglob("*")):
        if item.is_file() and not item.name.startswith("."):
            rel = str(item.relative_to(project_dir))
            size = item.stat().st_size
            files.append(f"  {rel} ({size} bytes)")
    return f"Project files:\n" + "\n".join(files) if files else "No files found"


def _pt_read_file(project_dir: Path, path: str) -> str:
    if not path or path in (".", "/", ""):
        return "Error: please specify a file path."
    target = project_dir / path
    try:
        target.resolve().relative_to(project_dir.resolve())
    except ValueError:
        return "Access denied: path outside project"
    if not target.exists():
        return f"File not found: {path}"
    if target.is_dir():
        return f"'{path}' is a directory."
    content = target.read_text()
    if len(content) > 16000:
        content = content[:16000] + f"\n... (truncated, {len(content)} chars)"
    return content


def _pt_edit_file(project_dir: Path, path: str, content: str) -> str:
    if not path or path in (".", "/", ""):
        return "Error: please specify a file path."
    target = project_dir / path
    try:
        target.resolve().relative_to(project_dir.resolve())
    except ValueError:
        return "Access denied: path outside project"
    if target.is_dir():
        return f"'{path}' is a directory."
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)
    return f"Written: {path} ({len(content)} chars)"
