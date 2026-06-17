"""Run the local FastAPI backend server."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import uvicorn


def check_ollama_running(url: str) -> bool:
    """Check if Ollama is running at the given base URL."""
    try:
        if "/v1" in url:
            root_url = url.split("/v1")[0]
        else:
            root_url = url
        req = urllib.request.Request(root_url, method="GET")
        with urllib.request.urlopen(req, timeout=1.0) as response:
            return response.status == 200
    except Exception:
        return False


def ensure_ollama_running(url: str) -> None:
    """Ensure Ollama server is running. If not, try to start it."""
    if check_ollama_running(url):
        print("[Ollama] Ollama server is already running.")
        return

    if not shutil.which("ollama"):
        print("[Ollama] Warning: 'ollama' command not found in PATH. Please install Ollama or start it manually.")
        return

    print("[Ollama] Ollama server is not running. Attempting to start 'ollama serve' in the background...")
    try:
        creationflags = 0
        if sys.platform == "win32":
            creationflags = 0x08000000  # CREATE_NO_WINDOW

        subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags,
            close_fds=True,
        )
        print("[Ollama] Started 'ollama serve' process.")

        for _ in range(10):
            time.sleep(0.5)
            if check_ollama_running(url):
                print("[Ollama] Ollama server successfully started and is now running.")
                return

        print("[Ollama] Warning: Ollama server started but is not responding yet. It might still be initializing.")
    except Exception as e:
        print(f"[Ollama] Warning: Failed to start Ollama server: {e}")


def load_env_file(env_file: Path) -> None:
    """Load simple KEY=VALUE entries from an env file without overriding env."""

    if not env_file.exists():
        return

    for raw_line in env_file.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ.setdefault(key, value)


def prepare_environment(backend_root: Path) -> None:
    """Prepare cwd, import path, and default .env settings for the server."""

    os.chdir(backend_root)
    src_path = str(backend_root / "src")
    if src_path not in sys.path:
        sys.path.insert(0, src_path)
    load_env_file(backend_root / ".env")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the QuestForge Agent backend.")
    parser.add_argument("--host", default=os.getenv("HOST", "127.0.0.1"))
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("PORT", "18000")),
        help="Server port. Defaults to 18000 because 8000 can be blocked on Windows.",
    )
    parser.add_argument("--app", default=os.getenv("APP", "app:create_app"))
    parser.add_argument(
        "--no-reload",
        action="store_true",
        help="Disable uvicorn reload.",
    )
    return parser.parse_args()


def main() -> None:
    backend_root = Path(__file__).resolve().parents[1]
    prepare_environment(backend_root)

    args = parse_args()

    providers = [
        os.getenv("QUESTFORGE_LLM_DEFAULT_PROVIDER"),
        os.getenv("QUESTFORGE_LLM_FALLBACK1_PROVIDER"),
        os.getenv("QUESTFORGE_LLM_FALLBACK2_PROVIDER"),
    ]
    if "local" in providers:
        base_urls = [
            os.getenv("QUESTFORGE_LLM_DEFAULT_BASE_URL"),
            os.getenv("QUESTFORGE_LLM_FALLBACK1_BASE_URL"),
            os.getenv("QUESTFORGE_LLM_FALLBACK2_BASE_URL"),
        ]
        for provider, base_url in zip(providers, base_urls):
            if provider == "local":
                target_url = base_url or "http://localhost:11434/v1"
                ensure_ollama_running(target_url)
                break

    uvicorn.run(
        args.app,
        host=args.host,
        port=args.port,
        reload=not args.no_reload,
        factory=True,
    )


if __name__ == "__main__":
    main()
