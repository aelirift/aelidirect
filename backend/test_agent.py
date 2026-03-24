"""
Test Agent — two-phase automated testing for aelidirect.

Phase 1 (plan): Reads codebase in batch, takes scope + context, asks LLM to produce a test plan.
Phase 2 (run):  Executes the test plan — API tests via httpx, browser tests via Playwright, unit tests via direct import.

Can also feed failures back through the chat pipeline for auto-fix, then re-verify.
"""

import json
import asyncio
import httpx
import importlib
import subprocess
import sys
import traceback
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

# ── Config (from constants.py) ──────────────────────────────────────
from constants import (
    BRANCH_PORT, PROD_PORT, PROJECTS_ROOT, BACKEND_DIR,
    MAX_TEST_FIX_ITERATIONS, CODE_EXTENSIONS, SKIP_DIRS,
    PLATFORM_SOURCE_FILES, TRUNCATE_TODO_RESULT,
)
DEFAULT_PORT = BRANCH_PORT
BASE_URL = f"http://127.0.0.1:{DEFAULT_PORT}"
MAX_FIX_ITERATIONS = MAX_TEST_FIX_ITERATIONS

# Files that make up the platform source
PLATFORM_FILES = [
    "backend/main.py",
    "backend/tools.py",
    "backend/llm_client.py",
    "backend/direct_todo.py",
    "backend/pod.py",
    "frontend/index.html",
    "SPEC.md",
]


def _now():
    return datetime.now(timezone.utc).isoformat()[:19]


# ═══════════════════════════════════════════════════════════════════
# FILE BATCHING — load all relevant files in one shot
# ═══════════════════════════════════════════════════════════════════

def load_source_batch(scope: str = "platform") -> str:
    """Load all source files as a single concatenated string.

    Instead of dozens of grep/read_lines calls, this sends everything
    to the LLM in one shot. For the platform (~5 files, ~37k chars),
    this easily fits in context.
    """
    root = BACKEND_DIR.parent
    files_to_load = PLATFORM_FILES if scope == "platform" else _discover_project_files(scope)

    parts = []
    total_chars = 0
    for rel_path in files_to_load:
        fpath = root / rel_path
        if not fpath.exists():
            continue
        try:
            content = fpath.read_text()
            total_chars += len(content)
            lines = len(content.splitlines())
            parts.append(
                f"\n{'=' * 60}\n"
                f"=== {rel_path} ({len(content):,} chars, {lines} lines) ===\n"
                f"{'=' * 60}\n"
                f"{content}"
            )
        except Exception:
            parts.append(f"\n=== {rel_path} (read error) ===\n")

    header = f"=== SOURCE BATCH ({len(parts)} files, {total_chars:,} chars) ===\n"
    return header + "\n".join(parts)


def _discover_project_files(project_name: str) -> list[str]:
    """Find all source files in a project directory."""
    project_dir = PROJECTS_ROOT / project_name
    if not project_dir.exists():
        return []
    code_ext = CODE_EXTENSIONS
    skip_dirs = SKIP_DIRS
    files = []
    for f in sorted(project_dir.rglob("*")):
        if not f.is_file():
            continue
        parts = f.relative_to(project_dir).parts
        if any(p.startswith(".") or p in skip_dirs for p in parts):
            continue
        if f.suffix.lower() in code_ext:
            files.append(str(f.relative_to(BACKEND_DIR.parent)))
    return files


# ═══════════════════════════════════════════════════════════════════
# PHASE 1: PLAN — LLM generates test plan from source + context
# ═══════════════════════════════════════════════════════════════════

