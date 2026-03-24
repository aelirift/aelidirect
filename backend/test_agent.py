"""
Test Agent — programmatic test generation and execution.

No LLM planning. Reads code changes, generates tests programmatically,
runs them directly with httpx (API) and Playwright (browser).
"""

import json
import asyncio
import httpx
import re
import traceback
from pathlib import Path

from constants import (
    BRANCH_PORT, PROD_PORT, BACKEND_DIR,
    MAX_TEST_FIX_ITERATIONS,
)

DEFAULT_PORT = BRANCH_PORT
MAX_FIX_ITERATIONS = MAX_TEST_FIX_ITERATIONS


def _resolve_url(url: str, base_url: str) -> str:
    """Resolve a URL: replace PORT_PLACEHOLDER, make relative URLs absolute."""
    if "PORT_PLACEHOLDER" in url:
        url = url.replace("PORT_PLACEHOLDER", base_url.split(":")[-1])
    if "127.0.0.1:10100" in url:
        url = url.replace("127.0.0.1:10100", base_url.split("//")[1] if "//" in base_url else base_url)
    if url.startswith("/"):
        url = f"{base_url}{url}"
    elif not url.startswith("http"):
        url = f"{base_url}/{url}"
    return url


# ═══════════════════════════════════════════════════════════════════
# CHANGE DETECTION — parse what the agent changed
# ═══════════════════════════════════════════════════════════════════

def detect_changes(changes_summary: list, messages: list = None) -> list[dict]:
    """Parse code changes into structured change objects.

    Returns list of:
    {
        "type": "ui_button" | "ui_function" | "api_endpoint" | "backend_function" | "css" | "patch",
        "file": "frontend/index.html",
        "details": {...}  # type-specific
    }
    """
    changes = []

    for change in changes_summary:
        # Detect new buttons: onclick="functionName(...)"
        buttons = re.findall(r'<button[^>]*onclick="(\w+)\(([^"]*)\)"[^>]*>([^<]+)</button>', change)
        for func_name, func_args, label in buttons:
            changes.append({
                "type": "ui_button",
                "file": _extract_file(change),
                "details": {"function": func_name, "args": func_args, "label": label.strip()},
            })

        # Detect new async/regular functions
        functions = re.findall(r'(?:async\s+)?function\s+(\w+)\s*\(([^)]*)\)', change)
        for func_name, params in functions:
            changes.append({
                "type": "ui_function",
                "file": _extract_file(change),
                "details": {"function": func_name, "params": params},
            })

        # Detect new API endpoints: @router.get/post/etc or fetch('/api/...')
        endpoints = re.findall(r'fetch\([\'"]([/\w.-]+)[\'"]\s*[,)]', change)
        for ep in endpoints:
            if ep.startswith("/api/"):
                changes.append({
                    "type": "api_endpoint",
                    "file": _extract_file(change),
                    "details": {"path": ep},
                })

        # Detect route decorators
        routes = re.findall(r'@(?:router|app)\.(get|post|put|delete)\([\'"]([^\'"]+)', change)
        for method, path in routes:
            changes.append({
                "type": "api_endpoint",
                "file": _extract_file(change),
                "details": {"method": method.upper(), "path": path},
            })

        # Detect CSS class additions
        css_classes = re.findall(r'class(?:Name)?="([^"]+)"', change)
        for cls in css_classes:
            for c in cls.split():
                if c not in ("ctx-modal-backdrop", "ctx-modal", "ctx-modal-header", "ctx-modal-close", "ctx-modal-body"):
                    changes.append({
                        "type": "css",
                        "file": _extract_file(change),
                        "details": {"class": c},
                    })

        # If nothing specific detected, record as generic patch
        if not any(c["file"] == _extract_file(change) for c in changes):
            changes.append({
                "type": "patch",
                "file": _extract_file(change),
                "details": {"raw": change[:200]},
            })

    # Deduplicate
    seen = set()
    unique = []
    for c in changes:
        key = (c["type"], c.get("details", {}).get("function", ""), c.get("details", {}).get("path", ""), c.get("details", {}).get("label", ""))
        if key not in seen:
            seen.add(key)
            unique.append(c)

    return unique


def _extract_file(change_text: str) -> str:
    """Extract filename from change description."""
    match = re.search(r'(?:In |Patched |File written: )(\S+)', change_text)
    if match:
        name = match.group(1).rstrip(",:")
        return name
    return "unknown"


# ═══════════════════════════════════════════════════════════════════
# TEST GENERATION — create tests from detected changes
# ═══════════════════════════════════════════════════════════════════

