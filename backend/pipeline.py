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

router = APIRouter()


@router.post("/api/direct/start")
async def direct_start(request: Request):
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
async def direct_stream(message: str, project_dir: str):
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

        # Site map — agent's primary orientation (compact file/function tree)
        site_map_path = PROD_ROOT / "SITE_MAP.md"
        if site_map_path.exists():
            system_prompt += "\n\n[SITE MAP]\n" + site_map_path.read_text()

        # SPEC — what the project does
        spec_path = PROD_ROOT / "SPEC.md"
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

        try:
            while action_turns < max_turns:
                total_turns += 1
                yield sse_event("turn", {"turn": total_turns, "action_turns": action_turns, "max": max_turns})

                raw = await asyncio.to_thread(
                    call_llm, selected, prov["api_key"], prov["base_url"],
                    prov["model"], messages, DIRECT_TOOL_DEFS, 0.3,
                )
                parsed = extract_response(raw)

                if parsed["type"] == "text":
                    _last_response_text = parsed["content"]
                    yield sse_event("response", {"content": parsed["content"]})
                    break

                if parsed["content"] and parsed["content"].strip():
                    yield sse_event("thinking", {"content": parsed["content"].strip()})

                assistant_msg = {"role": "assistant", "content": parsed["content"] or ""}
                assistant_msg["tool_calls"] = [
                    {"id": tc["id"], "type": "function",
                     "function": {"name": tc["function_name"], "arguments": json.dumps(tc["arguments"])}}
                    for tc in parsed["tool_calls"]
                ]
                messages.append(assistant_msg)

                all_readonly = all(_is_readonly_tool_call(tc) for tc in parsed["tool_calls"])

                for tc in parsed["tool_calls"]:
                    name = tc["function_name"]
                    args = tc["arguments"]
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
                        result = f"Tool error in {name}: {e}"

                    yield sse_event("tool_result", {"name": name, "result": result[:TRUNCATE_TOOL_RESULT]})
                    messages.append({"role": "tool", "tool_call_id": tc["id"], "content": result})

                    _used_any_tools = True
                    # Track if agent made code changes (for auto-test trigger)
                    if name in ("edit_file", "patch_file") and not result.startswith("ERROR"):
                        _made_code_changes = True

                if not all_readonly:
                    action_turns += 1

            # ── TEST PHASE (runs after agent loop, regardless of how it ended) ──
            # If agent made code changes: restart branch, run tests, feed failures back.
            # Uses its own loop so fix cycles re-enter the agent loop above.
            while (_made_code_changes and _test_fix_iteration < _max_test_fix):
                try:
                    from test_agent import plan_tests, run_tests, format_failures_as_message, load_source_batch

                    # Restart branch so tests hit the new code
                    if project_path.resolve() == BRANCH_ROOT.resolve():
                        import subprocess as _test_sp
                        yield sse_event("test_phase", {"status": "deploying_branch"})
                        try:
                            _test_sp.run(
                                ["systemctl", "--user", "restart", "aelidirect-branch.service"],
                                check=True, timeout=SUBPROCESS_TIMEOUT,
                            )
                            await asyncio.sleep(2)
                        except Exception:
                            pass

                    _test_fix_iteration += 1
                    yield sse_event("test_phase", {
                        "status": "planning", "iteration": _test_fix_iteration,
                    })

                    _test_context = (
                        f"Task: {msg}\n"
                        f"Agent response: {_last_response_text[:1000]}\n"
                        f"Test iteration: {_test_fix_iteration}"
                    )
                    source_batch = await asyncio.to_thread(load_source_batch, "platform")
                    _test_port = BRANCH_PORT if project_path.resolve() == BRANCH_ROOT.resolve() else PROD_PORT
                    plan = await plan_tests(
                        scope=msg, context=_test_context,
                        source_batch=source_batch, target_port=_test_port,
                    )

                    if plan.get("error"):
                        yield sse_event("test_phase", {"status": "error", "error": plan.get("error", "")[:200]})
                        break

                    tc_count = len(plan.get("test_cases", []))
                    yield sse_event("test_phase", {
                        "status": "running", "test_count": tc_count,
                        "iteration": _test_fix_iteration,
                    })

                    results = await run_tests(plan, target_port=_test_port)
                    passed = sum(1 for r in results if r.get("status") == "pass")
                    failed = [r for r in results if r.get("status") in ("fail", "error")]

                    _test_evidence.append({
                        "iteration": _test_fix_iteration,
                        "plan_summary": plan.get("summary", ""),
                        "total": len(results), "passed": passed, "failed": len(failed),
                        "details": results,
                    })

                    if not failed:
                        yield sse_event("test_phase", {
                            "status": "all_passed", "passed": passed,
                            "iteration": _test_fix_iteration,
                        })
                        break  # Tests passed, exit test loop

                    # Tests failed — feed failures back to agent
                    failure_msg = format_failures_as_message(results, plan)
                    yield sse_event("test_feedback", {
                        "status": "failures_found", "passed": passed,
                        "failed": len(failed), "iteration": _test_fix_iteration,
                    })
                    # Inject into same conversation (all prior context preserved)
                    if _last_response_text:
                        messages.append({"role": "assistant", "content": _last_response_text})
                    messages.append({"role": "user", "content": failure_msg})
                    action_turns = 0  # Reset turns

                    # Re-enter agent loop for fix attempt
                    _last_response_text = ""
                    while action_turns < max_turns:
                        total_turns += 1
                        yield sse_event("turn", {"turn": total_turns, "action_turns": action_turns, "max": max_turns})
                        raw = await asyncio.to_thread(
                            call_llm, selected, prov["api_key"], prov["base_url"],
                            prov["model"], messages, DIRECT_TOOL_DEFS, 0.3,
                        )
                        parsed = extract_response(raw)

                        if parsed["type"] == "text":
                            _last_response_text = parsed["content"]
                            yield sse_event("response", {"content": parsed["content"]})
                            break

                        if parsed["content"] and parsed["content"].strip():
                            yield sse_event("thinking", {"content": parsed["content"].strip()})

                        assistant_msg = {"role": "assistant", "content": parsed["content"] or ""}
                        assistant_msg["tool_calls"] = [
                            {"id": tc["id"], "type": "function",
                             "function": {"name": tc["function_name"], "arguments": json.dumps(tc["arguments"])}}
                            for tc in parsed["tool_calls"]
                        ]
                        messages.append(assistant_msg)
                        all_readonly = all(_is_readonly_tool_call(tc) for tc in parsed["tool_calls"])

                        for tc in parsed["tool_calls"]:
                            name = tc["function_name"]
                            args = tc["arguments"]
                            yield sse_event("tool_call", {"name": name, "args": args})
                            try:
                                result = execute_tool(name, args, project_dir=project_path)
                            except Exception as e:
                                result = f"Tool error in {name}: {e}"
                            yield sse_event("tool_result", {"name": name, "result": result[:TRUNCATE_TOOL_RESULT]})
                            messages.append({"role": "tool", "tool_call_id": tc["id"], "content": result})
                            _used_any_tools = True

                        if not all_readonly:
                            action_turns += 1

                    # After fix attempt, loop back to test again
                    continue

                except Exception as _te:
                    import logging as _tlog
                    _tlog.getLogger("uvicorn").error(f"[test-phase] Error: {_te}")
                    yield sse_event("test_phase", {"status": "error", "error": str(_te)[:200]})
                    break
            # ── END TEST PHASE ──────────────────────────────────

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
                    yield sse_event("td_review", {"status": "running"})
                    _review_input = f"Task: {msg}\n\nAgent Result:\n{_final_response[:8000]}"
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
                                        if _det.get("assertion_failed"):
                                            _review_input += f"    FAIL: {_det['assertion_failed'][:200]}\n"
                        _review_input = _review_input[:TRUNCATE_TD_INPUT]

                    _review_raw = await asyncio.to_thread(
                        call_llm, selected, prov["api_key"], prov["base_url"],
                        prov["model"], [
                            {"role": "system", "content": TODO_TD_REVIEW_PROMPT},
                            {"role": "user", "content": _review_input},
                        ], None, 0.3,
                    )
                    _td_review_text = extract_response(_review_raw)["content"]
                    yield sse_event("td_review", {
                        "status": "complete",
                        "review": _td_review_text,
                    })
                except Exception as _tde:
                    import logging as _tdlog
                    _tdlog.getLogger("uvicorn").error(f"[td-review] Pipeline error: {_tde}")
                    yield sse_event("td_review", {"status": "error", "error": str(_tde)[:200]})

            yield sse_event("done", {
                "turns": total_turns,
                "action_turns": action_turns,
                "test_evidence": _test_evidence if _test_evidence else None,
                "td_review": _td_review_text[:500] if _td_review_text else None,
            })
            try:
                _save_conversation(project_dir, msg, messages, test_evidence=_test_evidence)
                # Regenerate docs in background after chat completion
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
            yield sse_event("error", {"message": str(e), "traceback": traceback.format_exc()})
            try:
                _save_conversation(project_dir, msg, messages)
            except Exception:
                pass

    return StreamingResponse(event_generator(), media_type="text/event-stream")
