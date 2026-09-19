# OpenPoke 🌴

OpenPoke is a simplified, open-source take on [Interaction Company’s](https://interaction.co/about) [Poke](https://poke.com/) assistant—built to show how a multi-agent orchestration stack can feel genuinely useful. It keeps the handful of things Poke is great at (email triage, reminders, and persistent agents) while staying easy to spin up locally.

- Multi-agent FastAPI backend that mirrors Poke's interaction/execution split, powered by [OpenRouter](https://openrouter.ai/).
- Gmail tooling via [Composio](https://composio.dev/) for drafting/replying/forwarding without leaving chat.
- Trigger scheduler and background watchers for reminders and "important email" alerts.
- Next.js web UI that proxies everything through the shared `.env`, so plugging in API keys is the only setup.
- Optional typed-decision layer backed by [Jev](https://docs.typesafe.ai/concepts/system-one), so classification, routing and guardrail judgements are calibrated probabilities instead of another LLM call. Off unless a key is set.

## Requirements
- Python 3.10+
- Node.js 18+
- npm 9+

## Quickstart
1. **Clone and enter the repo.**
   ```bash
   git clone https://github.com/shlokkhemani/OpenPoke
   cd OpenPoke
   ```
2. **Create a shared env file.** Copy the template and open it in your editor:
   ```bash
   cp .env.example .env
   ```
3. **Get your API keys and add them to `.env`:**
   
   **OpenRouter (Required)**
   - Create an account at [openrouter.ai](https://openrouter.ai/)
   - Generate an API key
   - Replace `your_openrouter_api_key_here` with your actual key in `.env`
   
   **Composio (Required for Gmail)**
   - Sign in at [composio.dev](https://composio.dev/)
   - Create an API key
   - Set up Gmail integration and get your auth config ID
   - Replace `your_composio_api_key_here` and `your_gmail_auth_config_id_here` in `.env`
4. **(Required) Create and activate a Python 3.10+ virtualenv:**
   ```bash
   # Ensure you're using Python 3.10+
   python3.10 -m venv .venv
   source .venv/bin/activate
   
   # Verify Python version (should show 3.10+)
   python --version
   ```
   On Windows (PowerShell):
   ```powershell
   # Use Python 3.10+ (adjust path as needed)
   python3.10 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   
   # Verify Python version
   python --version
   ```

5. **Install backend dependencies:**
   ```bash
   pip install -r server/requirements.txt
   ```
6. **Install frontend dependencies:**
   ```bash
   npm install --prefix web
   ```
7. **Start the FastAPI server:**
   ```bash
   python -m server.server --reload
   ```
8. **Start the Next.js app (new terminal):**
   ```bash
   npm run dev --prefix web
   ```
9. **Connect Gmail for email workflows.** With both services running, open [http://localhost:3000](http://localhost:3000), head to *Settings → Gmail*, and complete the Composio OAuth flow. This step is required for email drafting, replies, and the important-email monitor.

The web app proxies API calls to the Python server using the values in `.env`, so keeping both processes running is required for end-to-end flows.

## Typed decisions with Jev (optional)

OpenPoke asks an LLM for a number of judgements that are not text generation: whether an inbound email is worth interrupting the user, whether an execution agent's tool call matches its assignment, whether a search result answers the question that was asked. Those are typed decisions, and [Jev](https://docs.typesafe.ai/concepts/system-one) — TypeSafe's System One model — answers them as calibrated probabilities rather than prose.

The clearest case is the important-email watcher. Today every new message goes to Sonnet with a tool schema whose only required field is a boolean, so learning "no" about a newsletter costs a full completion. With this layer a single Jev call screens the message first: confidently unimportant mail never reaches an LLM, confidently important mail skips straight to summarisation, and only the uncertain band pays for the existing tool-calling classifier.

Set `TYPESAFE_API_KEY` in `.env` to turn it on. **Leave it unset and nothing changes** — every entry point returns "undecided" or "allow" and the previous LLM paths run unchanged.

| Decision | File | Effect |
| --- | --- | --- |
| Email importance | `server/services/gmail/importance_classifier.py` | Four batched questions. Skip without an LLM call, surface and summarise, or defer to the existing classifier. |
| Tool-call guardrail | `server/agents/execution_agent/runtime.py` | Four questions before a tool runs. Only an irreversible call that also contradicts the assignment is held, and a held call returns to the agent as a tool error so it can correct itself. |
| Search relevance | `server/agents/execution_agent/tasks/search_email/tool.py` | Verifies the ids the search LLM selected. Never empties a result set. |

Every question lives in `server/jev/questions.py` and every threshold in `server/jev/thresholds.py`, so the policy is reviewable in two files. `docs/jev.md` covers configuration and the failure policy; `docs/injection-findings.md` reports what 43,776 measured requests say about how this behaves under attacker-authored email bodies, including the design flaw the measurement found and the change made because of it.

## Tests

```bash
pip install -r server/requirements-dev.txt
python -m pytest
```

90 tests, no network and no API keys: OpenRouter is monkeypatched and Jev is mocked through the SDK's `transport` seam with `httpx2.MockTransport`. `server/requirements-dev.txt` deliberately omits Composio, whose transitive `pysher` dependency needs a compiler and which nothing in the suite touches.

## Project Layout
- `server/` – FastAPI application and agents
- `server/jev/` – optional typed-decision layer (questions, thresholds, decisions)
- `web/` – Next.js app
- `server/data/` – runtime data (ignored by git)

## License
MIT — see [LICENSE](LICENSE).
