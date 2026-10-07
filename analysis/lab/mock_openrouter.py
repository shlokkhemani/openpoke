"""Capturing mock of the OpenRouter /chat/completions endpoint.

Every request body is appended verbatim to <state>/llm_captures.jsonl so tests can
assert on exactly what OpenPoke would have sent to the external model provider.
Responses are scripted per caller (identified by system prompt) so the real
orchestration code paths (tool loops, agent dispatch, summarisation) execute.

Control endpoint: POST /__control {"summarizer_mode": "faithful|lossy|fail",
                                    "delay": {"<category>": seconds}}
"""

from __future__ import annotations

import json
import re
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

STATE_DIR = Path(sys.argv[2] if len(sys.argv) > 2 else Path(__file__).parent / "state")
STATE_DIR.mkdir(parents=True, exist_ok=True)
CAPTURE_PATH = STATE_DIR / "llm_captures.jsonl"
_lock = threading.Lock()
CONTROL = {"summarizer_mode": "faithful", "delay": {}}


def classify(body: dict) -> str:
    msgs = body.get("messages") or []
    system = msgs[0]["content"] if msgs and msgs[0].get("role") == "system" else ""
    tools = [t["function"]["name"] for t in body.get("tools") or []]
    if "You extract durable facts about the USER" in system:  # LTM LLMExtractor (unique phrase in its prompt)
        return "memory_extractor"
    if "memory curator" in system:
        return "summarizer"
    if "review incoming Gmail messages" in system:
        return "email_classifier"
    if "Gmail search assistant" in system:
        return "search_subagent"
    if "send_message_to_agent" in tools:
        return "interaction_agent"
    if "task_email_search" in tools or "createTrigger" in tools:
        return "execution_agent"
    return "unknown"


def tool_call(name: str, args: dict) -> dict:
    return {
        "id": f"call_{uuid.uuid4().hex[:8]}",
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(args)},
    }


def reply(content: str = "", tool_calls: list | None = None) -> dict:
    msg = {"role": "assistant", "content": content}
    if tool_calls:
        msg["tool_calls"] = tool_calls
    return {"id": "mock", "choices": [{"index": 0, "message": msg, "finish_reason": "stop"}]}


def _between(text: str, tag: str) -> str:
    m = re.search(rf"<{tag}>\n?(.*?)\n?</{tag}>", text, re.S)
    return m.group(1).strip() if m else ""


def interaction_agent(body: dict) -> dict:
    msgs = body["messages"]
    if msgs[-1]["role"] == "tool":
        return reply("")  # tool loop finished; user-visible text already sent via tool
    content = msgs[-1]["content"]
    user_text = _between(content, "new_user_message")
    agent_text = _between(content, "new_agent_message")
    if agent_text:
        # Realistic relay: the system prompt instructs the agent to pass results through.
        return reply("", [tool_call("send_message_to_user", {"message": f"Update: {agent_text[:400]}"})])
    if user_text.startswith("DELEGATE:"):
        return reply("", [
            tool_call("send_message_to_user", {"message": "On it."}),
            tool_call("send_message_to_agent", {"agent_name": "Synthetic Lab Agent",
                                                "instructions": user_text[len("DELEGATE:"):].strip()}),
        ])
    return reply("", [tool_call("send_message_to_user", {"message": "Noted."})])


def execution_agent(body: dict) -> dict:
    msgs = body["messages"]
    if msgs[-1]["role"] == "tool":
        # Realistic behaviour per execution system prompt: forward relevant details verbatim.
        return reply(f"Result: {msgs[-1]['content'][:600]}")
    instr = msgs[-1]["content"]
    if instr.startswith("TRIGGER:"):
        return reply("", [tool_call("createTrigger", {"payload": instr, "recurrence_rule": "FREQ=DAILY"})])
    if "search" in instr.lower():
        return reply("", [tool_call("task_email_search", {"search_query": instr})])
    return reply("Done: " + instr[:200])


def search_subagent(body: dict) -> dict:
    msgs = body["messages"]
    if msgs[-1]["role"] == "tool":
        # Production sends a Python repr() here (datetime breaks json.dumps), so accept both quote styles.
        ids = re.findall(r"""["']id["']: ["']([^"']+)["']""", msgs[-1]["content"])
        return reply("", [tool_call("return_search_results", {"message_ids": ids})])
    return reply("", [tool_call("gmail_fetch_emails", {"query": "newer_than:7d", "max_results": 10})])


def email_classifier(body: dict) -> dict:
    content = body["messages"][-1]["content"]
    sender = re.search(r"Sender: (.*)", content).group(1)
    subject = re.search(r"Subject: (.*)", content).group(1)
    body_text = content.split("Cleaned Body:\n", 1)[-1]
    important = bool(re.search(r"code|otp|verification", content, re.I))
    args = {"important": important}
    if important:
        # The classifier prompt asks for OTPs to be surfaced with "the specific action".
        args["summary"] = f"{sender} sent '{subject}': {body_text[:160]}"
    return reply("", [tool_call("mark_email_importance", args)])


def summarizer(body: dict) -> dict | None:
    mode = CONTROL["summarizer_mode"]
    if mode == "fail":
        return None
    user = body["messages"][-1]["content"]
    if mode == "lossy":
        notes = ["- No items."]
    else:
        prev = re.findall(r"^\s*(- NOTE: .*)$", user, re.M)
        new = [f"- NOTE: {m}" for m in re.findall(r"^\s*\[\d+\] user message: (.*)$", user, re.M)]
        notes = [p for p in prev] + new or ["- No items."]
    text = (
        "Summary generated: 2026-10-07 12:00 (user timezone)\n\n"
        "Timeline & Commitments:\n- No items.\n\nPending & Follow-ups:\n- No items.\n\n"
        "Routines & Recurring:\n- No items.\n\nPreferences & Profile:\n- No items.\n\n"
        "Context & Notes:\n" + "\n".join(notes)
    )
    return reply(text)


def memory_extractor(body: dict) -> dict:
    # Default: no candidates. Gates never depend on mock extraction quality (handoff C3); the captures prove what
    # crossed the boundary.
    return reply(json.dumps({"candidates": [], "ignored": []}))


HANDLERS = {
    "memory_extractor": memory_extractor,
    "interaction_agent": interaction_agent,
    "execution_agent": execution_agent,
    "search_subagent": search_subagent,
    "email_classifier": email_classifier,
    "summarizer": summarizer,
}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # silence
        pass

    def _send(self, code: int, payload: dict) -> None:
        data = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        if self.path == "/__control":
            CONTROL.update(body)
            return self._send(200, CONTROL)
        category = classify(body)
        with _lock:
            with CAPTURE_PATH.open("a") as fh:
                fh.write(json.dumps({
                    "t": time.time(), "category": category,
                    "auth_header_present": bool(self.headers.get("Authorization")),
                    "body": body,
                }) + "\n")
        time.sleep(float(CONTROL["delay"].get(category, 0)))
        handler = HANDLERS.get(category)
        result = handler(body) if handler else reply("unknown caller")
        if result is None:
            return self._send(500, {"error": "mock summarizer failure"})
        self._send(200, result)


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 18080
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