def generate_tests(changes: list, project_dir: str, target_port: int) -> list[dict]:
    """Generate test cases programmatically from detected changes.

    Each test: {"id", "name", "type": "api"|"browser", "run": async callable}
    """
    tests = []
    base_url = f"http://127.0.0.1:{target_port}"
    tid = 0

    for change in changes:
        ctype = change["type"]
        details = change["details"]

        if ctype == "ui_button":
            tid += 1
            label = details["label"]
            func = details["function"]
            tests.append({
                "id": f"T{tid}",
                "name": f"Button '{label}' exists in UI",
                "type": "browser",
                "run": _make_button_exists_test(base_url, label),
            })
            tid += 1
            tests.append({
                "id": f"T{tid}",
                "name": f"Clicking '{label}' triggers {func}()",
                "type": "browser",
                "run": _make_button_click_test(base_url, label),
            })

        elif ctype == "ui_function":
            func = details["function"]
            # If function name suggests it shows/opens something, test the modal
            if func.startswith("show") or func.startswith("load") or func.startswith("open"):
                tid += 1
                tests.append({
                    "id": f"T{tid}",
                    "name": f"Function {func}() opens modal/content",
                    "type": "browser",
                    "run": _make_function_modal_test(base_url, func),
                })

        elif ctype == "api_endpoint":
            path = details["path"]
            method = details.get("method", "GET")
            tid += 1
            tests.append({
                "id": f"T{tid}",
                "name": f"{method} {path} returns 200",
                "type": "api",
                "run": _make_api_test(base_url, path, method, project_dir),
            })

    # Always add a basic page load test if there are browser tests
    if any(t["type"] == "browser" for t in tests):
        tests.insert(0, {
            "id": "T0",
            "name": "Page loads successfully",
            "type": "browser",
            "run": _make_page_load_test(base_url),
        })

    return tests


# ═══════════════════════════════════════════════════════════════════
# TEST RUNNERS — actual test implementations
# ═══════════════════════════════════════════════════════════════════

def _make_page_load_test(base_url: str):
    async def test():
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            try:
                await page.goto(base_url, wait_until="networkidle", timeout=15000)
                title = await page.title()
                if not title:
                    return {"status": "fail", "details": [{"step": "page load", "assertion_failed": "Page has no title"}]}
                return {"status": "pass", "details": [{"step": "page load", "done": f"Title: {title}"}]}
            except Exception as e:
                return {"status": "fail", "details": [{"step": "page load", "assertion_failed": str(e)}]}
            finally:
                await browser.close()
    return test


def _make_button_exists_test(base_url: str, label: str):
    async def test():
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            try:
                await page.goto(base_url, wait_until="networkidle", timeout=15000)
                # Wait for app to initialize
                await asyncio.sleep(1)
                btn = await page.query_selector(f"button:has-text('{label}')")
                if btn and await btn.is_visible():
                    return {"status": "pass", "details": [{"step": f"button '{label}'", "done": "visible"}]}
                # Check if it exists but might need a project selected
                all_btns = await page.query_selector_all("button")
                btn_texts = []
                for b in all_btns:
                    t = await b.text_content()
                    if t:
                        btn_texts.append(t.strip())
                return {"status": "fail", "details": [{"step": f"button '{label}'", "assertion_failed": f"Not found. Buttons on page: {btn_texts[:10]}"}]}
            except Exception as e:
                return {"status": "fail", "details": [{"step": f"button '{label}'", "assertion_failed": str(e)}]}
            finally:
                await browser.close()
    return test


def _make_button_click_test(base_url: str, label: str):
    async def test():
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            try:
                await page.goto(base_url, wait_until="networkidle", timeout=15000)
                await asyncio.sleep(1)
                btn = await page.query_selector(f"button:has-text('{label}')")
                if not btn:
                    return {"status": "fail", "details": [{"step": "find button", "assertion_failed": f"Button '{label}' not found"}]}
                await btn.click()
                await asyncio.sleep(1)
                # Check if a modal/overlay appeared
                modal = await page.query_selector(".ctx-modal-backdrop, .modal-backdrop, .modal-overlay, [class*='modal']")
                if not modal or not await modal.is_visible():
                    return {"status": "fail", "details": [{"step": f"click '{label}'", "assertion_failed": "Clicked but no modal/overlay appeared"}]}
                # Check modal has actual content (not empty)
                modal_text = await modal.text_content() or ""
                modal_text = modal_text.strip()
                if len(modal_text) < 20:
                    return {"status": "fail", "details": [{"step": f"modal content", "assertion_failed": f"Modal opened but content is empty or too short ({len(modal_text)} chars)"}]}
                # Check it doesn't show error/placeholder
                lower = modal_text.lower()
                if "no " in lower[:30] and "generated" in lower[:60]:
                    return {"status": "fail", "details": [{"step": "modal content", "assertion_failed": f"Modal shows placeholder: '{modal_text[:80]}'"}]}
                return {"status": "pass", "details": [
                    {"step": f"click '{label}'", "done": "modal opened"},
                    {"step": "modal content", "done": f"has content ({len(modal_text)} chars)"},
                ]}
            except Exception as e:
                return {"status": "fail", "details": [{"step": f"click '{label}'", "assertion_failed": str(e)}]}
            finally:
                await browser.close()
    return test


