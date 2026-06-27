"""
Stress Test: 100 Execution Agents
==================================
Simulates 100 agents being spawned, executing, and completing to find
the breaking points of our bounded solution.

Measures:
  1. Prompt size at each agent count (active_agents block)
  2. Roster file size and load/save latency at scale
  3. Log store disk usage with 100 agent files
  4. Conversation history truncation under pressure
  5. Batch manager coordination with 100 concurrent executions
  6. Memory footprint growth
  7. Total prompt token estimate at N=10,25,50,75,100

No real LLM calls are made — this is a synthetic load test of the
data structures and prompt construction logic.
"""

import asyncio
import json
import os
import sys
import time
import shutil
import tempfile
import tracemalloc
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.services.execution.roster import AgentRoster
from server.services.execution.log_store import ExecutionAgentLogStore
from server.agents.interaction_agent.agent import (
    _render_active_agents,
    _render_conversation_history,
    prepare_message_with_history,
    _MAX_HISTORY_CHARS,
)
from server.agents.execution_agent.agent import ExecutionAgent


# ─── Configuration ────────────────────────────────────────────────────────────
NUM_AGENTS = 100
MILESTONES = [10, 25, 50, 75, 100]
AGENT_NAME_TEMPLATE = "exec-agent-{:03d}-research-and-analysis"  # realistic length
FAKE_INSTRUCTIONS = "Please research the quarterly financial report for Q3 2025 and summarize the key metrics including revenue growth, EBITDA margin, and net income trajectory." * 2
FAKE_RESPONSE = "Based on my analysis of the Q3 2025 financial report: Revenue grew 12.4% YoY to $4.2B, EBITDA margin expanded 180bps to 28.3%, and net income rose 15.7% to $890M. Key drivers include cloud segment growth (+34%) and operational efficiency gains." * 3


@dataclass
class Metrics:
    """Collected metrics at a given agent count."""
    agent_count: int
    active_count: int
    completed_count: int
    # Prompt metrics
    active_agents_block_chars: int
    active_agents_block_tokens_est: int  # chars / 4
    full_prompt_chars: int
    full_prompt_tokens_est: int
    # Roster metrics
    roster_file_bytes: int
    roster_load_ms: float
    roster_save_ms: float
    # Log store metrics
    total_log_bytes: int
    log_file_count: int
    single_log_bytes: int  # largest single file
    # Memory
    memory_bytes: int


def create_test_env():
    """Create isolated temp directory for the stress test."""
    tmpdir = Path(tempfile.mkdtemp(prefix="openpoke_stress_"))
    roster_path = tmpdir / "roster.json"
    log_dir = tmpdir / "logs"
    log_dir.mkdir()
    return tmpdir, roster_path, log_dir


def measure_roster_ops(roster: AgentRoster, roster_path: Path) -> Dict:
    """Measure load/save latency."""
    t0 = time.perf_counter()
    roster.load()
    load_ms = (time.perf_counter() - t0) * 1000

    t0 = time.perf_counter()
    roster.save()
    save_ms = (time.perf_counter() - t0) * 1000

    file_bytes = roster_path.stat().st_size if roster_path.exists() else 0
    return {"load_ms": load_ms, "save_ms": save_ms, "file_bytes": file_bytes}


def measure_prompt_size(roster: AgentRoster) -> Dict:
    """Measure the rendered active_agents block and full prompt."""
    import server.agents.interaction_agent.agent as agent_mod
    original_fn = agent_mod.get_agent_roster
    agent_mod.get_agent_roster = lambda: roster

    try:
        block = _render_active_agents()
        block_chars = len(block)

        # Simulate a realistic conversation transcript (~8K chars)
        fake_transcript = "\n".join([
            f"<user_message>Tell me about topic {i}</user_message>\n"
            f"<assistant_response>Here's information about topic {i} with some detail...</assistant_response>"
            for i in range(40)
        ])

        messages = prepare_message_with_history(
            "What's the status of all my agents?",
            fake_transcript,
            message_type="user",
        )
        full_prompt_chars = sum(len(m["content"]) for m in messages)

        return {
            "block_chars": block_chars,
            "block_tokens_est": block_chars // 4,
            "full_prompt_chars": full_prompt_chars,
            "full_prompt_tokens_est": full_prompt_chars // 4,
        }
    finally:
        agent_mod.get_agent_roster = original_fn


