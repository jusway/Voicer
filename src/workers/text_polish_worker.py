"""
Subprocess worker for Text Polish streaming via OpenAI-compatible /v1/chat/completions.
- Reads SSE lines from HTTP stream
- Sends messages back to parent via multiprocessing.Queue
  * {"type": "delta", "text": "..."}
  * {"type": "done"}
  * {"type": "error", "message": "..."}
Note: Keep imports inside functions to be conservative for Windows spawn/packaging.
"""
from __future__ import annotations


def parse_delta(s: str) -> str:
    # Minimal parser for OpenAI-style SSE chunk JSON in 'data: ...' lines
    # Returns incremental content string; returns empty string for [DONE] or missing content
    if not s:
        return ""
    ss = s.strip()
    if ss == "[DONE]":
        return ""
    try:
        import json  # local import for packaging friendliness
        obj = json.loads(ss)
        choices = obj.get("choices") or []
        if not choices:
            return ""
        delta = choices[0].get("delta") or {}
        return delta.get("content", "") or ""
    except Exception:
        return ""


def run_text_polish_worker(base_url: str, api_key: str, model: str, messages, temperature: float, out_q) -> None:
    """Run in a subprocess. Stream chat completions and push deltas to out_q.
    This function must be at module top-level for Windows spawn.
    """
    try:
        import httpx  # required by openai anyway; explicit here
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "stream": True,
        }
        # Use open-ended read/write timeouts; rely on process-level hard cancel for responsiveness
        timeout = httpx.Timeout(None, connect=60.0, read=None, write=None, pool=None)
        url = f"{base_url}/chat/completions"
        with httpx.stream("POST", url, headers=headers, json=payload, timeout=timeout) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line:
                    continue
                # Expect SSE format: 'data: {...}'
                if line.startswith("data: "):
                    text = parse_delta(line[6:])
                    if text:
                        try:
                            out_q.put({"type": "delta", "text": text})
                        except Exception:
                            # Parent may have exited; nothing else to do
                            break
                # else: ignore comments/fields like 'event:' or other headers
        # Stream ended normally
        try:
            out_q.put({"type": "done"})
        except Exception:
            pass
    except Exception as e:  # network or parsing error
        try:
            out_q.put({"type": "error", "message": f"{type(e).__name__}: {e}"})
        except Exception:
            pass

