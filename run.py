"""Local AI Research Engine - unified launcher.

Starts Ollama (if needed), the FastAPI backend, and the Vite frontend, waits
for each to actually become healthy (never a blind sleep), then opens the
browser. Tracks which services it started so `--stop` never touches a
pre-existing Ollama instance it didn't launch.
"""

import argparse
import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND_DIR = ROOT / "backend"
FRONTEND_DIR = ROOT / "frontend"
LOGS_DIR = ROOT / "logs"
STATE_FILE = LOGS_DIR / "launcher_state.json"
ENV_FILE = ROOT / ".env"

IS_WINDOWS = platform.system() == "Windows"

if IS_WINDOWS:
    # Legacy cmd.exe codepages (437/1252) can't render checkmark glyphs and
    # will raise UnicodeEncodeError on print() otherwise.
    os.system("chcp 65001 >nul")
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

DEFAULTS = {
    "BACKEND_HOST": "127.0.0.1",
    "BACKEND_PORT": "8000",
    "FRONTEND_HOST": "localhost",
    "FRONTEND_PORT": "3000",
    "OLLAMA_HOST": "http://127.0.0.1:11434",
    "AUTO_PULL_MODELS": "false",
    "START_TIMEOUT": "90",
    "BROWSER_AUTO_OPEN": "true",
}

processes = {}
log_handles = {}
STATUS = {"ollama_started_by_launcher": False}

LOGS_DIR.mkdir(exist_ok=True)
LAUNCHER_LOG = LOGS_DIR / "launcher.log"


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------

def log(message):
    print(message)
    with LAUNCHER_LOG.open("a", encoding="utf-8") as f:
        f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}\n")


def banner(title):
    line = "=" * 50
    log(line)
    log(title.center(50))
    log(line)


def ok(msg):
    log(f"      ✓ {msg}")


def fail(msg):
    log(f"      ✗ {msg}")


def warn(msg):
    log(f"      ! {msg}")


def as_bool(value):
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def load_env():
    values = dict(DEFAULTS)
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip()
    for key in DEFAULTS:
        if key in os.environ:
            values[key] = os.environ[key]
    # Propagate every value (defaults + .env overrides, e.g. per-role
    # *_MODEL vars consumed by backend/config.py) into this process's real
    # environment - without clobbering anything the user already exported -
    # so both discover_configured_models() below and spawn()'s
    # os.environ.copy() for the backend subprocess see the same values.
    for key, value in values.items():
        os.environ.setdefault(key, value)
    return values


def shim_command(args):
    """Wrap a command with `cmd /c` on Windows so .cmd/.bat shims (npm/yarn/pnpm)
    execute correctly under subprocess without shell=True."""
    if IS_WINDOWS:
        return ["cmd", "/c"] + args
    return args


def check_command(name, use_shim=False):
    path = shutil.which(name)
    if not path:
        return None
    args = shim_command([name, "--version"]) if use_shim else [path, "--version"]
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=10)
        text = (result.stdout or result.stderr or "").strip()
        return text.splitlines()[0] if text else ""
    except Exception:
        return ""


def venv_python():
    if IS_WINDOWS:
        return BACKEND_DIR / "venv" / "Scripts" / "python.exe"
    return BACKEND_DIR / "venv" / "bin" / "python"


def detect_package_manager():
    if (FRONTEND_DIR / "pnpm-lock.yaml").exists():
        return "pnpm"
    if (FRONTEND_DIR / "yarn.lock").exists():
        return "yarn"
    return "npm"


def discover_configured_models():
    """Import backend/config.py directly (it only depends on stdlib) and
    read back every top-level `*_MODEL` string it resolves to, so the
    launcher never hard-codes model names and stays correct - including env
    overrides - as the backend's model roles evolve."""
    config_path = BACKEND_DIR / "config.py"
    if not config_path.exists():
        return {}
    import importlib.util

    spec = importlib.util.spec_from_file_location("_launcher_config_probe", config_path)
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception:
        return {}
    return {
        name: value
        for name, value in vars(module).items()
        if name.endswith("_MODEL") and isinstance(value, str)
    }


# --------------------------------------------------------------------------
# Network / health checks
# --------------------------------------------------------------------------