PLAN_SYSTEM_PROMPT = """You are a test planning agent. You receive:
1. The full source code of the system
2. A test scope (what area to focus on)
3. Context from the conversation (what the user reported, what's broken, recent changes)
4. The target port to test against (e.g. 10101 for branch, 10100 for prod)

Your job: produce a structured JSON test plan. Each test case should be concrete and executable.

CRITICAL: Every test MUST include a "setup" array that creates the preconditions needed for the test.
For example, to test a countdown timer you must FIRST:
- Create a todo item via the API
- Enable the heartbeat via the API
- Wait for the UI to update
Only THEN can you check if the countdown shows up.

IMPORTANT SETUP RULES:
- The context tells you the active project name. Use it in all API paths. Do NOT create new projects.
- There is NO "POST /api/projects" endpoint.
- For setup, use ONLY these endpoints (replace {project_dir} with the active project name):
  POST /api/direct/todos/{project_dir} {"task":"...", "category":"feature"} — create todo
  PUT /api/direct/todos/{project_dir}/{id} {"status":"...", "result":"..."} — update todo
  DELETE /api/direct/todos/{project_dir}/{id} — delete todo
  POST /api/direct/heartbeat/{project_dir} {"enabled":true, "interval_minutes":5} — configure heartbeat
  GET /api/direct/heartbeat/{project_dir} — read heartbeat state
- For browser tests, navigate to http://127.0.0.1:{port}/ and interact with the UI.
- Do NOT invent endpoints that don't exist. If unsure, skip the setup step.

Return ONLY valid JSON in this format:
{
  "summary": "Brief description of what we're testing and why",
  "test_cases": [
    {
      "id": "T1",
      "name": "descriptive test name",
      "type": "api|browser|unit",
      "description": "what this test verifies",
      "setup": [
        {"action": "create precondition", "details": {"method": "POST", "path": "/api/...", "body": {...}}}
      ],
      "steps": [
        {"action": "description of step", "details": {}}
      ],
      "expected": "what the correct behavior should be",
      "assertions": ["specific assertion 1", "specific assertion 2"]
    }
  ]
}

The "setup" array uses the same format as API steps: each has method, path, body.
Setup steps run BEFORE the test steps. They create todos, enable heartbeat, set config, etc.
Setup steps are NOT asserted — they just need to return 2xx.

Test types:
- "api": HTTP calls. Steps should include method, path, body, and expected status/response fields.
- "browser": Playwright actions. Steps should include selectors, actions (click, fill, wait_for), and what to check in the DOM. IMPORTANT: browser tests also have setup — use API calls in setup to create the data, then browser steps to verify the UI.
- "unit": Direct Python imports and function calls. Steps should include module, function, args, and expected return.

Use PORT_PLACEHOLDER in URLs — it will be replaced with the actual port at runtime.

Be thorough but practical. Only test things that can actually be verified programmatically.
For browser tests, use CSS selectors that exist in the actual HTML (you have the source).
For API tests, use actual endpoints from SITE_MAP.
For unit tests, use actual functions from the modules.
"""


async def plan_tests(
    scope: str,
    context: str = "",
    source_batch: str = "",
    target_port: int = DEFAULT_PORT,
) -> dict:
    """Phase 1: Ask LLM to generate a test plan.

    Args:
        scope: What to test (e.g. "heartbeat countdown", "chat pipeline", "todo CRUD")
        context: Conversation context — what's broken, what was reported, recent changes
        source_batch: Pre-loaded source code. If empty, loads automatically.
        target_port: Port to test against (10101 for branch, 10100 for prod)
    """
    user_msg = f"""## Test Scope
{scope}

## Target
Test against port {target_port} (http://127.0.0.1:{target_port})

## Context
{context if context else 'No specific context — do a general test sweep of the scope.'}
"""
    if source_batch:
        user_msg += f"\n## Source Code\n{source_batch}\n"

    # Call LLM to generate test plan
    from llm_client import call_llm, extract_response
    from state import config, _get_provider

    prov = _get_provider()
    messages = [
        {"role": "system", "content": PLAN_SYSTEM_PROMPT},
        {"role": "user", "content": user_msg},
    ]

    raw = call_llm(
        config["selected"], prov["api_key"], prov["base_url"],
        prov["model"], messages, None, 0.3,
    )
    parsed = extract_response(raw)
    content = parsed.get("content", "")

    # Extract JSON from response — handle markdown blocks, preamble, truncation
    json_str = content
    if "```json" in content:
        json_str = content.split("```json")[1].split("```")[0]
    elif "```" in content:
        json_str = content.split("```")[1].split("```")[0]

    # Try parsing as-is
    plan = None
    for attempt in [json_str.strip(), content.strip()]:
        try:
            plan = json.loads(attempt)
            break
        except json.JSONDecodeError:
            continue

    # Try finding JSON object in the text (handles preamble text before JSON)
    if plan is None:
        import re
        match = re.search(r'\{[\s\S]*"test_cases"[\s\S]*\}', content)
        if match:
            try:
                plan = json.loads(match.group(0))
            except json.JSONDecodeError:
                # Try fixing truncated JSON — add closing brackets
                truncated = match.group(0)
                for fix in ['}]}', '"}]}', '"}}]}']:
                    try:
                        plan = json.loads(truncated + fix)
                        break
                    except json.JSONDecodeError:
                        continue

    if plan is None:
        import logging
        logging.getLogger("uvicorn").warning(f"[test-agent] Failed to parse test plan. Content preview: {content[:500]}")
        plan = {"error": "Failed to parse test plan", "raw": content[:2000]}

    # Normalize alternate key names (LLM may use "tests" instead of "test_cases")
    if "test_cases" not in plan:
        for alt_key in ("tests", "test_plan", "testCases", "cases"):
            if alt_key in plan and isinstance(plan[alt_key], list):
                plan["test_cases"] = plan.pop(alt_key)
                break

    # Validate plan has test_cases
    if "test_cases" not in plan:
        import logging
        logging.getLogger("uvicorn").warning(f"[test-agent] Plan missing test_cases. Keys: {list(plan.keys())}. Raw: {json.dumps(plan)[:500]}")
        plan = {"error": "Test plan missing test_cases", "raw": json.dumps(plan)[:2000]}

    return plan


