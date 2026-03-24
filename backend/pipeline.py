"""
The single chat pipeline — direct_start, direct_stream, and event_generator.
"""

import json
import re
import asyncio
from pathlib import Path
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from starlette.responses import Response

from constants import (
    PROD_ROOT, BRANCH_ROOT, BRANCH_PORT, PROD_PORT,
    PLATFORM_SOURCE_FILES,
    MAX_ACTION_TURNS, MAX_TEST_FIX_ITERATIONS,
    SUBPROCESS_TIMEOUT, SUBPROCESS_TIMEOUT_LONG,
    MEMORY_DIR, SAFE_NAME_MAX_LENGTH,
    TRUNCATE_TOOL_RESULT, TRUNCATE_STDOUT, TRUNCATE_STDERR,
    TRUNCATE_GIT_DIFF, TRUNCATE_TD_INPUT,
)
from state import (
    config, _get_provider, _pod_url, sse_event,
    _is_readonly_tool_call, _direct_state,
    DIRECT_AGENT_PROMPT, DIRECT_TOOL_DEFS, TODO_TD_REVIEW_PROMPT,
)
from llm_client import call_llm, extract_response
from tools import execute_tool
from pod import spin_up_pod, http_get, get_available_port
from history import _save_conversation, _load_conversation_history
from docs import _regenerate_docs

import logging
_log = logging.getLogger("uvicorn")

router = APIRouter()


def _trim_messages(messages: list) -> list:
    """Trim stale/redundant content from messages to save context window.

    Trims:
    - <think> blocks → 1-line summary (19% savings)
    - File reads that are FOLLOWED BY a patch to same file (order-aware) (39%)
    - Bash output that is purely confirmatory — NOT search/grep results (11%)
    - old_text from patch_file args (10%)

    Never trims: last 6 messages (LLM needs recent context), user messages, errors.
    """
    if len(messages) <= 6:
        return messages

    # Build ordered list of patch positions per file
    # patch_positions[file_path] = [index_of_first_patch, index_of_second_patch, ...]
    patch_positions = {}
    for i, m in enumerate(messages):
        if m.get("role") == "assistant" and m.get("tool_calls"):
            for tc in m["tool_calls"]:
                fn = tc.get("function", {})
                if fn.get("name") == "patch_file":
                    try:
                        args = json.loads(fn.get("arguments", "{}"))
                        path = args.get("path", "")
                        if path:
                            patch_positions.setdefault(path, []).append(i)
                    except (json.JSONDecodeError, TypeError):
                        pass

    # Bash commands that are purely confirmatory (output not useful after success)
    _CONFIRMATORY_BASH = (
        "python3 -m py_compile", "git add", "git commit", "mkdir", "cd ",
        "systemctl", "pip install", "npm install",
    )

    # Never trim last 6 messages — LLM needs its most recent context
    protect_from = len(messages) - 6

    trimmed = []
    for i, m in enumerate(messages):
        role = m.get("role", "")

        # Never trim protected recent messages
        if i >= protect_from:
            trimmed.append(m)
            continue

        # Keep user and system messages as-is
        if role in ("user", "system"):
            trimmed.append(m)
            continue

        # Trim assistant messages
        if role == "assistant":
            content = m.get("content", "") or ""
            tool_calls = m.get("tool_calls", [])

            # Strip <think> blocks → first line summary
            if content.strip().startswith("<think"):
                lines = content.replace("<think>", "").replace("</think>", "").strip().split("\n")
                summary = next((l.strip() for l in lines if l.strip()), "")
                new_m = dict(m)
                new_m["content"] = f"(planning: {summary[:100]})" if summary else ""
                # Trim old_text from patch_file args
                if tool_calls:
                    new_calls = []
                    for tc in tool_calls:
                        fn = tc.get("function", {})
                        if fn.get("name") == "patch_file":
                            try:
                                args = json.loads(fn.get("arguments", "{}"))
                                if "old_text" in args and len(args["old_text"]) > 100:
                                    args["old_text"] = f"(trimmed {len(args['old_text'])} chars)"
                                    new_tc = dict(tc)
                                    new_tc["function"] = dict(fn)
                                    new_tc["function"]["arguments"] = json.dumps(args)
                                    new_calls.append(new_tc)
                                    continue
                            except (json.JSONDecodeError, TypeError):
                                pass
                        new_calls.append(tc)
                    new_m["tool_calls"] = new_calls
                trimmed.append(new_m)
            else:
                trimmed.append(m)
            continue

        # Trim tool results
        if role == "tool":
            content = m.get("content", "") or ""

            # Trim confirmatory bash success (NOT grep/search/informational output)
            if "exit code: 0" in content and len(content) > 200:
                # Check if the bash command was confirmatory
                # Look at the preceding assistant message for the command
                prev = messages[i - 1] if i > 0 else {}
                is_confirmatory = False
                if prev.get("tool_calls"):
                    for tc in prev["tool_calls"]:
                        fn = tc.get("function", {})
                        if fn.get("name") == "bash":
                            try:
                                cmd = json.loads(fn.get("arguments", "{}")).get("command", "")
                                if any(cmd.strip().startswith(p) for p in _CONFIRMATORY_BASH):
                                    is_confirmatory = True
                            except (json.JSONDecodeError, TypeError):
                                pass
                if is_confirmatory:
                    new_m = dict(m)
                    new_m["content"] = "exit code: 0 (confirmatory output trimmed)"
                    trimmed.append(new_m)
                    continue

            # Trim file reads ONLY if a patch to that file came AFTER this read
            if content.startswith("===") and " — lines " in content[:100]:
                header = content.split("\n")[0]
                stale = False
                for pf, positions in patch_positions.items():
                    if pf and pf in header:
                        # Stale only if ANY patch to this file is at a LATER index
                        if any(p > i for p in positions):
                            stale = True
                            break
                if stale:
                    new_m = dict(m)
                    new_m["content"] = f"(stale read — file patched later)"
                    trimmed.append(new_m)
                    continue

            trimmed.append(m)
            continue

        trimmed.append(m)

    return trimmed


