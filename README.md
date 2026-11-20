# OpenPoke 🌴

OpenPoke is a simplified, open-source take on [Interaction Company’s](https://interaction.co/about) [Poke](https://poke.com/) assistant—built to show how a multi-agent orchestration stack can feel genuinely useful. It keeps the handful of things Poke is great at (email triage, reminders, and persistent agents) while staying easy to spin up locally.

- Multi-agent FastAPI backend that mirrors Poke's interaction/execution split, powered by a local model server through [llama.cpp](https://github.com/ggml-org/llama.cpp) (`llama-server`) and its OpenAI-compatible API.
- Gmail tooling via [Composio](https://composio.dev/) for drafting/replying/forwarding without leaving chat.
- Trigger scheduler and background watchers for reminders and "important email" alerts.
- Next.js web UI that proxies everything through the shared `.env`, so plugging in API keys is the only setup.

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
3. **Configure the model endpoint and add your Gmail keys to `.env`:**

   **Local model server (Required)**
   - Run `llama-server` with the model you want to use, for example the bundled Qwen 9B:
     ```bash
     llama-server \
       -m D:/Claude_Projects/local_LLM/models/Qwen3.5-9B-Q4_K_M.gguf \
       --alias Qwen3.5-9B-Q4_K_M --jinja -c 131072 --reasoning-format deepseek --port 8080
     ```
   - `--jinja` is required: without it the server does not apply the model's tool-calling template.
   - `-c` must be large enough for the system prompt, transcript, and 13 tool schemas. The interaction agent's prompt alone runs about 40k tokens with a populated transcript, so stay at `65536` or above. A too-small `-c` fails with a 400 "exceeds the available context size" error, not a crash.
   - Reasoning is controlled by `--reasoning on|off` (or `--reasoning-format deepseek` so thoughts land in `reasoning_content`). The code falls back to `reasoning_content` when `content` is blank, but `--reasoning off` is the safer default for tool-heavy turns.
   - Set `LLM_BASE_URL` (default `http://127.0.0.1:8080/v1`) and `LLM_MODEL` (default `Qwen3.5-9B-Q4_K_M`) in `.env` to match. `LLM_API_KEY` is optional and only needed if your endpoint requires a bearer token.
   - Local generation is slow, so `LLM_TIMEOUT` (default `300`) also sets the per-agent execution budget. Raise it if agents time out.

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

## Project Layout
- `server/` – FastAPI application and agents
- `web/` – Next.js app
- `server/data/` – runtime data (ignored by git)

## License
MIT — see [LICENSE](LICENSE).