# ═══════════════════════════════════════════════════════════════════
# PHASE 2: RUN — Execute test plan
# ═══════════════════════════════════════════════════════════════════

async def _run_setup_steps(setup_steps: list, base_url: str) -> list[dict]:
    """Execute setup/precondition steps before a test. These create the conditions needed.
    Returns list of setup results (for debugging). Failures here are setup errors, not test failures."""
    results = []
    async with httpx.AsyncClient(timeout=30.0) as client:
        for step in setup_steps:
            details = step.get("details", {})
            method = details.get("method", "POST").upper()
            path = details.get("path", "/")
            body = details.get("body")
            url = f"{base_url}{path}"

            try:
                if method == "GET":
                    resp = await client.get(url)
                elif method == "POST":
                    resp = await client.post(url, json=body)
                elif method == "PUT":
                    resp = await client.put(url, json=body)
                elif method == "DELETE":
                    resp = await client.delete(url)
                elif method in ("NAVIGATE", "WAIT", "CLICK", "FILL", "BROWSER", "GOTO", "OPEN"):
                    # Browser actions in setup — skip, handled by browser test runner
                    results.append({"step": step.get("action", ""), "ok": True, "skipped": "browser action"})
                    continue
                else:
                    results.append({"step": step.get("action", ""), "error": f"Unknown method: {method}"})
                    continue

                results.append({
                    "step": step.get("action", ""),
                    "status_code": resp.status_code,
                    "ok": 200 <= resp.status_code < 300,
                    "body_preview": resp.text[:200],
                })
            except Exception as e:
                results.append({"step": step.get("action", ""), "error": str(e)})

    return results


async def run_tests(plan: dict, target_port: int = DEFAULT_PORT) -> list[dict]:
    """Phase 2: Execute each test case in the plan.

    For each test case:
    1. Run setup steps (create preconditions via API)
    2. Run test steps (verify behavior)

    Returns list of results: [{id, name, status, details, error}]
    """
    base_url = f"http://127.0.0.1:{target_port}"
    results = []
    for tc in plan.get("test_cases", []):
        tc_type = tc.get("type", "api")
        tc_id = tc.get("id", "?")
        tc_name = tc.get("name", "unnamed")

        try:
            # Run setup steps first (create preconditions)
            setup_steps = tc.get("setup", [])
            if setup_steps:
                setup_results = await _run_setup_steps(setup_steps, base_url)
                setup_failed = [s for s in setup_results if s.get("error") or not s.get("ok", True)]
                if setup_failed:
                    results.append({
                        "id": tc_id, "name": tc_name, "type": tc_type,
                        "expected": tc.get("expected", ""),
                        "status": "error",
                        "details": [{"step": "SETUP FAILED", "assertion_failed": f"Setup step failed: {setup_failed[0]}"}],
                        "setup_results": setup_results,
                    })
                    continue
                # Brief pause for server to process setup
                await asyncio.sleep(0.5)
            if tc_type == "api":
                result = await _run_api_test(tc, base_url)
            elif tc_type == "browser":
                result = await _run_browser_test(tc, base_url)
            elif tc_type == "unit":
                result = await _run_unit_test(tc)
            else:
                result = {"status": "skip", "details": f"Unknown test type: {tc_type}"}
        except Exception as e:
            result = {
                "status": "error",
                "details": [{"step": "exception", "assertion_failed": str(e)}],
                "traceback": traceback.format_exc(),
            }

        results.append({
            "id": tc_id,
            "name": tc_name,
            "type": tc_type,
            "expected": tc.get("expected", ""),
            **result,
        })

    return results