@router.post("/api/direct/start")
async def create_or_select_project(request: Request):
    from tools import PROJECTS_ROOT, init_project_dir, write_project_env, set_active_project, read_project_env

    data = await request.json()
    message = data.get("message", "")
    project_dir_name = data.get("project_dir", "")
    raw_name = data.get("project_name", "").strip()

    if project_dir_name:
        project_dir = PROJECTS_ROOT / project_dir_name
        if not project_dir.exists():
            return {"error": "Project not found"}
        env = read_project_env(project_dir)
        project_name = env.get("project_name", project_dir_name)
    else:
        # Use explicit project_name if provided, else derive from message
        if raw_name:
            project_name = raw_name
            safe_name = re.sub(r'[^a-zA-Z0-9_-]', '_', raw_name.lower())[:SAFE_NAME_MAX_LENGTH]
        else:
            words = re.sub(r'[^a-zA-Z0-9 ]', '', message.lower()).split()[:4]
            safe_name = "_".join(words) if words else "project"
            project_name = " ".join(w.capitalize() for w in words) if words else "Project"
        project_dir = PROJECTS_ROOT / safe_name
        if project_dir.exists():
            i = 2
            while (PROJECTS_ROOT / f"{safe_name}_{i}").exists():
                i += 1
            safe_name = f"{safe_name}_{i}"
            project_dir = PROJECTS_ROOT / safe_name
        init_project_dir(project_dir)
        write_project_env(project_dir, project_name)
        project_dir_name = safe_name

    set_active_project(project_dir)
    env = read_project_env(project_dir)
    port = int(env.get("pod_port", 0)) or get_available_port(project_name) or 0

    _direct_state["project_dir"] = project_dir
    _direct_state["project_name"] = project_name
    _direct_state["port"] = port

    return {
        "project_dir": project_dir_name,
        "project_name": project_name,
        "port": port,
        "stream_url": f"/api/direct/stream?message={__import__('urllib.parse', fromlist=['quote']).quote(message)}&project_dir={project_dir_name}",
    }


