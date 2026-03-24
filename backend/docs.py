"""
Auto-documentation regeneration — SPEC.md, CONTEXT_MAP.md, DATA_FLOW.md, SITE_MAP.md.
"""

import asyncio
import re
import concurrent.futures

from constants import PROD_ROOT, BRANCH_ROOT
from state import config, _get_provider
from llm_client import call_llm, extract_response


def _strip_llm_artifacts(text: str) -> str:
    """Strip <think> blocks and [TOOL_CALL] blocks from LLM output."""
    text = re.sub(r'<think>[\s\S]*?</think>', '', text)
    text = re.sub(r'\[TOOL_CALL\][\s\S]*?\[/TOOL_CALL\]', '', text)
    return text.strip()


_CONTEXT_MAP_PROMPT = (
    "You are a documentation generator for a software project.\n\n"
    "Given the source code below, produce a CONTEXT_MAP.md that maps:\n"
    "1. File structure with purpose of each file\n"
    "2. All API endpoints (method, path, handler function, line number)\n"
    "3. All tools/functions available to the LLM agent\n"
    "4. Data directories and their formats\n"
    "5. Frontend components and key JS functions\n"
    "6. Key constants, config, and state variables\n\n"
    "Use tables and code blocks. Be specific with line numbers. "
    "Format as markdown. Start with '# aelidirect -- Context Map'."
)

_DATA_FLOW_PROMPT = (
    "You are a documentation generator for a software project.\n\n"
    "Given the source code below, produce a DATA_FLOW.md that traces:\n"
    "1. Main chat flow (user message → SSE stream → agent loop → response)\n"
    "2. Tool call loop (LLM response → tool execution → result → next LLM call)\n"
    "3. Memory system (long-term save/load, short-term conversation history)\n"
    "4. Heartbeat/todo execution flow\n"
    "5. Deployment flow (pod management)\n"
    "6. Config and state management\n"
    "7. Branch/prod sync flow\n\n"
    "Trace data step by step with file names, function names, and line numbers. "
    "Format as markdown. Start with '# aelidirect -- Data Flow'."
)


_SPEC_PROMPT = (
    "You are a documentation generator for a software project.\n\n"
    "Given the source code below, produce a SPEC.md that covers:\n"
    "1. What the project is (1-2 paragraph overview in plain English)\n"
    "2. How it works (the big picture — message flow, agent loop, tool execution)\n"
    "3. Features — organized by category (core agent, file tools, system tools, memory, "
    "project management, testing, deployment, frontend, TD review)\n"
    "4. Tech stack table\n"
    "5. How to run it\n\n"
    "Write for someone who has never seen the project. Be specific about what each feature does. "
    "Include the test agent (test_agent.py) — explain the two-phase test system (plan then run), "
    "the test-fix loop (failures feed back to coder with context preserved), and how TD review "
    "incorporates test evidence.\n\n"
    "Format as markdown. Start with '# aelidirect -- Project Specification'."
)


