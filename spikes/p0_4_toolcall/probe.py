"""P0.4 — prove that a llama-swap model can emit a tool call.

Sends one request with one tool definition and reports what came back.
No retries, no prompt massaging: the raw answer decides.

Usage: uv run python spikes/p0_4_toolcall/probe.py <model-id>
"""

from __future__ import annotations

import json
import sys
import time
import urllib.request

BASE = "http://127.0.0.1:8080/v1"

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_inbox_count",
            "description": "Return the number of unread messages in the inbox.",
            "parameters": {
                "type": "object",
                "properties": {
                    "account": {
                        "type": "string",
                        "description": "Mailbox address, e.g. someone@example.org",
                    }
                },
                "required": ["account"],
            },
        },
    }
]


def post(path: str, payload: dict, timeout: int = 600) -> dict:
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        BASE + path,
        data=body,
        headers={"Content-Type": "application/json", "Authorization": "Bearer none"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def main() -> int:
    model = sys.argv[1]
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": "Wie viele ungelesene Mails hat das Postfach frank@example.org?",
            }
        ],
        "tools": TOOLS,
        "tool_choice": "auto",
        "temperature": 0,
        "max_tokens": 300,
    }
    started = time.time()
    raw = post("/chat/completions", payload)
    elapsed = time.time() - started

    msg = raw["choices"][0]["message"]
    calls = msg.get("tool_calls") or []

    print(f"model      : {model}")
    print(f"latency_s  : {elapsed:.1f}")
    print(f"finish     : {raw['choices'][0].get('finish_reason')}")
    print(f"content    : {msg.get('content')!r}")
    print(f"tool_calls : {json.dumps(calls, ensure_ascii=False)}")
    print(f"usage      : {json.dumps(raw.get('usage'))}")

    verdict = "PASS" if len(calls) == 1 and calls[0]["function"]["name"] == "get_inbox_count" else "FAIL"
    print(f"verdict    : {verdict}")
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