async def _run_api_test(tc: dict, base_url: str = BASE_URL) -> dict:
    """Execute an API test case."""
    details = []
    last_response = None

    async with httpx.AsyncClient(timeout=30.0) as client:
        for step in tc.get("steps", []):
            step_details = step.get("details", {})
            method = step_details.get("method", "GET").upper()
            path = step_details.get("path", "/")
            body = step_details.get("body")
            expected_status = step_details.get("expected_status")
            expected_fields = step_details.get("expected_fields", {})
            url = f"{base_url}{path}"

            if method == "GET":
                resp = await client.get(url)
            elif method == "POST":
                resp = await client.post(url, json=body)
            elif method == "PUT":
                resp = await client.put(url, json=body)
            elif method == "DELETE":
                resp = await client.delete(url)
            else:
                details.append({"step": step.get("action"), "error": f"Unknown method: {method}"})
                continue

            last_response = resp
            step_result = {
                "step": step.get("action", ""),
                "status_code": resp.status_code,
                "body_preview": resp.text[:500],
            }

            # Check expected status
            if expected_status and resp.status_code != expected_status:
                step_result["assertion_failed"] = f"Expected status {expected_status}, got {resp.status_code}"

            # Check expected fields in JSON response
            if expected_fields and resp.headers.get("content-type", "").startswith("application/json"):
                try:
                    data = resp.json()
                    for field, expected_val in expected_fields.items():
                        actual_val = data.get(field)
                        if expected_val == "__exists__":
                            if actual_val is None:
                                step_result.setdefault("assertion_failed", "")
                                step_result["assertion_failed"] += f" Field '{field}' missing."
                        elif expected_val == "__gt_zero__":
                            if not (isinstance(actual_val, (int, float)) and actual_val > 0):
                                step_result.setdefault("assertion_failed", "")
                                step_result["assertion_failed"] += f" Field '{field}' not > 0: {actual_val}"
                        elif actual_val != expected_val:
                            step_result.setdefault("assertion_failed", "")
                            step_result["assertion_failed"] += f" Field '{field}': expected {expected_val!r}, got {actual_val!r}"
                except Exception as e:
                    step_result["json_parse_error"] = str(e)

            details.append(step_result)

    # Determine overall pass/fail
    failures = [d for d in details if d.get("assertion_failed")]
    status = "fail" if failures else "pass"

    return {"status": status, "details": details}


