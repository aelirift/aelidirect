"""
Minimal LLM client — supports OpenRouter and MiniMax.
Shows exactly what goes over the wire so you can learn.
"""

import httpx
import json
import time
from typing import Optional

TIMEOUT = 180.0
RETRYABLE_CODES = {429, 502, 503, 504}
MAX_RETRIES = 3
RETRY_DELAY = 3.0


class LLMError(Exception):
    """Raised when an LLM API call fails after retries."""
    def __init__(self, message: str, status_code: int = 0, response_body: str = ""):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


def call_llm(
    provider: str,
    api_key: str,
    base_url: str,
    model: str,
    messages: list[dict],
    tools: Optional[list[dict]] = None,
    temperature: float = 0.7,
) -> dict:
    """Make a single LLM API call. Returns the raw API response as a dict.

    This is the lowest level — one request, one response.
    The 'tools' parameter is what turns a plain LLM call into a tool-use call.
    Retries once on transient errors (429, 502, 503, 504).
    """
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    # Build the request body — this is what gets sent to the LLM
    body = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": 16000,
    }

    # THIS IS THE KEY DIFFERENCE:
    # When tools is None → plain LLM call (just generates text)
    # When tools is a list → LLM can choose to call a tool instead of generating text
    if tools:
        body["tools"] = tools

    # Figure out the endpoint
    if "minimax" in provider.lower():
        url = f"{base_url.rstrip('/')}/text/chatcompletion_v2"
    else:
        # OpenRouter, OpenAI, and most others use /chat/completions
        url = base_url.rstrip("/")
        if not url.endswith("/chat/completions"):
            url = f"{url}/chat/completions"

    # Make the actual HTTP request with retry
    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            with httpx.Client(timeout=TIMEOUT) as client:
                resp = client.post(url, headers=headers, json=body)
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPStatusError as e:
            last_error = e
            if e.response.status_code in RETRYABLE_CODES and attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY * (attempt + 1))
                continue
            raise LLMError(
                f"LLM API error: {e.response.status_code} {e.response.text[:500]}",
                status_code=e.response.status_code,
                response_body=e.response.text[:1000],
            )
        except httpx.TimeoutException:
            last_error = "timeout"
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY)
                continue
            raise LLMError(f"LLM API timeout after {TIMEOUT}s", status_code=0)
        except Exception as e:
            raise LLMError(f"LLM API connection error: {str(e)}", status_code=0)

    raise LLMError(f"LLM API failed after {MAX_RETRIES} retries: {last_error}")


def extract_response(raw: dict) -> dict:
    """Parse the LLM response into a simpler format.

    Returns:
        {
            "type": "text" | "tool_call",
            "content": "..." (if text),
            "tool_calls": [...] (if tool_call),
            "raw": {...} (original response)
        }
    """
    choice = raw.get("choices", [{}])[0]
    message = choice.get("message", {})

    # Check if the LLM wants to call a tool
    tool_calls = message.get("tool_calls", [])
    if tool_calls:
        parsed_calls = []
        for tc in tool_calls:
            raw_args = tc.get("function", {}).get("arguments", "{}")
            try:
                args = json.loads(raw_args)
            except (json.JSONDecodeError, TypeError):
                # LLM returned malformed JSON in tool arguments — attempt repair
                # Common issue: unterminated strings, trailing commas
                try:
                    # Try adding a closing quote + brace if truncated
                    repaired = raw_args.rstrip()
                    if repaired and not repaired.endswith("}"):
                        repaired += '"}'
                    args = json.loads(repaired)
                except (json.JSONDecodeError, TypeError):
                    # Give up — pass raw string as a single "input" argument
                    args = {"input": raw_args}
            parsed_calls.append({
                "id": tc.get("id", ""),
                "function_name": tc.get("function", {}).get("name", ""),
                "arguments": args,
            })
        return {
            "type": "tool_call",
            "content": message.get("content", ""),
            "tool_calls": parsed_calls,
            "raw": raw,
        }

    # Plain text response
    return {
        "type": "text",
        "content": message.get("content", ""),
        "tool_calls": [],
        "raw": raw,
    }
