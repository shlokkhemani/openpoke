"""Rebuild the interaction-agent request for turn 3 using the production prompt code.
Usage (from repo root):
  .venv/bin/python analysis/lab/reconstruct_prompt.py "$PWD" <copy-of-poke_working_memory.log> <tmp-output.log>
Reads a COPY of working memory truncated to the state before turn 3 (lines 1-6). No writes to server/data."""
import sys, json
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from server.services.conversation.summarization.working_memory_log import WorkingMemoryLog
from server.agents.interaction_agent.agent import build_system_prompt, prepare_message_with_history
from server.config import get_settings

src, tmp = Path(sys.argv[2]), Path(sys.argv[3])
tmp.write_text("\n".join(src.read_text(encoding="utf-8").splitlines()[:6]) + "\n", encoding="utf-8")
transcript_before = WorkingMemoryLog(tmp).render_transcript()
final_q = "What’s my favorite programming language?"
msgs = prepare_message_with_history(final_q, transcript_before, message_type="user")
s = get_settings()
print("summarization_enabled:", s.summarization_enabled, "threshold:", s.conversation_summary_threshold)
print("model:", s.interaction_agent_model)
print("system prompt mentions python/rust:", any(w in build_system_prompt().lower() for w in ("python", "rust")))
print("----- messages[0].content -----")
print(msgs[0]["content"])