async def _run_browser_test(tc: dict, base_url: str = BASE_URL) -> dict:
    """Execute a browser test case using Playwright. Setup steps already ran via API."""
    from playwright.async_api import async_playwright

    details = []
    screenshots = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        try:
            for step in tc.get("steps", []):
                action = step.get("action", "")
                step_details = step.get("details", {})
                step_result = {"step": action}

                try:
                    if step_details.get("goto"):
                        # Replace PORT_PLACEHOLDER or hardcoded ports with actual base_url
                        goto_url = step_details["goto"]
                        if "PORT_PLACEHOLDER" in goto_url:
                            goto_url = goto_url.replace("PORT_PLACEHOLDER", base_url.split(":")[-1])
                        elif goto_url.startswith("/"):
                            goto_url = f"{base_url}{goto_url}"
                        elif "127.0.0.1:10100" in goto_url:
                            goto_url = goto_url.replace("127.0.0.1:10100", f"127.0.0.1:{base_url.split(':')[-1]}")
                        await page.goto(goto_url, wait_until="networkidle", timeout=15000)
                        step_result["done"] = f"Navigated to {goto_url}"

                    if step_details.get("click"):
                        selector = step_details["click"]
                        await page.wait_for_selector(selector, timeout=5000)
                        await page.click(selector)
                        step_result["done"] = f"Clicked {selector}"

                    if step_details.get("fill"):
                        selector = step_details["fill"]["selector"]
                        value = step_details["fill"]["value"]
                        await page.fill(selector, str(value))
                        step_result["done"] = f"Filled {selector} with {value}"

                    if step_details.get("wait_for"):
                        selector = step_details["wait_for"]
                        timeout = step_details.get("timeout", 10000)
                        await page.wait_for_selector(selector, timeout=timeout)
                        step_result["done"] = f"Found {selector}"

                    if step_details.get("wait_ms"):
                        await asyncio.sleep(step_details["wait_ms"] / 1000)
                        step_result["done"] = f"Waited {step_details['wait_ms']}ms"

                    if step_details.get("check_text"):
                        selector = step_details["check_text"]["selector"]
                        expected = step_details["check_text"].get("contains", "")
                        not_expected = step_details["check_text"].get("not_contains", "")
                        el = await page.query_selector(selector)
                        if el is None:
                            step_result["assertion_failed"] = f"Element not found: {selector}"
                        else:
                            text = await el.text_content() or ""
                            step_result["actual_text"] = text[:200]
                            if expected and expected not in text:
                                step_result["assertion_failed"] = f"Expected '{expected}' in text, got: '{text[:100]}'"
                            if not_expected and not_expected in text:
                                step_result["assertion_failed"] = f"Did not expect '{not_expected}' in text, got: '{text[:100]}'"

                    if step_details.get("check_visible"):
                        selector = step_details["check_visible"]
                        el = await page.query_selector(selector)
                        visible = el is not None and await el.is_visible() if el else False
                        if not visible:
                            step_result["assertion_failed"] = f"Element not visible: {selector}"
                        else:
                            step_result["done"] = f"Visible: {selector}"

                    if step_details.get("check_count"):
                        selector = step_details["check_count"]["selector"]
                        min_count = step_details["check_count"].get("min", 1)
                        elements = await page.query_selector_all(selector)
                        count = len(elements)
                        if count < min_count:
                            step_result["assertion_failed"] = f"Expected >= {min_count} elements for {selector}, found {count}"
                        else:
                            step_result["done"] = f"Found {count} elements for {selector}"

                    if step_details.get("screenshot"):
                        name = step_details["screenshot"]
                        path = BACKEND_DIR / f".test_screenshots/{name}.png"
                        path.parent.mkdir(exist_ok=True)
                        await page.screenshot(path=str(path))
                        screenshots.append(str(path))
                        step_result["screenshot"] = str(path)

                    if step_details.get("evaluate"):
                        js = step_details["evaluate"]
                        result = await page.evaluate(js)
                        step_result["eval_result"] = str(result)[:500]
                        if step_details.get("eval_expected") is not None:
                            if result != step_details["eval_expected"]:
                                step_result["assertion_failed"] = f"JS eval: expected {step_details['eval_expected']!r}, got {result!r}"

                except Exception as e:
                    step_result["error"] = str(e)
                    step_result["assertion_failed"] = str(e)

                details.append(step_result)

        finally:
            await browser.close()

    failures = [d for d in details if d.get("assertion_failed")]
    return {
        "status": "fail" if failures else "pass",
        "details": details,
        "screenshots": screenshots,
    }


async def _run_unit_test(tc: dict) -> dict:
    """Execute a unit test case via direct Python import."""
    details = []

    for step in tc.get("steps", []):
        step_details = step.get("details", {})
        module_name = step_details.get("module", "")
        func_name = step_details.get("function", "")
        args = step_details.get("args", [])
        kwargs = step_details.get("kwargs", {})
        expected = step_details.get("expected")
        step_result = {"step": step.get("action", "")}

        try:
            mod = importlib.import_module(module_name)
            func = getattr(mod, func_name)
            result = func(*args, **kwargs)
            step_result["result"] = str(result)[:500]

            if expected is not None:
                if expected == "__truthy__" and not result:
                    step_result["assertion_failed"] = f"Expected truthy, got {result!r}"
                elif expected == "__falsy__" and result:
                    step_result["assertion_failed"] = f"Expected falsy, got {result!r}"
                elif expected == "__not_none__" and result is None:
                    step_result["assertion_failed"] = "Expected not None, got None"
                elif isinstance(expected, dict) and "__contains__" in expected:
                    if expected["__contains__"] not in str(result):
                        step_result["assertion_failed"] = f"Expected result to contain {expected['__contains__']!r}"
                elif isinstance(expected, dict) and "__type__" in expected:
                    expected_type = expected["__type__"]
                    if type(result).__name__ != expected_type:
                        step_result["assertion_failed"] = f"Expected type {expected_type}, got {type(result).__name__}"
                elif expected not in ("__truthy__", "__falsy__", "__not_none__") and not isinstance(expected, dict):
                    if result != expected:
                        step_result["assertion_failed"] = f"Expected {expected!r}, got {result!r}"
        except Exception as e:
            step_result["error"] = str(e)
            step_result["assertion_failed"] = str(e)

        details.append(step_result)

    failures = [d for d in details if d.get("assertion_failed")]
    return {"status": "fail" if failures else "pass", "details": details}