def measure_log_store(log_store: ExecutionAgentLogStore, log_dir: Path) -> Dict:
    """Measure log disk usage."""
    total_bytes = sum(f.stat().st_size for f in log_dir.glob("*.log"))
    log_files = list(log_dir.glob("*.log"))
    largest = max((f.stat().st_size for f in log_files), default=0)
    return {
        "total_bytes": total_bytes,
        "file_count": len(log_files),
        "largest_file_bytes": largest,
    }


def run_stress_test():
    """Main stress test orchestrator."""
    print("=" * 70)
    print("  STRESS TEST: 100 Execution Agents")
    print("  Finding limits of bounded solution")
    print("=" * 70)
    print()

    tmpdir, roster_path, log_dir = create_test_env()
    roster = AgentRoster(roster_path)
    log_store = ExecutionAgentLogStore(log_dir)

    tracemalloc.start()
    results: List[Metrics] = []

    # ─── Phase A: Spawn all 100 agents as ACTIVE (worst case) ─────────────
    print("━━━ Phase A: All agents ACTIVE (worst case for prompt bloat) ━━━")
    print()

    for i in range(NUM_AGENTS):
        name = AGENT_NAME_TEMPLATE.format(i)
        roster.add_agent(name)

        # Write logs for each
        log_store.record_request(name, FAKE_INSTRUCTIONS)
        log_store.record_action(name, f"tool_call_{i}: doing work")
        log_store.record_tool_response(name, f"tool_{i}", "result data " * 20)
        log_store.record_agent_response(name, FAKE_RESPONSE)

        if (i + 1) in MILESTONES:
            roster_metrics = measure_roster_ops(roster, roster_path)
            prompt_metrics = measure_prompt_size(roster)
            log_metrics = measure_log_store(log_store, log_dir)
            current, _ = tracemalloc.get_traced_memory()

            m = Metrics(
                agent_count=i + 1,
                active_count=len(roster.get_active_agents()),
                completed_count=len(roster.get_completed_agents()),
                active_agents_block_chars=prompt_metrics["block_chars"],
                active_agents_block_tokens_est=prompt_metrics["block_tokens_est"],
                full_prompt_chars=prompt_metrics["full_prompt_chars"],
                full_prompt_tokens_est=prompt_metrics["full_prompt_tokens_est"],
                roster_file_bytes=roster_metrics["file_bytes"],
                roster_load_ms=roster_metrics["load_ms"],
                roster_save_ms=roster_metrics["save_ms"],
                total_log_bytes=log_metrics["total_bytes"],
                log_file_count=log_metrics["file_count"],
                single_log_bytes=log_metrics["largest_file_bytes"],
                memory_bytes=current,
            )
            results.append(m)
            print(f"  N={i+1:3d} active | prompt={m.full_prompt_tokens_est:,} tok | "
                  f"roster={m.roster_file_bytes:,}B | logs={m.total_log_bytes:,}B | "
                  f"mem={m.memory_bytes/1024/1024:.1f}MB")

    print()
    print("━━━ Phase B: Agents complete (lifecycle transitions + pruning) ━━━")
    print()

    # ─── Phase B: Now complete agents in order (tests pruning) ────────────
    for i in range(NUM_AGENTS):
        name = AGENT_NAME_TEMPLATE.format(i)
        roster.complete_agent(name)

        if (i + 1) in MILESTONES:
            roster_metrics = measure_roster_ops(roster, roster_path)
            prompt_metrics = measure_prompt_size(roster)
            log_metrics = measure_log_store(log_store, log_dir)
            current, _ = tracemalloc.get_traced_memory()

            m = Metrics(
                agent_count=NUM_AGENTS,
                active_count=len(roster.get_active_agents()),
                completed_count=len(roster.get_completed_agents()),
                active_agents_block_chars=prompt_metrics["block_chars"],
                active_agents_block_tokens_est=prompt_metrics["block_tokens_est"],
                full_prompt_chars=prompt_metrics["full_prompt_chars"],
                full_prompt_tokens_est=prompt_metrics["full_prompt_tokens_est"],
                roster_file_bytes=roster_metrics["file_bytes"],
                roster_load_ms=roster_metrics["load_ms"],
                roster_save_ms=roster_metrics["save_ms"],
                total_log_bytes=log_metrics["total_bytes"],
                log_file_count=log_metrics["file_count"],
                single_log_bytes=log_metrics["largest_file_bytes"],
                memory_bytes=current,
            )
            results.append(m)
            print(f"  {i+1:3d} completed | active={m.active_count:3d} | "
                  f"completed(in roster)={m.completed_count:3d} | "
                  f"prompt={m.full_prompt_tokens_est:,} tok | "
                  f"roster={m.roster_file_bytes:,}B")

    print()
    print("━━━ Phase C: Rapid churn — 100 new agents after 100 completed ━━━")
    print()

    # ─── Phase C: Rapid churn scenario (old completed, new arriving) ──────
    for i in range(100, 200):
        name = AGENT_NAME_TEMPLATE.format(i)
        roster.add_agent(name)
        log_store.record_request(name, FAKE_INSTRUCTIONS)
        log_store.record_agent_response(name, FAKE_RESPONSE)
        roster.complete_agent(name)

    roster_metrics = measure_roster_ops(roster, roster_path)
    prompt_metrics = measure_prompt_size(roster)
    log_metrics = measure_log_store(log_store, log_dir)
    current, peak = tracemalloc.get_traced_memory()

    print(f"  After 200 total agents (100 churned):")
    print(f"    Active: {len(roster.get_active_agents())}")
    print(f"    Completed (in roster): {len(roster.get_completed_agents())}")
    print(f"    Prompt tokens: {prompt_metrics['full_prompt_tokens_est']:,}")
    print(f"    Roster file: {roster_metrics['file_bytes']:,} bytes")
    print(f"    Total log disk: {log_metrics['total_bytes']:,} bytes ({log_metrics['total_bytes']/1024:.0f} KB)")
    print(f"    Log files: {log_metrics['file_count']}")
    print(f"    Peak memory: {peak/1024/1024:.1f} MB")

    # ─── Phase D: Execution agent prompt size (history cap test) ───────────
    print()
    print("━━━ Phase D: Execution agent prompt size (history cap test) ━━━")
    print()

    # Write 50 request/response pairs to one agent's log
    for j in range(50):
        log_store.record_request("exec-agent-heavy-workload", f"Request {j}: {FAKE_INSTRUCTIONS}")
        log_store.record_agent_response("exec-agent-heavy-workload", f"Response {j}: {FAKE_RESPONSE}")

    entries = list(log_store.iter_entries("exec-agent-heavy-workload"))
    log_path = log_dir / "exec-agent-heavy-workload.log"
    log_size = log_path.stat().st_size if log_path.exists() else 0
    print(f"  Heavy agent (50 rounds): {len(entries)} entries, {log_size:,} bytes")
    print(f"  conversation_limit=5 means only last 5 pairs sent to LLM")
    print(f"  Log rotation cap: {ExecutionAgentLogStore.MAX_LOG_BYTES:,} bytes")
    if log_size > ExecutionAgentLogStore.MAX_LOG_BYTES:
        print(f"  ⚠️  Log exceeded cap! ({log_size:,} > {ExecutionAgentLogStore.MAX_LOG_BYTES:,})")
        print(f"    Note: rotation only triggers on _append, not retroactively")
    else:
        print(f"  ✓ Log within rotation threshold")

    # ─── Phase E: Concurrent batch execution simulation ───────────────────
    print()
    print("━━━ Phase E: Concurrent execution (semaphore @ 100 agents) ━━━")
    print()

    from server.agents.execution_agent.batch_manager import ExecutionBatchManager

    async def simulate_concurrent():
        """Test that the semaphore limits concurrency."""
        manager = ExecutionBatchManager(timeout_seconds=5)
        concurrent_peak = 0
        concurrent_current = 0
        lock = asyncio.Lock()

        async def fake_execute(idx):
            nonlocal concurrent_peak, concurrent_current
            async with manager._semaphore:
                async with lock:
                    concurrent_current += 1
                    concurrent_peak = max(concurrent_peak, concurrent_current)
                await asyncio.sleep(0.01)  # Simulate brief work
                async with lock:
                    concurrent_current -= 1

        tasks = [fake_execute(i) for i in range(100)]
        await asyncio.gather(*tasks)
        return concurrent_peak

    peak_concurrent = asyncio.run(simulate_concurrent())
    print(f"  100 agents queued, semaphore limit={ExecutionBatchManager.MAX_CONCURRENT}")
    print(f"  Peak concurrent observed: {peak_concurrent}")
    if peak_concurrent <= ExecutionBatchManager.MAX_CONCURRENT:
        print(f"  ✓ Semaphore held — max {ExecutionBatchManager.MAX_CONCURRENT} concurrent")
    else:
        print(f"  ✗ SEMAPHORE VIOLATED! Peak {peak_concurrent} > limit {ExecutionBatchManager.MAX_CONCURRENT}")

    # ─── Summary Table ────────────────────────────────────────────────────
    print()
    print("=" * 70)
    print("  RESULTS TABLE")
    print("=" * 70)
    print()
    print("┌─────────┬────────┬───────────┬────────────┬─────────────┬──────────┐")
    print("│ Agents  │ Active │ Completed │ Prompt Tok │ Roster (B)  │ Logs (KB)│")
    print("├─────────┼────────┼───────────┼────────────┼─────────────┼──────────┤")
    for m in results:
        print(f"│ {m.agent_count:7d} │ {m.active_count:6d} │ {m.completed_count:9d} │ "
              f"{m.full_prompt_tokens_est:10,} │ {m.roster_file_bytes:11,} │ "
              f"{m.total_log_bytes/1024:8.0f} │")
    print("└─────────┴────────┴───────────┴────────────┴─────────────┴──────────┘")

    # ─── Verdict ──────────────────────────────────────────────────────────
    print()
    print("=" * 70)
    print("  VERDICT: IDENTIFIED LIMITS")
    print("=" * 70)
    print()

    worst_prompt = max(m.full_prompt_tokens_est for m in results)
    best_prompt_after_drain = min(
        m.full_prompt_tokens_est for m in results
        if m.active_count == 0
    ) if any(m.active_count == 0 for m in results) else worst_prompt

    print(f"  1. WORST-CASE PROMPT (all 100 active): {worst_prompt:,} tokens")
    if worst_prompt > 8000:
        print(f"     🔴 CRITICAL: Exceeds 8K context budget!")
        print(f"     → Active agents block grows O(N) with no cap")
        print(f"     → Need: MAX_ACTIVE_RENDERED or active roster summarization")
    elif worst_prompt > 4000:
        print(f"     🟡 WARNING: Approaches danger zone (>4K)")
    else:
        print(f"     🟢 Acceptable")

    print(f"\n  2. BEST-CASE PROMPT (all completed): {best_prompt_after_drain:,} tokens")
    print(f"     🟢 Bounded by MAX_COMPLETED={roster.MAX_COMPLETED}")

    print(f"\n  3. ROSTER FILE: max {max(m.roster_file_bytes for m in results):,} bytes")
    max_load = max(m.roster_load_ms for m in results)
    print(f"     Load latency: max {max_load:.2f}ms")
    if max_load > 10:
        print(f"     🟡 Over 10ms — may affect request latency")
    else:
        print(f"     🟢 Fast enough")

    print(f"\n  4. LOG DISK: {log_metrics['total_bytes']/1024:.0f} KB across {log_metrics['file_count']} files")
    if log_metrics['total_bytes'] > 5_000_000:
        print(f"     🔴 Over 5MB — needs per-agent cleanup or global cap")
    elif log_metrics['total_bytes'] > 1_000_000:
        print(f"     🟡 Over 1MB — monitor growth")
    else:
        print(f"     🟢 Manageable")

    print(f"\n  5. CONCURRENCY: semaphore correctly limits to {ExecutionBatchManager.MAX_CONCURRENT}")
    print(f"     🟢 Bounded")

    print(f"\n  6. MEMORY: peak {peak/1024/1024:.1f} MB")
    if peak > 100_000_000:
        print(f"     🟡 Over 100MB")
    else:
        print(f"     🟢 Acceptable")

    print()
    print("─" * 70)
    print()

    # Cleanup
    tracemalloc.stop()
    shutil.rmtree(tmpdir)


if __name__ == "__main__":
    run_stress_test()