async def _regenerate_docs():
    """Regenerate SPEC.md, CONTEXT_MAP.md and DATA_FLOW.md in parallel."""
    import logging
    _log = logging.getLogger("uvicorn")
    prov = _get_provider()
    if not prov["api_key"]:
        return

    # Read all source files in parallel
    source_files = [
        PROD_ROOT / "backend/app.py",
        PROD_ROOT / "backend/state.py",
        PROD_ROOT / "backend/pipeline.py",
        PROD_ROOT / "backend/heartbeat.py",
        PROD_ROOT / "backend/platform_routes.py",
        PROD_ROOT / "backend/history.py",
        PROD_ROOT / "backend/td.py",
        PROD_ROOT / "backend/docs.py",
        PROD_ROOT / "backend/tools.py",
        PROD_ROOT / "backend/direct_todo.py",
        PROD_ROOT / "backend/llm_client.py",
        PROD_ROOT / "backend/pod.py",
        PROD_ROOT / "backend/test_agent.py",
        PROD_ROOT / "backend/constants.py",
        PROD_ROOT / "frontend/index.html",
    ]

    def _read_file(p):
        if p.exists():
            content = p.read_text()
            # Truncate large files to keep within LLM context
            if len(content) > 30000:
                content = content[:15000] + "\n\n... [TRUNCATED] ...\n\n" + content[-15000:]
            return f"\n### {p.relative_to(PROD_ROOT)}\n```\n{content}\n```\n"
        return ""

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        futures = [pool.submit(_read_file, f) for f in source_files]
        file_contents = [fut.result() for fut in futures]

    all_source = "\n".join(file_contents)
    selected = config["selected"]

    # Run both LLM calls in parallel
    async def _gen_context_map():
        try:
            result = await asyncio.to_thread(
                call_llm, selected, prov["api_key"], prov["base_url"], prov["model"],
                [
                    {"role": "system", "content": _CONTEXT_MAP_PROMPT},
                    {"role": "user", "content": all_source},
                ],
                None, 0.3,
            )
            parsed = extract_response(result)
            (BRANCH_ROOT / "CONTEXT_MAP.md").write_text(_strip_llm_artifacts(parsed["content"]))
            _log.info("[docs] CONTEXT_MAP.md regenerated")
        except Exception as e:
            _log.error(f"[docs] Failed to regenerate CONTEXT_MAP.md: {e}")

    async def _gen_data_flow():
        try:
            result = await asyncio.to_thread(
                call_llm, selected, prov["api_key"], prov["base_url"], prov["model"],
                [
                    {"role": "system", "content": _DATA_FLOW_PROMPT},
                    {"role": "user", "content": all_source},
                ],
                None, 0.3,
            )
            parsed = extract_response(result)
            (BRANCH_ROOT / "DATA_FLOW.md").write_text(_strip_llm_artifacts(parsed["content"]))
            _log.info("[docs] DATA_FLOW.md regenerated")
        except Exception as e:
            _log.error(f"[docs] Failed to regenerate DATA_FLOW.md: {e}")

    async def _gen_spec():
        try:
            result = await asyncio.to_thread(
                call_llm, selected, prov["api_key"], prov["base_url"], prov["model"],
                [
                    {"role": "system", "content": _SPEC_PROMPT},
                    {"role": "user", "content": all_source},
                ],
                None, 0.3,
            )
            parsed = extract_response(result)
            (BRANCH_ROOT / "SPEC.md").write_text(_strip_llm_artifacts(parsed["content"]))
            _log.info("[docs] SPEC.md regenerated")
        except Exception as e:
            _log.error(f"[docs] Failed to regenerate SPEC.md: {e}")

    async def _gen_site_map():
        try:
            result = await asyncio.to_thread(
                call_llm, selected, prov["api_key"], prov["base_url"], prov["model"],
                [
                    {"role": "system", "content": (
                        "You are a documentation generator. Given the source code below, "
                        "produce a SITE_MAP.md — a compact file tree like an uncollapsed file explorer.\n\n"
                        "Format:\n"
                        "# Site Map\n"
                        "## backend/\n"
                        "### filename.py — one-line description\n"
                        "  - function_name() — short description / tags\n"
                        "  - another_func() — short description\n\n"
                        "## frontend/\n"
                        "### index.html — one-line description\n"
                        "  - jsFunction() — short description\n\n"
                        "## Root docs\n"
                        "  - SPEC.md — description\n\n"
                        "Rules:\n"
                        "- List EVERY function/class in every file\n"
                        "- Descriptions are keyword tags or 5-10 word phrases, not sentences\n"
                        "- DO NOT include line numbers (they go stale after edits)\n"
                        "- DO NOT include file contents, just names + descriptions\n"
                        "- Group by directory, then by file\n"
                        "- Include endpoints next to their handler functions\n"
                        "Start with '# Site Map'."
                    )},
                    {"role": "user", "content": all_source},
                ],
                None, 0.3,
            )
            parsed = extract_response(result)
            (BRANCH_ROOT / "SITE_MAP.md").write_text(_strip_llm_artifacts(parsed["content"]))
            _log.info("[docs] SITE_MAP.md regenerated")
        except Exception as e:
            _log.error(f"[docs] Failed to regenerate SITE_MAP.md: {e}")

    # Run all four in parallel
    await asyncio.gather(_gen_spec(), _gen_context_map(), _gen_data_flow(), _gen_site_map())
    _log.info("[docs] Documentation regeneration complete")