# ═══════════════════════════════════════════════════════════════════
# FIX LOOP — feed failures back through chat pipeline
# ═══════════════════════════════════════════════════════════════════

def format_failures_as_message(results: list[dict], plan: dict) -> str:
    """Format test failures as a message that can be sent to the chat pipeline."""
    failures = [r for r in results if r.get("status") in ("fail", "error")]
    if not failures:
        return ""

    parts = [f"## Test Failures Found ({len(failures)} failed)\n"]
    for f in failures:
        parts.append(f"### {f['id']}: {f['name']} ({f['type']})")
        parts.append(f"**Expected:** {f.get('expected', 'N/A')}")
        for detail in f.get("details", []):
            if detail.get("assertion_failed"):
                parts.append(f"- FAIL: {detail['step']}")
                parts.append(f"  {detail['assertion_failed']}")
            if detail.get("error"):
                parts.append(f"  Error: {detail['error']}")
            if detail.get("body_preview"):
                parts.append(f"  Response: {detail['body_preview'][:200]}")
        parts.append("")

    parts.append("Please fix the issues above. After fixing, the tests will be re-run to verify.")
    return "\n".join(parts)


async def send_to_chat_pipeline(message: str, project_dir: str) -> str:
    """Send a message through the chat pipeline and collect the response.

    This is the same flow as a user pasting an error into the chat.
    """
    async with httpx.AsyncClient(timeout=httpx.Timeout(600.0)) as client:
        # Step 1: Start conversation
        start_resp = await client.post(f"{BASE_URL}/api/direct/start", json={
            "message": message,
            "project_dir": project_dir,
        })
        start_data = start_resp.json()
        if start_data.get("error"):
            return f"ERROR: {start_data['error']}"

        stream_url = start_data["stream_url"]
        result_text = ""

        # Step 2: Consume SSE stream
        async with client.stream("GET", f"{BASE_URL}{stream_url}") as stream:
            buffer = ""
            async for chunk in stream.aiter_text():
                buffer += chunk
                while "\n\n" in buffer:
                    event_text, buffer = buffer.split("\n\n", 1)
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

                    if event_type == "response":
                        result_text = d.get("content", "")
                    elif event_type == "done":
                        break
                    elif event_type == "error":
                        return f"ERROR: {d.get('message', 'Stream error')}"

    return result_text


async def test_and_fix_loop(
    scope: str,
    context: str = "",
    project_dir: str = "aelidirect_platform",
    max_iterations: int = MAX_FIX_ITERATIONS,
) -> dict:
    """Full test-fix loop:
    1. Plan tests
    2. Run tests
    3. If failures: send to chat pipeline for fix
    4. Re-run tests with updated source
    5. Repeat until pass or max iterations

    Returns: {plan, iterations: [{results, fix_message, fix_response}], final_status}
    """
    source_batch = load_source_batch("platform")
    plan = await plan_tests(scope, context, source_batch)

    if plan.get("error"):
        return {"plan": plan, "iterations": [], "final_status": "plan_failed"}

    iterations = []

    for i in range(max_iterations):
        # Run tests
        results = await run_tests(plan)

        # Format results
        passed = sum(1 for r in results if r.get("status") == "pass")
        failed = sum(1 for r in results if r.get("status") in ("fail", "error"))
        skipped = sum(1 for r in results if r.get("status") == "skip")

        iteration = {
            "iteration": i + 1,
            "results": results,
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
            "fix_message": None,
            "fix_response": None,
        }

        if failed == 0:
            iterations.append(iteration)
            return {
                "plan": plan,
                "iterations": iterations,
                "final_status": "all_passed",
                "summary": f"All {passed} tests passed on iteration {i + 1}.",
            }

        # Generate fix message from failures
        fix_msg = format_failures_as_message(results, plan)
        iteration["fix_message"] = fix_msg

        if i < max_iterations - 1:
            # Send to chat pipeline for fix
            fix_response = await send_to_chat_pipeline(fix_msg, project_dir)
            iteration["fix_response"] = fix_response

            # Reload source for re-test (files may have changed)
            source_batch = load_source_batch("platform")

        iterations.append(iteration)

    return {
        "plan": plan,
        "iterations": iterations,
        "final_status": "max_iterations_reached",
        "summary": f"{failed} tests still failing after {max_iterations} iterations.",
    }


