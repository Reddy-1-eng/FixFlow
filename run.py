"""
BuildFail-SLM: Unified Single-Command Runner
Launches both the FastAPI Backend (Port 8001) and Next.js Frontend (Port 3000)
with health monitoring, synchronized logs, and graceful shutdown.
"""

import os
import sys
import time
import signal
import socket
import webbrowser
import subprocess
from pathlib import Path

# Color terminal formatting
GREEN = "\033[92m"
BLUE = "\033[94m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
RED = "\033[91m"
BOLD = "\033[1m"
RESET = "\033[0m"


def is_port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    """Checks if a network port is already occupied."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


def get_python_exe() -> str:
    """Finds the appropriate Python executable (prioritizing .venv)."""
    root_dir = Path(__file__).resolve().parent
    venv_py_win = root_dir / ".venv" / "Scripts" / "python.exe"
    venv_py_unix = root_dir / ".venv" / "bin" / "python"

    if venv_py_win.exists():
        return str(venv_py_win)
    elif venv_py_unix.exists():
        return str(venv_py_unix)
    return sys.executable


def get_npm_exe() -> str:
    """Return the platform-compatible npm launcher used for the Next.js UI."""
    return "npm.cmd" if sys.platform == "win32" else "npm"


def check_backend_health(port: int = 8000, max_retries: int = 40) -> bool:
    """Polls backend health endpoint until it is ready."""
    url = f"http://127.0.0.1:{port}/health"
    try:
        import urllib.request
        for _ in range(max_retries):
            try:
                with urllib.request.urlopen(url, timeout=1.5) as resp:
                    if resp.status == 200:
                        return True
            except Exception:
                pass
            time.sleep(1.0)
    except Exception:
        pass
    return False

def kill_ports(ports: list):
    """Terminate any lingering processes on the specified ports before starting."""
    for port in ports:
        try:
            if sys.platform == "win32":
                cmd = f"(Get-NetTCPConnection -LocalPort {port} -ErrorAction SilentlyContinue).OwningProcess"
                res = subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, text=True, timeout=5)
                for line in res.stdout.splitlines():
                    pid = line.strip()
                    if pid and pid != "0":
                        try:
                            subprocess.run(["taskkill", "/F", "/PID", pid], capture_output=True, timeout=5)
                        except Exception:
                            pass
        except Exception:
            pass


def main():
    root_dir = Path(__file__).resolve().parent
    os.chdir(root_dir)
    backend_port = int(os.getenv("BACKEND_PORT", "8000"))
    kill_ports([backend_port, 8001, 3000])
    python_exe = get_python_exe()

    print(f"\n{BOLD}{CYAN}{'='*65}{RESET}")
    print(f"{BOLD}{GREEN}  🛠️  BuildFail-SLM — Unified Service Launcher {RESET}")
    print(f"{BOLD}{CYAN}{'='*65}{RESET}")
    print(f"  {BOLD}Python Environment:{RESET} {python_exe}")
    print(f"  {BOLD}Working Directory:{RESET}  {root_dir}")
    print(f"  {BOLD}Backend API:{RESET}        http://127.0.0.1:{backend_port}")
    print(f"  {BOLD}Frontend UI:{RESET}        http://localhost:3000")
    print(f"{CYAN}{'='*65}{RESET}\n")

    # Set PYTHONPATH
    env = os.environ.copy()
    existing_pp = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{root_dir}{os.pathsep}{existing_pp}" if existing_pp else str(root_dir)

    procs = []

    def shutdown(signum=None, frame=None):
        print(f"\n\n{YELLOW}Shutting down BuildFail-SLM services...{RESET}")
        for p in procs:
            if p.poll() is None:
                p.terminate()
                try:
                    p.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    p.kill()
        print(f"{GREEN}✓ All services stopped cleanly.{RESET}")
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, shutdown)

    # 1. Start FastAPI Backend
    backend_cmd = [
        python_exe, "-m", "uvicorn",
        "backend.app:app",
        "--host", "127.0.0.1",
        "--port", str(backend_port),
        "--log-level", "info"
    ]
    print(f"{BLUE}[1/2] Starting FastAPI Backend on port {backend_port}...{RESET}")
    backend_proc = subprocess.Popen(backend_cmd, env=env)
    procs.append(backend_proc)

    # Wait for Backend to be online
    print(f"{YELLOW}  ⏳ Waiting for model & backend initialization...{RESET}")
    if check_backend_health(port=backend_port):
        print(f"{GREEN}  ✓ Backend is ONLINE (Model & API Ready)!{RESET}")
    else:
        print(f"{YELLOW}  ⚠️ Backend took longer than expected to report ready, proceeding with UI...{RESET}")

    # 2. Start the Next.js / React frontend. Dependencies are installed once
    # from frontend/package.json and then reused on subsequent launches.
    frontend_dir = root_dir / "frontend"
    npm_exe = get_npm_exe()
    if not (frontend_dir / "node_modules").exists():
        print(f"\n{BLUE}[2/2] Installing frontend dependencies...{RESET}")
        install_result = subprocess.run([npm_exe, "install"], cwd=frontend_dir)
        if install_result.returncode != 0:
            print(f"{RED}Frontend dependency installation failed. Stopping the launcher.{RESET}")
            shutdown()

    frontend_cmd = [
        npm_exe, "run", "dev", "--",
        "--hostname", "127.0.0.1",
        "--port", "3000"
    ]
    print(f"\n{BLUE}[2/2] Starting Next.js frontend on port 3000...{RESET}")
    frontend_proc = subprocess.Popen(frontend_cmd, env=env, cwd=frontend_dir)
    procs.append(frontend_proc)

    # Open browser
    time.sleep(2)
    print(f"\n{BOLD}{GREEN}======================================================={RESET}")
    print(f"{BOLD}{GREEN}  🚀 Application is running!{RESET}")
    print(f"  👉 Dashboard: {BOLD}http://localhost:3000{RESET}")
    print(f"  👉 API Docs:  {BOLD}http://127.0.0.1:{backend_port}/docs{RESET}")
    print(f"  Press {BOLD}Ctrl + C{RESET} in this terminal to stop all servers.")
    print(f"{BOLD}{GREEN}======================================================={RESET}\n")

    try:
        webbrowser.open("http://localhost:3000")
    except Exception:
        pass

    try:
        # Keep alive while any child is running
        while True:
            for p in procs:
                if p.poll() is not None:
                    # One of the processes died
                    print(f"{RED}A service exited unexpectedly. Stopping all.{RESET}")
                    shutdown()
            time.sleep(1)
    except KeyboardInterrupt:
        shutdown()


if __name__ == "__main__":
    main()
