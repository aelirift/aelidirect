"""
TD (Technical Director) review and analysis endpoints.
"""

import json
import re
import asyncio
from fastapi import APIRouter

from constants import (
    CONVERSATIONS_DIR, TD_REPORTS_DIR,
    TD_ANALYSIS_RECENT_COUNT, TRUNCATE_TD_CONTEXT,
)
from state import config, _get_provider
from llm_client import call_llm, extract_response

router = APIRouter()


# ── TD Analysis Prompt ─────────────────────────────────────────────────
TD_ANALYSIS_PROMPT = (
    "You are a Technical Director reviewing an AI agent's work across multiple conversations and projects.\n\n"
    "Analyze the conversation history below and produce a comprehensive report:\n\n"
    "1. SUMMARY — What projects were worked on, how many conversations, overall health\n"
    "2. BUGS FOUND — Every bug discovered across all sessions (with root cause)\n"
    "3. BUGS FIXED — Every fix applied (what changed, which file, was it verified)\n"
    "4. BUGS MISSED — Anything the agent should have caught but didn't\n"
    "5. FEATURES BUILT — What was created, deployed, tested\n"
    "6. AGENT BEHAVIOR — How the agent approached tasks:\n"
    "   - Did it read code before acting?\n"
    "   - Did it verify fixes specifically or just check HTTP 200?\n"
    "   - Did it rationalize things as 'intentional' without evidence?\n"
    "   - Did it stop too early or keep investigating?\n"
    "7. PATTERNS — Recurring issues, common failures, things that work well\n"
    "8. RECOMMENDATIONS — Specific, actionable improvements for the agent's prompt, tools, or workflow\n\n"
    "Be thorough and specific. Name files, functions, line numbers. "
    "Don't sugarcoat — if the agent failed, say so and explain why.\n"
    "Format as markdown."
)


def _parse_td_verdict(review_text: str) -> str:
    """Parse the STATUS: line from TD review. Returns success/partial/failure/incomplete."""
    match = re.search(r"STATUS:\s*(PASS|PARTIAL|FAIL|INCOMPLETE)", review_text, re.IGNORECASE)
    if not match:
        return ""
    verdict = match.group(1).upper()
    return {"PASS": "success", "PARTIAL": "partial", "FAIL": "failure", "INCOMPLETE": "incomplete"}.get(verdict, "")


# ── Routes ─────────────────────────────────────────────────────────────

@router.post("/api/td-analysis")
async def run_td_analysis():
    """Run TD analysis across all projects and conversations."""
    prov = _get_provider()
    if not prov["api_key"]:
        return {"error": "No API key configured"}

    # Gather all conversations across all projects
    parts = []
    total_convs = 0

    if CONVERSATIONS_DIR.exists():
        for proj_dir in sorted(CONVERSATIONS_DIR.iterdir()):
            if not proj_dir.is_dir():
                continue
            conv_files = sorted(proj_dir.glob("*.json"), key=lambda p: p.name)
            if not conv_files:
                continue

            parts.append(f"\n## Project: {proj_dir.name} ({len(conv_files)} conversations)\n")

            for f in conv_files[-TD_ANALYSIS_RECENT_COUNT:]:
                try:
                    conv = json.loads(f.read_text())
                    total_convs += 1
                    parts.append(f"### [{conv.get('timestamp', f.stem)}] User: {conv.get('user_message', '?')}")

                    for m in (conv.get("messages") or []):
                        if m.get("role") == "assistant" and m.get("content"):
                            parts.append(f"  Agent: {m['content'][:600]}")
                        elif m.get("role") == "assistant" and m.get("tools"):
                            parts.append(f"  Tools: {', '.join(m['tools'][:8])}")
                        elif m.get("role") == "tool" and m.get("result"):
                            parts.append(f"  Result ({m.get('name', '?')}): {m['result'][:200]}")
                    parts.append("")
                except (json.JSONDecodeError, OSError):
                    continue

    if total_convs == 0:
        return {"error": "No conversations to analyze"}

    context = "\n".join(parts)

    # Truncate if too large for the LLM
    if len(context) > 400_000:
        context = context[:TRUNCATE_TD_CONTEXT] + "\n\n... (truncated)"

    try:
        selected = config["selected"]
        result = await asyncio.to_thread(
            call_llm, selected, prov["api_key"], prov["base_url"], prov["model"],
            [
                {"role": "system", "content": TD_ANALYSIS_PROMPT},
                {"role": "user", "content": f"Analyze these {total_convs} conversations:\n\n{context}"},
            ],
            None, 0.3,
        )
        parsed = extract_response(result)
        report = parsed["content"]

        # Save report
        from datetime import datetime, timezone
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
        (TD_REPORTS_DIR / f"{ts}.md").write_text(report)

        return {"report": report, "timestamp": ts, "conversations_analyzed": total_convs}
    except Exception as e:
        return {"error": f"Analysis failed: {e}"}


@router.get("/api/td-analysis")
async def get_latest_td_analysis():
    """Get the most recent TD analysis report."""
    if not TD_REPORTS_DIR.exists():
        return {"report": None}
    files = sorted(TD_REPORTS_DIR.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        return {"report": None}
    return {"report": files[0].read_text(), "timestamp": files[0].stem}


@router.get("/api/td-reports")
async def list_td_reports():
    """List all TD analysis reports."""
    reports = []
    if TD_REPORTS_DIR.exists():
        for f in sorted(TD_REPORTS_DIR.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True):
            content = f.read_text()
            reports.append({"timestamp": f.stem, "preview": content[:300].replace("\n", " ")})
    return {"reports": reports}


@router.get("/api/td-reports/{timestamp}")
async def get_td_report(timestamp: str):
    """Get a specific TD report by timestamp."""
    report_path = TD_REPORTS_DIR / f"{timestamp}.md"
    if report_path.exists():
        return {"report": report_path.read_text(), "timestamp": timestamp}
    return {"report": None, "timestamp": timestamp}