# All requests here target 127.0.0.1/localhost. Windows' urllib consults the
# system/registry proxy configuration by default (WinHTTP), and a proxy that
# doesn't cleanly bypass localhost can silently hang or fail these calls even
# though the target is reachable - a browser (which usually has its own
# localhost bypass) would succeed at the exact same time. Force no-proxy for
# every request this launcher makes so a misconfigured system proxy can never
# make a genuinely healthy service look down.
_NO_PROXY_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def http_get_json(url, timeout=3):
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with _NO_PROXY_OPENER.open(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def tcp_port_open(host, port, timeout=1.5):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def ollama_is_running(ollama_host):
    try:
        http_get_json(f"{ollama_host}/api/tags", timeout=2)
        return True
    except Exception:
        return False


def ollama_list_models(ollama_host):
    try:
        data = http_get_json(f"{ollama_host}/api/tags", timeout=5)
        return [m.get("name", "") for m in data.get("models", [])]
    except Exception:
        return []


def model_available(model_name, available):
    base = model_name.split(":")[0]
    return any(a == model_name or a.split(":")[0] == base for a in available)


def backend_healthy(host, port, timeout=5):
    try:
        data = http_get_json(f"http://{host}:{port}/health", timeout=timeout)
        return data.get("status") == "ok"
    except Exception:
        return False


def frontend_looks_like_ours(host, port, timeout=2):
    try:
        req = urllib.request.Request(f"http://{host}:{port}/")
        with _NO_PROXY_OPENER.open(req, timeout=timeout) as resp:
            body = resp.read(4096).decode("utf-8", errors="ignore")
            return "Local AI Research Engine" in body
    except Exception:
        return False


def wait_until(predicate, timeout_seconds, interval=1.0):
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


# --------------------------------------------------------------------------
# Process lifecycle
# --------------------------------------------------------------------------

def open_log(name):
    path = LOGS_DIR / f"{name}.log"
    handle = path.open("a", encoding="utf-8")
    handle.write(f"\n----- session start {time.strftime('%Y-%m-%d %H:%M:%S')} -----\n")
    handle.flush()
    log_handles[name] = handle
    return handle


def spawn(name, args, cwd=None, extra_env=None):
    handle = open_log(name)
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    kwargs = {"env": env}
    if IS_WINDOWS:
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    proc = subprocess.Popen(args, cwd=str(cwd) if cwd else None, stdout=handle, stderr=subprocess.STDOUT, **kwargs)
    processes[name] = proc
    return proc


def terminate_process(proc):
    if IS_WINDOWS:
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)
    else:
        try:
            os.killpg(proc.pid, 15)
        except Exception:
            proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()


def terminate_pid(pid):
    if IS_WINDOWS:
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
    else:
        try:
            os.killpg(pid, 15)
        except Exception:
            try:
                os.kill(pid, 15)
            except Exception:
                pass


def pid_alive(pid):
    if IS_WINDOWS:
        result = subprocess.run(["tasklist", "/FI", f"PID eq {pid}"], capture_output=True, text=True)
        return str(pid) in result.stdout
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def write_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def read_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


def shutdown():
    for name in ("frontend", "backend"):
        proc = processes.get(name)
        if proc and proc.poll() is None:
            terminate_process(proc)
            ok(f"Stopped {name}")
    ollama_proc = processes.get("ollama")
    if ollama_proc and STATUS["ollama_started_by_launcher"] and ollama_proc.poll() is None:
        terminate_process(ollama_proc)
        ok("Stopped Ollama")
    elif "ollama" in processes:
        log("      Ollama was already running before this launcher started - leaving it running.")
    for handle in log_handles.values():
        handle.close()
    if STATE_FILE.exists():
        STATE_FILE.unlink()


# --------------------------------------------------------------------------
# start
# --------------------------------------------------------------------------

def start_backend(env):
    py = venv_python()
    args = [str(py), "-m", "uvicorn", "api:app", "--host", env["BACKEND_HOST"], "--port", str(env["BACKEND_PORT"])]
    extra_env = {"FRONTEND_ORIGIN": f"http://{env['FRONTEND_HOST']}:{env['FRONTEND_PORT']}"}
    return spawn("backend", args, cwd=BACKEND_DIR, extra_env=extra_env)


def start_frontend(env, pm):
    args = shim_command([pm, "run", "dev", "--", "--port", str(env["FRONTEND_PORT"]), "--strictPort"])
    return spawn("frontend", args, cwd=FRONTEND_DIR)


def start_ollama():
    ollama_path = shutil.which("ollama")
    if not ollama_path:
        return None
    return spawn("ollama", [ollama_path, "serve"], cwd=ROOT)


