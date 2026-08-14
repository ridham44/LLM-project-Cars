# Running the Local AI Research Engine

## 1. First-time setup

Run once:

```
setup.bat
```

This checks for Python, Node.js, npm, and Ollama, creates `backend/venv`,
installs backend and frontend dependencies, creates `.env` from
`.env.example` if missing, creates `logs/`, and verifies the models
configured in `backend/config.py` are pulled in Ollama (see [Required
models](#7-required-models)).

Setup is separate from normal startup on purpose: `start.bat` never
reinstalls dependencies on its own, so day-to-day startup stays fast.

## 2. Normal startup

```
start.bat
```

or, cross-platform:

```
python run.py
```

This will, in order: check the environment, start Ollama if it isn't
already running, verify the configured models are present, start the
backend, start the frontend, then open `http://localhost:3000` in your
browser. Every checkmark it prints reflects a real, just-performed check —
nothing is assumed or faked.

Useful flags (pass to either `start.bat` or `python run.py`):

| Flag | Effect |
|---|---|
| `--no-browser` | don't open a browser window |
| `--backend-only` | start only the backend |
| `--frontend-only` | start only the frontend |
| `--no-ollama` | skip checking/starting Ollama |

On Linux/macOS, use `./start.sh` instead of `start.bat`.

## 3. Stopping services

```
stop.bat
```

Stops the backend and frontend the launcher started. **It will not stop
Ollama unless this launcher was the one that started it** — if Ollama was
already running before you ran `start.bat`, `stop.bat` leaves it alone.

## 4. Restarting

```
restart.bat
```

Equivalent to `stop.bat` followed by `start.bat` (including health checks
and reopening the browser).

## 5. Troubleshooting

Start with the log files (see [Logs](#9-logs)) — they contain the actual
process output, which is almost always more specific than the summary the
launcher prints. Then see [Common errors](#10-common-errors) below.

## 6. Required software

- Python 3.10+
- Node.js + npm (or yarn/pnpm — the launcher detects whichever lockfile is
  present in `frontend/`)
- [Ollama](https://ollama.ai)

## 7. Required models

The launcher imports `backend/config.py` directly (it only depends on the
standard library) and reads back every top-level `*_MODEL` name it resolves
to — including any override set in `.env` or the real environment — so it
never hard-codes model names. As of this writing the defaults are:

```
ROUTER_MODEL = qwen2.5:1.5b
FAST_MODEL = qwen2.5:1.5b
RESEARCHER_MODEL = qwen2.5:1.5b
HEAVY_RESEARCHER_MODEL = qwen2.5:1.5b
ANALYST_MODEL = qwen2.5:1.5b
CRITIC_MODEL = gemma3:4b
JUDGE_MODEL = qwen2.5:1.5b
SPECIALIST_MODEL = llava:7b
EMBEDDING_MODEL = nomic-embed-text
```

Every role except `critic` defaults to the SAME model on purpose - see
README.md's "Hardware reality" section: on the reference machine, a bigger
Qwen measured *slower per token*, not just slower to load, and a reasoning
model (DeepSeek-R1) spends most of its budget on invisible "thinking"
tokens before answering. Sharing one model means none of those roles ever
pays a reload swapping between each other. `HEAVY_RESEARCHER_MODEL`/
`ANALYST_MODEL`/`CRITIC_MODEL` are exactly where to point at a bigger or
more diverse model (e.g. `mistral-small3.1:24b`, `qwen3:8b`,
`deepseek-r1:7b`) if your hardware benchmarks fast enough to actually
benefit from it.

`SPECIALIST_MODEL` is registered for future vision/document-image use but
isn't invoked by the current pipeline — it's fine if it's the one model in
this list you don't have pulled. Pull whatever is currently listed there
manually with:

```
ollama pull <model-name>
```

or set `AUTO_PULL_MODELS=true` in `.env` to have the launcher pull missing
models automatically during `setup.bat` / `start.bat`.

## 8. Ports

Configured via `.env` (copy from `.env.example`):

```
BACKEND_HOST=127.0.0.1
BACKEND_PORT=8000

FRONTEND_HOST=localhost
FRONTEND_PORT=3000

OLLAMA_HOST=http://127.0.0.1:11434
```

If you change `FRONTEND_PORT`, the launcher passes the matching
`FRONTEND_ORIGIN` to the backend automatically so CORS keeps working — you
don't need to edit `backend/api.py`.

## 9. Logs

```
logs/
    launcher.log   the same status output start.bat prints, timestamped
    ollama.log     Ollama's own stdout/stderr
    backend.log    uvicorn/FastAPI stdout/stderr
    frontend.log   Vite dev server stdout/stderr
```

If a service fails to start or crashes, the launcher tells you exactly
which of these to check.

## 10. Common errors

**"Backend virtual environment not found. Run setup.bat first."**
`backend/venv` doesn't exist yet — run `setup.bat`.

**`PORT CONFLICT` — port already in use**
Something other than this app is already listening on the configured
port. Either stop that process, or change `BACKEND_PORT` / `FRONTEND_PORT`
in `.env`.

**`MODEL MISSING`**
Run the `ollama pull <model-name>` command it prints, or set
`AUTO_PULL_MODELS=true` in `.env`.

**Backend starts but research requests fail / return "Insufficient
evidence in the local knowledge base."**
This is expected until the vector DB is populated — see
`ARCHITECTURE_AUDIT.md` and `backend/load_docs.py`. It is not a launcher
bug.

**Ollama not found on PATH**
Install it from https://ollama.ai. The launcher will continue without it
(with a clear warning) so you can still reach the frontend, but research
calls that need local models will fail until it's installed.
