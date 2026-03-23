"""
Conversation persistence and history endpoint.
"""

import json
from pathlib import Path
from fastapi import APIRouter

from constants import (
    CONVERSATIONS_DIR, CONVERSATION_HISTORY_LIMIT,
    SUMMARIZE_BATCH_SIZE,
)
from llm_client import call_llm, extract_response

router = APIRouter()


def _save_conversation(project_name: str, user_message: str, messages: list, test_evidence: list = None):
    from datetime import datetime, timezone
    conv_dir = CONVERSATIONS_DIR / project_name
    conv_dir.mkdir(exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")

    full_messages = []
    for m in messages:
        role = m.get("role", "")
        if role == "system":
            continue
        if role == "user":
            full_messages.append({"role": "user", "content": m.get("content", "")})
        elif role == "assistant":
            content = m.get("content", "") or ""
            tool_calls = m.get("tool_calls", [])
            entry = {"role": "assistant"}
            if content.strip():
                entry["content"] = content
            if tool_calls:
                entry["tools"] = [
                    f"{tc['function']['name']}({tc['function'].get('arguments', '')})"
                    for tc in tool_calls
                ]
            full_messages.append(entry)
        elif role == "tool":
            full_messages.append({
                "role": "tool",
                "name": m.get("name", ""),
                "result": m.get("content", ""),
            })

    conv = {"timestamp": ts, "user_message": user_message, "messages": full_messages, "llm_summary": None}
    if test_evidence:
        conv["test_evidence"] = test_evidence
    (conv_dir / f"{ts}.json").write_text(json.dumps(conv, indent=1))


def _load_conversation_history(project_name: str, prov: dict = None, selected: str = None) -> str:
    conv_dir = CONVERSATIONS_DIR / project_name
    if not conv_dir.exists():
        return ""
    conv_files = sorted(conv_dir.glob("*.json"), key=lambda p: p.name)
    if not conv_files:
        return ""
    if len(conv_files) > CONVERSATION_HISTORY_LIMIT:
        for old_file in conv_files[:-CONVERSATION_HISTORY_LIMIT]:
            old_file.unlink()
        conv_files = conv_files[-CONVERSATION_HISTORY_LIMIT:]

    # Load only last 5 conversations for system prompt (rest are archived on disk)
    # This saves ~30-40k tokens of stale context per conversation
    recent_files = conv_files[-5:]
    conversations = []
    for f in recent_files:
        try:
            conv = json.loads(f.read_text())
            conv["_path"] = str(f)
            conversations.append(conv)
        except (json.JSONDecodeError, OSError):
            continue
    if not conversations:
        return ""

    def _conv_to_text(conv):
        summary = conv.get("llm_summary") or conv.get("summary")
        if summary:
            return f"[{conv['timestamp']}] {summary}"
        lines = [f"[{conv['timestamp']}] User: {conv.get('user_message', '?')}"]
        for m in (conv.get("messages") or []):
            if m.get("role") == "assistant" and m.get("content"):
                lines.append(f"  Assistant: {m['content'][:300]}")
            elif m.get("role") == "assistant" and m.get("tools"):
                lines.append(f"  Tools: {', '.join(m['tools'][:5])}")
        return "\n".join(lines)

    total_text = "\n\n".join(_conv_to_text(c) for c in conversations)
    return total_text


def _summarize_old_conversations(conversations: list, prov: dict, selected: str):
    unsummarized = [c for c in conversations[:-10]
                    if not c.get("llm_summary") and not c.get("summary")]
    if not unsummarized:
        return
    batch = unsummarized[:10]
    batch_text = ""
    for conv in batch:
        lines = [f"[{conv['timestamp']}] User: {conv.get('user_message', '?')}"]
        for m in (conv.get("messages") or []):
            if m.get("role") == "assistant" and m.get("content"):
                lines.append(f"  Assistant: {m['content'][:800]}")
            elif m.get("role") == "assistant" and m.get("tools"):
                lines.append(f"  Tools: {', '.join(m['tools'][:8])}")
            elif m.get("role") == "tool" and m.get("result"):
                lines.append(f"  Tool result ({m.get('name', '?')}): {m['result'][:300]}")
        batch_text += "\n".join(lines) + "\n---\n"

    try:
        result = call_llm(
            selected, prov["api_key"], prov["base_url"], prov["model"],
            [
                {"role": "system", "content": (
                    "You are summarizing developer conversations for future LLM context.\n\n"
                    "For EACH conversation delimited by ---:\n"
                    "1. List EVERY bug found (with root cause)\n"
                    "2. List EVERY fix applied (with what changed)\n"
                    "3. List EVERY feature added or config changed\n"
                    "4. Note any deploy/test results\n\n"
                    "Format: one conversation per line, starting with the timestamp.\n"
                    "Be specific — name functions, files, line numbers, error types.\n"
                    "DO NOT merge or skip items. If 3 bugs were found, list all 3.\n\n"
                    "Max 2000 chars per summary if needed, but keep it concise — don't pad. "
                    "Accuracy over brevity — never drop a bug or fix."
                )},
                {"role": "user", "content": batch_text},
            ],
            tools=None, temperature=0.2,
        )
        parsed = extract_response(result)
        summaries = [s.strip() for s in parsed["content"].strip().split("\n") if s.strip()]
        for i, conv in enumerate(batch):
            summary = summaries[i] if i < len(summaries) else f"[{conv['timestamp']}] (summarized)"
            if not summary.startswith("["):
                summary = f"[{conv['timestamp']}] {summary}"
            conv["llm_summary"] = summary
            conv_path = conv.get("_path")
            if conv_path:
                save_data = json.loads(Path(conv_path).read_text())
                save_data["llm_summary"] = summary
                Path(conv_path).write_text(json.dumps(save_data, indent=1))
    except Exception:
        pass


# ── Route ──────────────────────────────────────────────────────────────

@router.get("/api/direct/history/{project_dir}")
async def get_direct_history(project_dir: str):
    conv_dir = CONVERSATIONS_DIR / project_dir
    if not conv_dir.exists():
        return {"conversations": []}
    conv_files = sorted(conv_dir.glob("*.json"), key=lambda p: p.name)
    conversations = []
    for f in conv_files[-50:]:
        try:
            conv = json.loads(f.read_text())
            msgs = conv.get("messages") or []
            assistant_parts = []
            tool_names = []
            for m in msgs:
                if m.get("role") == "assistant" and m.get("content"):
                    assistant_parts.append(m["content"])
                if m.get("role") == "assistant" and m.get("tools"):
                    tool_names.extend(m["tools"])
            conversations.append({
                "timestamp": conv.get("timestamp", f.stem),
                "user_message": conv.get("user_message", ""),
                "response": "\n".join(assistant_parts) if assistant_parts else "",
                "tools_used": tool_names,
            })
        except (json.JSONDecodeError, OSError):
            continue
    return {"conversations": conversations}