def error_block(title, lines, log_file=None):
    log("")
    banner(title)
    for line in lines:
        log(line)
    if log_file:
        log("")
        log(f"Check: logs/{log_file}")
    log("=" * 50)


def cmd_start(args):
    env = load_env()
    timeout = int(env.get("START_TIMEOUT", 60))
    auto_pull = as_bool(env.get("AUTO_PULL_MODELS", "false"))
    browser_auto_open = as_bool(env.get("BROWSER_AUTO_OPEN", "true")) and not args.no_browser

    do_backend = not args.frontend_only
    do_frontend = not args.backend_only
    do_ollama = (not args.no_ollama) and do_backend

    banner("LOCAL AI RESEARCH ENGINE")
    log("")
    log("[1/6] Checking environment...")
    ok(f"Python {platform.python_version()}")

    pm = detect_package_manager()
    if do_frontend:
        node_version = check_command("node")
        if node_version:
            ok(f"Node.js {node_version}")
        else:
            fail("Node.js not found on PATH")
            log("Install from https://nodejs.org and try again.")
            sys.exit(1)

        pm_version = check_command(pm, use_shim=True)
        if pm_version is not None:
            ok(f"{pm} {pm_version}")
        else:
            fail(f"{pm} not found on PATH")
            sys.exit(1)

    if do_ollama:
        ollama_version = check_command("ollama")
        if ollama_version is not None:
            ok(f"Ollama {ollama_version}")
        else:
            warn("Ollama not found on PATH - install from https://ollama.ai")
            warn("Continuing without it - research calls that need local models will fail.")
            do_ollama = False

    if do_backend:
        if venv_python().exists():
            ok("Backend environment (venv)")
        else:
            fail("Backend virtual environment not found.")
            log("")
            log("Run setup.bat first to create it.")
            sys.exit(1)

    if do_frontend:
        if (FRONTEND_DIR / "node_modules").exists():
            ok("Frontend dependencies")
        else:
            fail("Frontend dependencies not installed.")
            log("")
            log("Run setup.bat first, or `npm install` inside frontend/.")
            sys.exit(1)

    # Ollama must be reachable before models can be checked.
    log("")
    log("[2/6] Starting Ollama...")
    if not do_ollama:
        warn("Skipped.")
    elif ollama_is_running(env["OLLAMA_HOST"]):
        ok("Ollama already running")
        STATUS["ollama_started_by_launcher"] = False
    else:
        start_ollama()
        if wait_until(lambda: ollama_is_running(env["OLLAMA_HOST"]), timeout):
            ok("Ollama started")
            STATUS["ollama_started_by_launcher"] = True
        else:
            warn(f"Ollama did not respond within {timeout}s - continuing without it.")
            warn("Check: logs/ollama.log")
            do_ollama = False

    log("")
    log("[3/6] Checking AI models...")
    if not do_ollama:
        warn("Skipped (Ollama unavailable).")
    else:
        configured = discover_configured_models()
        if not configured:
            warn("No *_MODEL entries found in backend/config.py.")
        else:
            available = ollama_list_models(env["OLLAMA_HOST"])
            missing = []
            for var, name in configured.items():
                if model_available(name, available):
                    ok(f"{var}: {name}")
                else:
                    fail(f"{var}: {name}")
                    missing.append(name)
            for name in missing:
                log("")
                banner("MODEL MISSING")
                log("")
                log(f"Required model: {name}")
                log("")
                log(f"Run: ollama pull {name}")
                log("=" * 50)
                if auto_pull:
                    log(f"AUTO_PULL_MODELS is enabled - pulling {name} ...")
                    result = subprocess.run([shutil.which("ollama"), "pull", name])
                    if result.returncode == 0:
                        ok(f"Pulled {name}")
                    else:
                        fail(f"Failed to pull {name}")
                else:
                    warn("Set AUTO_PULL_MODELS=true in .env to pull missing models automatically.")

    if do_backend:
        log("")
        log("[4/6] Starting backend...")
        host, port = env["BACKEND_HOST"], int(env["BACKEND_PORT"])
        if tcp_port_open(host, port):
            if backend_healthy(host, port):
                ok(f"Backend already running at http://{host}:{port}")
            else:
                error_block("PORT CONFLICT", [
                    "",
                    f"Port {port} is already in use by something else.",
                    "Free the port or set a different BACKEND_PORT in .env.",
                ])
                sys.exit(1)
        else:
            start_backend(env)
            if wait_until(lambda: backend_healthy(host, port), timeout):
                ok(f"Backend ready at http://{host}:{port}")
            else:
                error_block("ERROR", [
                    "",
                    f"Backend did not become healthy within {timeout}s.",
                    "",
                    "Possible causes:",
                    "  - Python environment missing or incomplete",
                    "  - a dependency is missing",
                    "  - the port is already in use",
                    "  - a configuration error",
                    "  - the machine is under heavy load and startup is just slow",
                    "    (check logs/backend.log - if it shows 'Uvicorn running', it",
                    "    likely did start; try again, or raise START_TIMEOUT in .env)",
                ], log_file="backend.log")
                shutdown()
                sys.exit(1)
    else:
        log("")
        log("[4/6] Starting backend...")
        warn("Skipped (--frontend-only).")

    if do_frontend:
        log("")
        log("[5/6] Starting frontend...")
        host, port = env["FRONTEND_HOST"], int(env["FRONTEND_PORT"])
        if tcp_port_open(host, port):
            if frontend_looks_like_ours(host, port):
                ok(f"Frontend already running at http://{host}:{port}")
            else:
                error_block("PORT CONFLICT", [
                    "",
                    f"Port {port} is already in use by something else.",
                    "Free the port or set a different FRONTEND_PORT in .env.",
                ])
                shutdown()
                sys.exit(1)
        else:
            start_frontend(env, pm)
            if wait_until(lambda: tcp_port_open(host, port), timeout):
                ok(f"Frontend ready at http://{host}:{port}")
            else:
                error_block("ERROR", [
                    "",
                    "Frontend failed to start.",
                    "",
                    "Possible causes:",
                    "  - dependency install is incomplete",
                    "  - the port is already in use",
                    "  - a build/config error",
                ], log_file="frontend.log")
                shutdown()
                sys.exit(1)
    else:
        log("")
        log("[5/6] Starting frontend...")
        warn("Skipped (--backend-only).")

    log("")
    log("[6/6] Opening application...")
    if do_frontend and browser_auto_open:
        webbrowser.open(f"http://{env['FRONTEND_HOST']}:{env['FRONTEND_PORT']}")
        ok("Browser opened")
    else:
        warn("Skipped.")

    write_state({
        "backend_pid": processes["backend"].pid if "backend" in processes else None,
        "frontend_pid": processes["frontend"].pid if "frontend" in processes else None,
        "ollama_pid": processes["ollama"].pid if "ollama" in processes else None,
        "ollama_started_by_launcher": STATUS["ollama_started_by_launcher"],
        "backend_port": env["BACKEND_PORT"],
        "frontend_port": env["FRONTEND_PORT"],
    })

    log("")
    banner("READY")
    log("")
    if do_frontend:
        log(f"Application:       http://{env['FRONTEND_HOST']}:{env['FRONTEND_PORT']}")
    if do_backend:
        log(f"API:               http://{env['BACKEND_HOST']}:{env['BACKEND_PORT']}")
        log(f"API Documentation: http://{env['BACKEND_HOST']}:{env['BACKEND_PORT']}/docs")
    log("")
    log("Logs: logs/backend.log, logs/frontend.log, logs/ollama.log")
    log("Press Ctrl+C to stop.")
    log("=" * 50)

    watches = []
    if do_backend:
        backend_host, backend_port = env["BACKEND_HOST"], int(env["BACKEND_PORT"])
        watches.append(("backend", lambda: backend_healthy(backend_host, backend_port)))
    if do_frontend:
        frontend_host, frontend_port = env["FRONTEND_HOST"], int(env["FRONTEND_PORT"])
        watches.append(("frontend", lambda: tcp_port_open(frontend_host, frontend_port)))

    monitor(watches)


