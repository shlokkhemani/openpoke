"""Step 9 gate (in-process; OpenRouter patched like the lab).

Flag off: no server/data/memory, system prompt sha256 unchanged, no LTM sections, raw values in conversation files.
Flag on: placeholders in conversation files and payloads, LTM block on the next relevant turn.
Debug routes: 404 when disabled, 403 from non-loopback.
"""

from __future__ import annotations

import copy
import hashlib
import shutil
import tempfile
import unittest
import warnings
from pathlib import Path
from unittest import mock

from server.agents.interaction_agent import agent as agent_mod
from server.agents.interaction_agent import runtime as runtime_mod
from server.config import get_settings
from server.services import memory as memory_pkg
from server.services.conversation.log import ConversationLog
from server.services.conversation.summarization.working_memory_log import WorkingMemoryLog
from server.services.memory.models import MemoryScope
from server.services.memory.store import MemoryStore

from ._util import make_service

SECRET = "sk-test-SYNTHETIC-12345"
EMAIL = "test.user@example.com"
PROMPT_FILE = Path(agent_mod.__file__).parent / "system_prompt.md"
LTM_FLAGS = ("ltm_enabled", "ingress_scrub_enabled", "ltm_debug", "ltm_debug_events", "ltm_test_hooks")


def sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


class FakeOpenRouter:
    """Captures the exact payload the interaction model would receive; always replies with plain text."""

    def __init__(self):
        self.calls = []

    async def __call__(self, *, model, messages, system, api_key, tools=None, **_):
        self.calls.append({"system": system, "messages": copy.deepcopy(messages)})
        return {"choices": [{"message": {"role": "assistant", "content": "Noted."}}]}

    def user_content(self, i=-1) -> str:
        return self.calls[i]["messages"][0]["content"]


class IntegrationCase(unittest.IsolatedAsyncioTestCase):
    ltm = False

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ltm-int-"))
        self.settings = get_settings()
        self._saved = {k: getattr(self.settings, k) for k in LTM_FLAGS}
        for k in LTM_FLAGS:
            setattr(self.settings, k, self.ltm)
        self.wm = WorkingMemoryLog(self.tmp / "conversation" / "poke_working_memory.log")
        self.conv = ConversationLog(self.tmp / "conversation" / "poke_conversation.log")
        self.conv._working_memory_log = self.wm
        self.llm = FakeOpenRouter()
        self.patches = [mock.patch.object(runtime_mod, "request_chat_completion", self.llm),
                        mock.patch.object(self.settings, "openrouter_api_key", "test-key")]
        for p in self.patches:
            p.start()
        self.real_memory_dir = memory_pkg.DATA_DIR
        self.real_memory_dir_existed = self.real_memory_dir.exists()
        if self.ltm:
            self.store = MemoryStore(self.tmp / "memory" / "ltm.db", hmac_key=b"k" * 32)
            self.svc = make_service(self.store, MemoryScope("local-user"))
            memory_pkg._service = self.svc
        else:
            # Flag off must never touch the memory service at all.
            self.patches.append(mock.patch.object(memory_pkg, "get_memory_service",
                                                  side_effect=AssertionError("LTM used with flags off")))
            self.patches[-1].start()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        for k, v in self._saved.items():
            setattr(self.settings, k, v)
        memory_pkg.reset_memory_service()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def runtime(self):
        rt = runtime_mod.InteractionAgentRuntime()
        rt.conversation_log = self.conv
        rt.working_memory_log = self.wm
        return rt

    async def send(self, text):
        result = await self.runtime().execute(user_message=text)
        self.assertTrue(result.success, result.error)
        if self.ltm:
            self.assertTrue(await self.svc.await_idle())
        return self.llm.user_content()

    def files(self) -> str:
        return "".join(p.read_text() for p in (self.tmp / "conversation").glob("*.log"))