# ═══════════════════════════════════════════════════════════════════
# TOOL INTERFACE — callable from the chat agent
# ═══════════════════════════════════════════════════════════════════

async def handle_test_agent(args: dict) -> str:
    """Entry point when called as a tool from the agent.

    Args (from LLM):
        scope: What to test
        context: Why / what's broken (optional)
        project_dir: Which project (optional, defaults to platform)
        phase: "plan" | "run" | "full" (default: "full")
        fix_loop: Whether to attempt fixes (default: true)
    """
    scope = args.get("scope", "")
    context = args.get("context", "")
    project_dir = args.get("project_dir", "aelidirect_platform")
    phase = args.get("phase", "full")
    fix_loop = args.get("fix_loop", True)

    if phase == "plan":
        plan = await plan_tests(scope, context)
        return json.dumps(plan, indent=2)

    elif phase == "run":
        plan_data = args.get("plan")
        if not plan_data:
            return json.dumps({"error": "No plan provided for run phase"})
        results = await run_tests(plan_data)
        return json.dumps(results, indent=2)

    else:  # "full"
        if fix_loop:
            result = await test_and_fix_loop(scope, context, project_dir)
        else:
            source_batch = load_source_batch("platform")
            plan = await plan_tests(scope, context, source_batch)
            if plan.get("error"):
                return json.dumps({"plan": plan, "final_status": "plan_failed"}, indent=2)
            results = await run_tests(plan)
            passed = sum(1 for r in results if r.get("status") == "pass")
            failed = sum(1 for r in results if r.get("status") in ("fail", "error"))
            result = {
                "plan": plan,
                "iterations": [{"results": results, "passed": passed, "failed": failed}],
                "final_status": "all_passed" if failed == 0 else "failures_found",
            }
        return json.dumps(result, indent=2, default=str)


# ═══════════════════════════════════════════════════════════════════
# CLI — run directly for testing
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Test Agent")
    parser.add_argument("scope", help="What to test (e.g. 'heartbeat countdown', 'chat pipeline')")
    parser.add_argument("--context", default="", help="Additional context about what's broken")
    parser.add_argument("--project", default="aelidirect_platform", help="Project directory name")
    parser.add_argument("--phase", default="full", choices=["plan", "run", "full"])
    parser.add_argument("--no-fix", action="store_true", help="Don't attempt fixes on failure")
    parser.add_argument("--plan-only", action="store_true", help="Just show the test plan")

    args = parser.parse_args()

    async def main():
        if args.plan_only or args.phase == "plan":
            plan = await plan_tests(args.scope, args.context)
            print(json.dumps(plan, indent=2))
            return

        result = await test_and_fix_loop(
            args.scope, args.context, args.project,
            max_iterations=1 if args.no_fix else MAX_FIX_ITERATIONS,
        )

        # Print summary
        print(f"\n{'=' * 60}")
        print(f"TEST RESULTS: {result['final_status']}")
        print(f"{'=' * 60}")

        if result.get("plan", {}).get("summary"):
            print(f"Plan: {result['plan']['summary']}")

        for it in result.get("iterations", []):
            print(f"\nIteration {it.get('iteration', '?')}:")
            print(f"  Passed: {it.get('passed', 0)}")
            print(f"  Failed: {it.get('failed', 0)}")
            for r in it.get("results", []):
                icon = "PASS" if r["status"] == "pass" else "FAIL" if r["status"] == "fail" else "ERR "
                print(f"  [{icon}] {r['id']}: {r['name']}")
                if r["status"] != "pass":
                    for d in r.get("details", []):
                        if d.get("assertion_failed"):
                            print(f"         {d['assertion_failed']}")

        if result.get("summary"):
            print(f"\n{result['summary']}")

    asyncio.run(main())