def monitor(watches=(), health_check_interval=5, failure_threshold=3):
    """Watches both processes this launcher spawned (fast poll() check, every
    second) and services it detected as already-running via `watches`
    (periodic real health check) - so a pre-existing service that dies after
    startup is caught honestly instead of the launcher continuing to claim
    READY. A watch must fail `failure_threshold` consecutive times before
    being declared down, since a single slow/missed check on a busy machine
    is noise, not a crash."""
    elapsed_since_health_check = 0
    failure_counts = {name: 0 for name, _ in watches}
    try:
        while True:
            time.sleep(1)
            for name, proc in list(processes.items()):
                if name == "ollama" and not STATUS["ollama_started_by_launcher"]:
                    continue
                code = proc.poll()
                if code is not None:
                    error_block("SERVICE STOPPED UNEXPECTEDLY", [
                        "",
                        f"{name} exited with code {code}.",
                    ], log_file=f"{name}.log")
                    shutdown()
                    sys.exit(1)

            elapsed_since_health_check += 1
            if elapsed_since_health_check >= health_check_interval:
                elapsed_since_health_check = 0
                for name, healthy in watches:
                    if healthy():
                        failure_counts[name] = 0
                        continue
                    failure_counts[name] += 1
                    if failure_counts[name] >= failure_threshold:
                        error_block("SERVICE STOPPED UNEXPECTEDLY", [
                            "",
                            f"{name} is no longer reachable.",
                        ], log_file=f"{name}.log" if name in processes else None)
                        shutdown()
                        sys.exit(1)
    except KeyboardInterrupt:
        log("")
        log("Shutting down...")
        shutdown()
        log("Stopped.")