class TestFlagOff(IntegrationCase):
    ltm = False

    async def test_baseline_unchanged(self):
        await self.send("My favorite programming language is Python.")
        await self.send("Actually, my favorite programming language is Rust.")
        payload = await self.send(f"My email is {EMAIL}, my test API key is {SECRET}, and I prefer concise emails.")
        # Same system prompt, byte for byte (the runtime sends system_prompt.md stripped, as before).
        for call in self.llm.calls:
            self.assertEqual(sha(call["system"]), sha(PROMPT_FILE.read_text(encoding="utf-8").strip()))
        # No new prompt sections.
        for call in self.llm.calls:
            body = call["messages"][0]["content"]
            self.assertNotIn("<long_term_memory>", body)
            self.assertNotIn("<memory_notice>", body)
        # Same files: raw values persisted and replayed exactly as in the baseline evidence.
        self.assertIn(SECRET, self.files())
        self.assertIn(SECRET, payload)
        self.assertIn("Python", self.llm.user_content(-1))
        self.assertEqual(self.real_memory_dir.exists(), self.real_memory_dir_existed)
        self.assertFalse((self.tmp / "memory").exists())

    async def test_message_shape_identical_to_original_signature(self):
        await self.send("hello there")
        sections = [s.split("\n", 1)[0] for s in self.llm.user_content().split("\n\n")]
        self.assertEqual(sections, ["<conversation_history>", "<active_agents>", "<new_user_message>"])


class TestFlagOn(IntegrationCase):
    ltm = True

    async def test_placeholders_and_ltm_block(self):
        await self.send("My favorite programming language is Python.")
        await self.send("Actually, my favorite programming language is Rust.")
        payload = await self.send("What's my favorite programming language?")
        self.assertIn("<long_term_memory>", payload)
        self.assertIn('replaces_earlier_value="true">User\'s favorite programming language is Rust.</memory>', payload)
        ltm_section = payload.split("<long_term_memory>", 1)[1].split("</long_term_memory>", 1)[0]
        self.assertNotIn("Python", ltm_section)
        # Section order: history, LTM, (notices), agents, new message.
        heads = [s.split("\n", 1)[0] for s in payload.split("\n\n")]
        self.assertEqual(heads, ["<conversation_history>", "<long_term_memory>", "<active_agents>", "<new_user_message>"])
        # System prompt = baseline + addendum (system_prompt.md itself is untouched).
        self.assertTrue(self.llm.calls[-1]["system"].startswith(PROMPT_FILE.read_text(encoding="utf-8").strip()))
        self.assertIn("<long_term_memory>", self.llm.calls[-1]["system"])

    async def test_secret_scrubbed_before_files_and_payload(self):
        payload = await self.send(f"My email is {EMAIL}, my test API key is {SECRET}, and I prefer concise emails.")
        self.assertNotIn(SECRET, payload)
        self.assertIn("[SECRET:API_KEY]", payload)
        self.assertIn("<memory_notice>A secret-like value in the latest message was replaced with [SECRET:API_KEY]",
                      payload)
        self.assertIn(EMAIL, payload)  # contact PII stays in short-term context by design (D24)
        files = self.files()
        self.assertNotIn(SECRET, files)
        self.assertIn("[SECRET:API_KEY]", files)
        self.assertIn(EMAIL, files)
        later = await self.send("Draft a short note to Sam about the launch.")
        self.assertNotIn(SECRET, later)
        self.assertIn("User prefers concise emails.", later)
        self.assertTrue(memory_pkg.DATA_DIR.exists() == self.real_memory_dir_existed)  # temp store, not the real dir

    async def test_review_m3_prefixed_credentials_scrubbed_at_every_boundary(self):
        from ._util import ltm_bytes

        cases = [("my password is [X]hunter2pass", "hunter2pass"),
                 ("SECRET:API_KEY=hunter2pass99", "hunter2pass99"),
                 ("Use passphrase: [SECRET:X]realsecret123", "realsecret123")]
        for raw, _ in cases:
            await self.send(raw)
        sinks = {"conversation+working memory": self.files(),
                 "interaction model": repr([c["messages"] for c in self.llm.calls]),
                 "extractor input": repr(self.svc.extractor.calls),
                 "ltm.db*": ltm_bytes(self.store).decode("latin-1")}
        for _, secret in cases:
            for name, blob in sinks.items():
                self.assertNotIn(secret, blob, f"{secret} in {name}")
        self.assertEqual(len(self.svc.extractor.calls), 3)

    async def test_i2_record_reply_and_agent_messages_scrubbed(self):
        self.conv.record_reply(f"Your key is {SECRET}")
        result = await self.runtime().handle_agent_message("Use code 771204 to sign in.")
        self.assertTrue(result.success)
        files = self.files()
        self.assertNotIn(SECRET, files)
        self.assertNotIn("771204", files)
        self.assertNotIn("771204", self.llm.user_content())
        await self.svc.await_idle()
        self.assertEqual(self.store.all_rows(MemoryScope("local-user")), [])  # agent messages never ingest (D6)


