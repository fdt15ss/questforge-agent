"""Run the production backend with the OpenAI environment profile."""

from __future__ import annotations

try:
    from scripts import run_prod_server
except ImportError:  # pragma: no cover - supports direct script execution
    import run_prod_server  # type: ignore[no-redef]


def main() -> None:
    """Start the production server using backend/.env.prod.openai."""

    run_prod_server.main(env_file_name=".env.prod.openai")


if __name__ == "__main__":
    main()