# --------------------------------------------------------------------------
# stop / restart
# --------------------------------------------------------------------------

def cmd_stop():
    state = read_state()
    if not state:
        log("No running services recorded (logs/launcher_state.json not found).")
        return
    for name in ("frontend", "backend"):
        pid = state.get(f"{name}_pid")
        if pid and pid_alive(pid):
            log(f"Stopping {name} (pid {pid})...")
            terminate_pid(pid)
        else:
            log(f"{name} is not running.")
    if state.get("ollama_started_by_launcher") and state.get("ollama_pid"):
        pid = state["ollama_pid"]
        if pid_alive(pid):
            log(f"Stopping Ollama (pid {pid}, started by this launcher)...")
            terminate_pid(pid)
    else:
        log("Ollama was not started by the launcher - leaving it running.")
    if STATE_FILE.exists():
        STATE_FILE.unlink()
    log("Stopped.")


def cmd_restart(args):
    cmd_stop()
    time.sleep(1)
    cmd_start(args)


def cmd_check_models():
    """Verify Ollama is reachable and every model configured in
    backend/config.py is available, optionally pulling missing ones. Used by
    setup.bat. If Ollama wasn't already running, it's stopped again
    afterwards - checking models during setup shouldn't leave a background
    server running that the user didn't ask to start."""
    env = load_env()
    banner("CHECKING OLLAMA + MODELS")
    ollama_version = check_command("ollama")
    if ollama_version is None:
        warn("Ollama not found on PATH - install from https://ollama.ai")
        return

    ok(f"Ollama {ollama_version}")

    started_here = False
    if ollama_is_running(env["OLLAMA_HOST"]):
        ok("Ollama already running")
    else:
        log("      Starting Ollama temporarily to check models...")
        start_ollama()
        started_here = True
        if not wait_until(lambda: ollama_is_running(env["OLLAMA_HOST"]), int(env["START_TIMEOUT"])):
            fail("Ollama did not respond in time.")
            shutdown()
            return

    configured = discover_configured_models()
    if not configured:
        warn("No *_MODEL entries found in backend/config.py.")
    else:
        available = ollama_list_models(env["OLLAMA_HOST"])
        auto_pull = as_bool(env.get("AUTO_PULL_MODELS", "false"))
        for var, name in configured.items():
            if model_available(name, available):
                ok(f"{var}: {name}")
                continue
            fail(f"{var}: {name}")
            log(f"      Run: ollama pull {name}")
            if auto_pull:
                log(f"      AUTO_PULL_MODELS is enabled - pulling {name} ...")
                subprocess.run([shutil.which("ollama"), "pull", name])

    if started_here:
        shutdown()


# --------------------------------------------------------------------------
# entry point
# --------------------------------------------------------------------------

def build_arg_parser():
    parser = argparse.ArgumentParser(description="Local AI Research Engine launcher")
    parser.add_argument("--no-browser", action="store_true", help="do not open a browser window")
    parser.add_argument("--backend-only", action="store_true", help="start only the backend")
    parser.add_argument("--frontend-only", action="store_true", help="start only the frontend")
    parser.add_argument("--no-ollama", action="store_true", help="skip checking/starting Ollama")
    parser.add_argument("--stop", action="store_true", help="stop previously started services and exit")
    parser.add_argument("--restart", action="store_true", help="stop then start")
    parser.add_argument("--check-models", action="store_true", help="verify Ollama + configured models and exit")
    return parser


def main():
    args = build_arg_parser().parse_args()
    if args.check_models:
        cmd_check_models()
        return
    if args.stop:
        cmd_stop()
        return
    if args.restart:
        cmd_restart(args)
        return
    cmd_start(args)


if __name__ == "__main__":
    main()