class TestDebugRoutes(unittest.TestCase):
    def setUp(self):
        from fastapi import FastAPI

        from server.routes.memory_debug import router

        self.settings = get_settings()
        self._saved = {k: getattr(self.settings, k) for k in LTM_FLAGS}
        self.tmp = Path(tempfile.mkdtemp(prefix="ltm-dbg-"))
        memory_pkg._service = make_service(MemoryStore(self.tmp / "ltm.db", hmac_key=b"k" * 32), MemoryScope("local-user"))
        self.app = FastAPI()
        self.app.include_router(router, prefix="/api/v1")

    def tearDown(self):
        for k, v in self._saved.items():
            setattr(self.settings, k, v)
        memory_pkg.reset_memory_service()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def client(self, host):
        from fastapi.testclient import TestClient

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return TestClient(self.app, client=(host, 50000))

    def test_404_when_disabled(self):
        for k in LTM_FLAGS:
            setattr(self.settings, k, False)
        c = self.client("127.0.0.1")
        for path in ("/api/v1/memory/debug/state", "/api/v1/memory/debug/traces", "/api/v1/memory/debug/trace/x"):
            self.assertEqual(c.get(path).status_code, 404, path)
        self.assertEqual(c.post("/api/v1/memory/debug/test/await-idle").status_code, 404)

    def test_hooks_404_without_test_hook_flag(self):
        for k in LTM_FLAGS:
            setattr(self.settings, k, k != "ltm_test_hooks")
        c = self.client("127.0.0.1")
        self.assertEqual(c.get("/api/v1/memory/debug/state").status_code, 200)
        self.assertEqual(c.post("/api/v1/memory/debug/test/ingest-delay",
                                json={"duplicate_next_job_with_delay_ms": 10}).status_code, 404)

    def test_403_from_non_loopback(self):
        for k in LTM_FLAGS:
            setattr(self.settings, k, True)
        c = self.client("10.0.0.7")
        self.assertEqual(c.get("/api/v1/memory/debug/state").status_code, 403)
        self.assertEqual(c.post("/api/v1/memory/debug/test/await-idle").status_code, 403)

    def test_loopback_ok(self):
        for k in LTM_FLAGS:
            setattr(self.settings, k, True)
        c = self.client("127.0.0.1")
        self.assertEqual(c.get("/api/v1/memory/debug/state").json(),
                         {"memories": [], "deleted": [], "edges": [], "tombstones": []})
        self.assertEqual(c.get("/api/v1/memory/debug/traces?limit=5").json(), [])
        self.assertEqual(c.post("/api/v1/memory/debug/test/await-idle", json={"timeout_s": 1}).json(),
                         {"idle": True, "pending": 0})


if __name__ == "__main__":
    unittest.main()