def _make_function_modal_test(base_url: str, func_name: str):
    async def test():
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            try:
                await page.goto(base_url, wait_until="networkidle", timeout=15000)
                await asyncio.sleep(1)
                # Check function exists in JS
                exists = await page.evaluate(f"typeof {func_name} === 'function'")
                if not exists:
                    return {"status": "fail", "details": [{"step": f"{func_name} defined", "assertion_failed": f"{func_name} is not defined"}]}
                return {"status": "pass", "details": [{"step": f"{func_name} defined", "done": "function exists"}]}
            except Exception as e:
                return {"status": "fail", "details": [{"step": f"{func_name} defined", "assertion_failed": str(e)}]}
            finally:
                await browser.close()
    return test


def _make_api_test(base_url: str, path: str, method: str, project_dir: str):
    async def test():
        url = f"{base_url}{path}"
        # Replace path parameters
        url = url.replace("{project_dir}", project_dir)
        url = url.replace("{project}", project_dir)
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                if method == "GET":
                    resp = await client.get(url)
                elif method == "POST":
                    resp = await client.post(url, json={})
                elif method == "PUT":
                    resp = await client.put(url, json={})
                elif method == "DELETE":
                    resp = await client.delete(url)
                else:
                    resp = await client.get(url)
                if 200 <= resp.status_code < 300:
                    return {"status": "pass", "details": [{"step": f"{method} {path}", "done": f"HTTP {resp.status_code}"}]}
                else:
                    return {"status": "fail", "details": [{"step": f"{method} {path}", "assertion_failed": f"HTTP {resp.status_code}: {resp.text[:200]}"}]}
        except Exception as e:
            return {"status": "fail", "details": [{"step": f"{method} {path}", "assertion_failed": str(e)}]}
    return test


# ═══════════════════════════════════════════════════════════════════
# MAIN ENTRY — called from pipeline
# ═══════════════════════════════════════════════════════════════════

async def run_tests_from_changes(
    changes_summary: list,
    messages: list,
    project_dir: str,
    target_port: int = DEFAULT_PORT,
    user_prompt: str = "",
) -> dict:
    """Generate and run tests from code changes. No LLM involved.

    Returns: {"summary", "total", "passed", "failed", "results": [...]}
    """
    base_url = f"http://127.0.0.1:{target_port}"

    # Detect what changed
    changes = detect_changes(changes_summary, messages)
    if not changes:
        return {
            "summary": "No testable changes detected",
            "total": 0, "passed": 0, "failed": 0,
            "results": [],
        }

    # Generate tests
    tests = generate_tests(changes, project_dir, target_port)
    if not tests:
        return {
            "summary": f"Detected {len(changes)} changes but no tests generated",
            "total": 0, "passed": 0, "failed": 0,
            "results": [],
        }

    # Run tests
    results = []
    for t in tests:
        try:
            result = await t["run"]()
            result["id"] = t["id"]
            result["name"] = t["name"]
            result["type"] = t["type"]
            results.append(result)
        except Exception as e:
            results.append({
                "id": t["id"],
                "name": t["name"],
                "type": t["type"],
                "status": "error",
                "details": [{"step": "execution", "assertion_failed": str(e)}],
            })

    passed = sum(1 for r in results if r.get("status") == "pass")
    failed = sum(1 for r in results if r.get("status") in ("fail", "error"))

    summary = f"Ran {len(results)} tests from {len(changes)} detected changes: {passed} passed, {failed} failed"

    return {
        "summary": summary,
        "total": len(results),
        "passed": passed,
        "failed": failed,
        "results": results,
    }


def format_failures_as_message(results: list, context: dict = None) -> str:
    """Format test failures as a message for feeding back to the coder."""
    failures = [r for r in results if r.get("status") in ("fail", "error")]
    if not failures:
        return ""

    parts = [f"## Test Failures ({len(failures)} failed)\n"]
    for f in failures:
        parts.append(f"### {f['id']}: {f['name']} ({f['type']})")
        for detail in f.get("details", []):
            if isinstance(detail, dict) and detail.get("assertion_failed"):
                parts.append(f"- FAIL: {detail['assertion_failed'][:200]}")
        parts.append("")

    parts.append("Fix the failures above. The tests will re-run to verify.")
    return "\n".join(parts)