@router.get("/api/direct/stream")
async def run_chat_pipeline(message: str, project_dir: str):
    from tools import PROJECTS_ROOT, set_active_project, read_project_env, file_cache_wipe_branch

    project_path = PROJECTS_ROOT / project_dir
    if not project_path.exists():
        return Response(content=json.dumps({"error": "Project not found"}), status_code=404)

    prov = _get_provider()
    if not prov["api_key"]:
        return Response(content=json.dumps({"error": "No API key configured"}), status_code=400)

    selected = config["selected"]

    # Platform self-editing: redirect to branch, auto-wipe if no testing in progress
    if project_dir == "aelidirect_platform" and BRANCH_ROOT.exists():
        import hashlib
        branch_has_newer = False
        for rel in PLATFORM_SOURCE_FILES:
            prod_f = PROD_ROOT / rel
            branch_f = BRANCH_ROOT / rel
            if prod_f.exists() and branch_f.exists():
                if hashlib.md5(branch_f.read_bytes()).hexdigest() != hashlib.md5(prod_f.read_bytes()).hexdigest():
                    if branch_f.stat().st_mtime > prod_f.stat().st_mtime:
                        branch_has_newer = True
                        break
        if not branch_has_newer:
            # Auto-wipe: copy prod → branch
            import shutil
            for rel in PLATFORM_SOURCE_FILES:
                prod_f = PROD_ROOT / rel
                branch_f = BRANCH_ROOT / rel
                if prod_f.exists():
                    branch_f.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(str(prod_f), str(branch_f))
            file_cache_wipe_branch()
            import logging
            logging.getLogger("uvicorn").info("[platform] Auto-wiped branch from prod (no testing in progress)")
        # Agent works on branch files directly
        project_path = BRANCH_ROOT

    set_active_project(project_path)

    env = read_project_env(PROJECTS_ROOT / project_dir)  # metadata stays in original project dir
    project_name = env.get("project_name", project_dir)
    port = int(env.get("pod_port", 0)) or _direct_state.get("port", 0)

    _direct_state["project_dir"] = project_path
    _direct_state["project_name"] = project_name
    _direct_state["port"] = port
    msg = message or ""

    async def event_generator():
        system_prompt = DIRECT_AGENT_PROMPT

        # Docs root — branch docs when editing platform, prod docs otherwise
        _docs_root = BRANCH_ROOT if project_path.resolve() == BRANCH_ROOT.resolve() else PROD_ROOT

        # Site map — agent's primary orientation (compact file/function tree)
        site_map_path = _docs_root / "SITE_MAP.md"
        if site_map_path.exists():
            system_prompt += "\n\n[SITE MAP]\n" + site_map_path.read_text()

        # SPEC — what the project does
        spec_path = _docs_root / "SPEC.md"
        if spec_path.exists():
            system_prompt += "\n\n[PROJECT SPEC]\n" + spec_path.read_text()

        # Long-term memory
        mem_dir = MEMORY_DIR / project_path.name
        if mem_dir.exists():
            memories = []
            for f in sorted(mem_dir.glob("*.md")):
                memories.append(f"[{f.stem}]: {f.read_text()[:500]}")
            if memories:
                system_prompt += "\n\n[LONG-TERM MEMORY]\n" + "\n".join(memories)

        # Recent conversation history (trimmed to last 5 for efficiency)
        conv_history = await asyncio.to_thread(
            _load_conversation_history, project_path.name, prov, selected
        )
        if conv_history:
            # Cap at ~10k tokens to leave room for actual work
            if len(conv_history) > 40000:
                conv_history = conv_history[-40000:]
            system_prompt += "\n\n[RECENT CONVERSATION HISTORY]\n" + conv_history

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": msg},
        ]
        action_turns = 0
        max_turns = MAX_ACTION_TURNS
        total_turns = 0
        _made_code_changes = False  # Track if agent wrote/edited files
        _used_any_tools = False     # Track if agent called any tools at all
        _test_fix_iteration = 0
        _max_test_fix = MAX_TEST_FIX_ITERATIONS
        _test_evidence = []  # Collected for TD review
        _last_response_text = ""    # Captures final agent response for TD review
        _phase = "coding"           # Current phase: coding, testing, post_test

        try:
            _sys_prompt_len = len(system_prompt)
            _log.info(f"[trace] START project={project_dir} msg={msg[:80]} "
                      f"system_prompt={_sys_prompt_len} chars model={prov['model']}")
            _log.info(f"[trace] CONTEXT site_map={'yes' if 'SITE MAP' in system_prompt else 'no'} "
                      f"spec={'yes' if 'PROJECT SPEC' in system_prompt else 'no'} "
                      f"memory={'yes' if 'LONG-TERM MEMORY' in system_prompt else 'no'} "
                      f"history={'yes' if 'CONVERSATION HISTORY' in system_prompt else 'no'}")
            # ── PLANNING TURN (disabled — model hallucinates tool calls and adds unrelated fixes) ──
            _plan_text = ""

            # ── CODING (tools enabled) ──
            yield sse_event("phase", {"phase": "coding"})
            _log.info(f"[trace] PHASE coding tools={len(DIRECT_TOOL_DEFS)} max_turns={max_turns}")
            while action_turns < max_turns:
                total_turns += 1
                yield sse_event("turn", {"turn": total_turns, "action_turns": action_turns, "max": max_turns})

                # Trim stale content before each LLM call to save context window
                _trimmed = _trim_messages(messages)
                _trimmed_chars = sum(len(json.dumps(m)) for m in _trimmed)
                _log.info(f"[trace] LLM_CALL turn={total_turns} action={action_turns} "
                          f"msgs={len(_trimmed)} chars={_trimmed_chars}")
                raw = await asyncio.to_thread(
                    call_llm, selected, prov["api_key"], prov["base_url"],
                    prov["model"], _trimmed, DIRECT_TOOL_DEFS, 0.3,
                )
                parsed = extract_response(raw)
                _log.info(f"[trace] LLM_RESPONSE type={parsed['type']} "
                          f"content_len={len(parsed.get('content', '') or '')} "
                          f"tool_calls={len(parsed.get('tool_calls', []))}")

                if parsed["type"] == "text":
                    _last_response_text = parsed["content"]
                    _log.info(f"[trace] TEXT_RESPONSE len={len(_last_response_text)} preview={_last_response_text[:100]}")
                    yield sse_event("response", {"content": parsed["content"]})
                    break

                if parsed["content"] and parsed["content"].strip():
                    _think_preview = parsed["content"].strip()[:100]
                    _log.info(f"[trace] THINKING len={len(parsed['content'])} preview={_think_preview}")
                    yield sse_event("thinking", {"content": parsed["content"].strip()})

                assistant_msg = {"role": "assistant", "content": parsed["content"] or ""}
                assistant_msg["tool_calls"] = [
                    {"id": tc["id"], "type": "function",
                     "function": {"name": tc["function_name"], "arguments": json.dumps(tc["arguments"])}}
                    for tc in parsed["tool_calls"]
                ]
                messages.append(assistant_msg)

                all_readonly = all(_is_readonly_tool_call(tc) for tc in parsed["tool_calls"])
                _tool_names = [tc["function_name"] for tc in parsed["tool_calls"]]
                _log.info(f"[trace] TOOL_CALLS count={len(_tool_names)} names={_tool_names} readonly={all_readonly}")

                for tc in parsed["tool_calls"]:
                    name = tc["function_name"]
                    args = tc["arguments"]
                    _args_preview = json.dumps(args)[:150]
                    _log.info(f"[trace] TOOL_EXEC name={name} args={_args_preview}")
                    yield sse_event("tool_call", {"name": name, "args": args})

                    try:
                        if name == "deploy_pod" and project_path.name == "aelidirect_platform":
                            result = "ERROR: This is the platform itself — use restart_platform() instead of deploy_pod(). The platform runs as a systemd service, not a pod."
                        elif name == "deploy_pod":
                            from tools import write_project_env as _wpd
                            _env = read_project_env(project_path)
                            _port = int(_env.get("pod_port", 0)) or get_available_port(project_name) or 0
                            if _port:
                                _ver = int(_env.get("deploy_version", "0")) + 1
                                deploy_result = spin_up_pod(project_path, project_name, _port, _ver)
                                if deploy_result["success"]:
                                    _direct_state["port"] = _port
                                    _env2 = read_project_env(project_path)
                                    _extra = {k: v for k, v in _env2.items()
                                              if k not in ("project_name", "project_dir", "tech_stack", "os", "python", "pod_port", "deploy_version")}
                                    _extra["Pod Port"] = str(_port)
                                    _extra["Deploy Version"] = str(_ver)
                                    _wpd(project_path, _env2.get("project_name", project_name),
                                         _env2.get("tech_stack", "auto"), _extra if _extra else None)
                                    result = f"DEPLOYED: {_pod_url(_port)} (v{_ver})\nPod: {deploy_result['pod_name']}"
                                    yield sse_event("pod_url", {"url": _pod_url(_port)})
                                else:
                                    result = f"FAILED at {deploy_result['phase']}: {deploy_result['message']}\nLogs: {deploy_result.get('logs', '')[:500]}"
                            else:
                                result = "FAILED: No available ports"
                        elif name == "restart_platform":
                            import subprocess as _sp
                            try:
                                # Always restart the BRANCH (10101), never prod (10100)
                                # Prod is what we're running on — restarting it kills this conversation
                                r = _sp.run(
                                    ["systemctl", "--user", "restart", "aelidirect-branch"],
                                    capture_output=True, text=True, timeout=SUBPROCESS_TIMEOUT,
                                )
                                if r.returncode == 0:
                                    import time as _time
                                    _time.sleep(2)
                                    # Verify branch came up
                                    _check = http_get(BRANCH_PORT, "/")
                                    if _check.startswith("HTTP 200"):
                                        result = "Branch restarted on port 10101 and healthy. Test your changes there, then use TO PROD button when ready."
                                    else:
                                        result = f"Branch restarted but health check failed: {_check[:200]}. Check for syntax errors."
                                else:
                                    result = f"Branch restart failed: {r.stderr}"
                            except Exception as e:
                                result = f"Restart error: {e}"
                        elif name == "http_check":
                            _port = _direct_state.get("port", 0)
                            result = http_get(_port, args.get("path", "/")) if _port else "No pod running — call deploy_pod first"
                        elif name == "bash":
                            import subprocess as _sp
                            cmd = args.get("command", "")
                            try:
                                r = _sp.run(cmd, shell=True, capture_output=True, text=True, timeout=SUBPROCESS_TIMEOUT_LONG, cwd=str(project_path))
                                result = f"exit code: {r.returncode}\n"
                                if r.stdout: result += f"stdout:\n{r.stdout[:TRUNCATE_STDOUT]}\n"
                                if r.stderr: result += f"stderr:\n{r.stderr[:TRUNCATE_STDERR]}"
                                if not r.stdout and not r.stderr: result += "(no output)"
                            except _sp.TimeoutExpired:
                                result = "Command timed out (60s limit)"
                        elif name == "git_status":
                            import subprocess as _sp
                            if not (project_path / ".git").exists():
                                _sp.run(["git", "init"], cwd=str(project_path), capture_output=True)
                                _sp.run(["git", "add", "."], cwd=str(project_path), capture_output=True)
                                _sp.run(["git", "commit", "-m", "Initial commit"],
                                       cwd=str(project_path), capture_output=True,
                                       env={**__import__('os').environ, "GIT_AUTHOR_NAME": "aelidirect",
                                            "GIT_AUTHOR_EMAIL": "aelidirect@local",
                                            "GIT_COMMITTER_NAME": "aelidirect",
                                            "GIT_COMMITTER_EMAIL": "aelidirect@local"})
                            r = _sp.run(["git", "status"], cwd=str(project_path), capture_output=True, text=True, timeout=10)
                            result = r.stdout + r.stderr
                        elif name == "git_diff":
                            import subprocess as _sp
                            r = _sp.run(["git", "diff"], cwd=str(project_path), capture_output=True, text=True, timeout=10)
                            result = r.stdout[:TRUNCATE_GIT_DIFF] or "(no changes)"
                        elif name == "git_log":
                            import subprocess as _sp
                            n = int(args.get("n", 5))
                            r = _sp.run(["git", "log", "--oneline", f"-{n}"], cwd=str(project_path), capture_output=True, text=True, timeout=10)
                            result = r.stdout or "(no commits)"
                        elif name == "git_commit":
                            import subprocess as _sp
                            _commit_msg = args.get("message", "Update")
                            _sp.run(["git", "add", "."], cwd=str(project_path), capture_output=True)
                            r = _sp.run(["git", "commit", "-m", _commit_msg],
                                       cwd=str(project_path), capture_output=True, text=True, timeout=SUBPROCESS_TIMEOUT,
                                       env={**__import__('os').environ, "GIT_AUTHOR_NAME": "aelidirect",
                                            "GIT_AUTHOR_EMAIL": "aelidirect@local",
                                            "GIT_COMMITTER_NAME": "aelidirect",
                                            "GIT_COMMITTER_EMAIL": "aelidirect@local"})
                            result = r.stdout + r.stderr
                        elif name == "memory_save":
                            key = args.get("key", "").replace("/", "_").replace("..", "")
                            content = args.get("content", "")
                            mem_dir = MEMORY_DIR / project_path.name
                            mem_dir.mkdir(exist_ok=True)
                            (mem_dir / f"{key}.md").write_text(content)
                            result = f"Saved memory: {key} ({len(content)} chars)"
                        elif name == "memory_load":
                            key = args.get("key", "").replace("/", "_").replace("..", "")
                            mem_path = MEMORY_DIR / project_path.name / f"{key}.md"
                            result = mem_path.read_text() if mem_path.exists() else f"Memory '{key}' not found"
                        elif name == "memory_list":
                            mem_dir = MEMORY_DIR / project_path.name
                            if mem_dir.exists():
                                keys = [f.stem for f in sorted(mem_dir.glob("*.md"))]
                                result = "Saved memories:\n" + "\n".join(f"  - {k}" for k in keys) if keys else "No memories saved"
                            else:
                                result = "No memories saved"
                        elif name == "test_agent":
                            from test_agent import handle_test_agent
                            result = await handle_test_agent(args)
                        else:
                            result = execute_tool(name, args, project_dir=project_path)
                    except Exception as e:
                        _log.error(f"[trace] TOOL_ERROR name={name} error={e}")
                        result = f"Tool error in {name}: {e}"

                    _result_preview = result[:150].replace('\n', ' ')
                    _log.info(f"[trace] TOOL_RESULT name={name} len={len(result)} preview={_result_preview}")
                    yield sse_event("tool_result", {"name": name, "result": result[:TRUNCATE_TOOL_RESULT]})
                    messages.append({"role": "tool", "tool_call_id": tc["id"], "content": result})

                    _used_any_tools = True
                    if name in ("edit_file", "patch_file") and not result.startswith("ERROR"):
                        _made_code_changes = True
                        _log.info(f"[trace] CODE_CHANGE tool={name} file={args.get('path', '?')}")

                if not all_readonly:
                    action_turns += 1
                    _log.info(f"[trace] ACTION_TURN incremented to {action_turns}")

            # ── TEST PHASE (runs after agent loop, regardless of how it ended) ──
            _msg_chars = sum(len(json.dumps(m)) for m in messages)
            _log.info(f"[trace] AGENT_LOOP_DONE turns={total_turns} action={action_turns} "
                      f"code_changes={_made_code_changes} tools_used={_used_any_tools} "
                      f"msgs={len(messages)} chars={_msg_chars} "
                      f"last_response={'text' if _last_response_text else 'none'}")
            # ── TEST PHASE REMOVED — using e2e trace logs instead ──

            # ── POST-TEST PHASE ──────────────────────────────────
            _phase = "post_test"
            _log.info(f"[trace] POST_PHASE code_changes={_made_code_changes} tools_used={_used_any_tools}")
            yield sse_event("phase", {"phase": "post_test"})

            # Extract final response text for TD review
            _final_response = _last_response_text
            if not _final_response:
                for _m in reversed(messages):
                    if _m.get("role") == "assistant" and _m.get("content", "").strip():
                        _final_response = _m["content"]
                        break

            # ── TD REVIEW (runs for every conversation that used tools) ──
            _td_review_text = None
            if _used_any_tools:
                try:
                    _log.info(f"[trace] TD_REVIEW_START tools_used={_used_any_tools}")
                    yield sse_event("td_review", {"status": "running"})
                    # Build full arc summary for TD: task → plan → changes → response → tests
                    _review_input = f"## Original Task\n{msg}\n\n"
                    if _plan_text:
                        _review_input += f"## Agent Plan\n{_plan_text[:2000]}\n\n"

                    # Summarize what the agent actually changed (extract from messages)
                    _changes = []
                    for _rm in messages:
                        if _rm.get("role") == "tool":
                            _rc = _rm.get("content", "")
                            if _rc.startswith("Patched "):
                                _changes.append(_rc[:200])
                            elif _rc.startswith("File written"):
                                _changes.append(_rc[:200])
                            elif "ERROR" in _rc[:20] or "Error" in _rc[:20]:
                                _changes.append(f"ERROR: {_rc[:200]}")
                    if _changes:
                        _review_input += "## Code Changes Made\n"
                        for _c in _changes:
                            _review_input += f"- {_c}\n"
                        _review_input += "\n"

                    if _final_response:
                        _review_input += f"## Agent Final Response\n{_final_response[:2000]}\n\n"
                    _review_input += f"## Test Fix Iterations: {_test_fix_iteration}\n"
                    if _test_evidence:
                        _review_input += "\n\n## Automated Test Results\n"
                        for _te in _test_evidence:
                            _review_input += (
                                f"\n### Test Iteration {_te.get('iteration', '?')}\n"
                                f"Plan: {_te.get('plan_summary', 'N/A')}\n"
                                f"Total: {_te.get('total', 0)}, Passed: {_te.get('passed', 0)}, "
                                f"Failed: {_te.get('failed', 0)}\n"
                            )
                            for _d in _te.get("details", []):
                                _status = _d.get("status", "?")
                                _review_input += f"- [{_status.upper()}] {_d.get('id', '?')}: {_d.get('name', '')}\n"
                                if _status != "pass":
                                    for _det in _d.get("details", []):
                                        if isinstance(_det, dict) and _det.get("assertion_failed"):
                                            _review_input += f"    FAIL: {_det['assertion_failed'][:200]}\n"
                        _review_input = _review_input[:TRUNCATE_TD_INPUT]

                    _review_raw = await asyncio.to_thread(
                        call_llm, selected, prov["api_key"], prov["base_url"],
                        prov["model"], [
                            {"role": "system", "content": TODO_TD_REVIEW_PROMPT},
                            {"role": "user", "content": _review_input},
                        ], None, 0.3,
                    )
                    _td_review_raw = extract_response(_review_raw)["content"]
                    # Strip hallucinated tool calls and think blocks from TD output
                    import re as _re
                    _td_review_text = _re.sub(r'<think>[\s\S]*?</think>', '', _td_review_raw)
                    _td_review_text = _re.sub(r'\[TOOL_CALL\][\s\S]*?\[/TOOL_CALL\]', '', _td_review_text)
                    _td_review_text = _td_review_text.strip()
                    if len(_td_review_text) < 50:
                        _log.warning(f"[pipeline] TD REVIEW produced no useful output. Raw length={len(_td_review_raw)}, cleaned={len(_td_review_text)}")
                        _td_review_text = f"TD review failed to produce valid output (model outputted tool calls instead of review text). Raw: {_td_review_raw[:500]}"
                    yield sse_event("td_review", {
                        "status": "complete",
                        "review": _td_review_text,
                    })
                except Exception as _tde:
                    import traceback as _tdb
                    _log.error(f"[pipeline] TD REVIEW ERROR error={_tde}\n{_tdb.format_exc()}")
                    yield sse_event("td_review", {"status": "error", "error": str(_tde)[:200]})

            _log.info(f"[trace] DONE turns={total_turns} action={action_turns} "
                      f"td={'yes' if _td_review_text else 'no'} "
                      f"td_len={len(_td_review_text) if _td_review_text else 0}")
            yield sse_event("done", {
                "turns": total_turns,
                "action_turns": action_turns,
                "test_evidence": _test_evidence if _test_evidence else None,
                "td_review": _td_review_text[:500] if _td_review_text else None,
            })
            try:
                _log.info(f"[trace] SAVE_CONVERSATION project={project_dir} msgs={len(messages)}")
                _save_conversation(project_dir, msg, messages, test_evidence=_test_evidence)
                # Regenerate docs only on branch — prod never generates docs
                if project_path.resolve() == BRANCH_ROOT.resolve():
                    _log.info(f"[trace] REGEN_DOCS triggered (branch project)")
                    loop = asyncio.get_event_loop()
                    loop.create_task(_regenerate_docs())
                # Restart branch if code changed but tests didn't run (no test phase triggered)
                # If test phase ran, it already restarted the branch before testing.
                if (project_path.resolve() == BRANCH_ROOT.resolve()
                        and _made_code_changes and _test_fix_iteration == 0):
                    import subprocess
                    try:
                        subprocess.run(["systemctl", "--user", "restart", "aelidirect-branch.service"],
                                       check=True, timeout=10)
                    except Exception:
                        pass
            except Exception:
                pass

        except Exception as e:
            import traceback
            _log.error(f"[trace] FATAL phase={_phase} turns={total_turns} action={action_turns} "
                       f"msgs={len(messages)} error={e}\n{traceback.format_exc()}")
            yield sse_event("error", {"message": str(e), "traceback": traceback.format_exc()})
            try:
                _save_conversation(project_dir, msg, messages)
            except Exception:
                pass

    return StreamingResponse(event_generator(), media_type="text/event-stream")
