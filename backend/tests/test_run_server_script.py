from __future__ import annotations

import os
from pathlib import Path

import pytest

from scripts import (
    run_prod_server,
    run_prod_server_gemini,
    run_prod_server_openai,
    run_server,
)


def test_load_env_file_sets_values_without_overwriting_existing_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "HOST=0.0.0.0",
                "PORT=19000",
                "APP='custom:create_app'",
                "# ignored comment",
                "QUESTFORGE_LLM_DEFAULT_PROVIDER=local",
                "",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("HOST", "127.0.0.1")
    monkeypatch.delenv("PORT", raising=False)
    monkeypatch.delenv("APP", raising=False)
    monkeypatch.delenv("QUESTFORGE_LLM_DEFAULT_PROVIDER", raising=False)

    run_server.load_env_file(env_file)

    assert os.environ["HOST"] == "127.0.0.1"
    assert os.environ["PORT"] == "19000"
    assert os.environ["APP"] == "custom:create_app"
    assert os.environ["QUESTFORGE_LLM_DEFAULT_PROVIDER"] == "local"


def test_prepare_environment_loads_backend_env_before_parsing_args(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("PORT=19001\n", encoding="utf-8")
    monkeypatch.delenv("PORT", raising=False)
    monkeypatch.setattr(run_server.sys, "argv", ["run_server.py"])

    run_server.prepare_environment(tmp_path)

    args = run_server.parse_args()

    assert args.port == 19001


def test_prepare_prod_environment_loads_env_prod_and_sets_production_default(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    env_file = tmp_path / ".env.prod"
    env_file.write_text(
        "\n".join(
            [
                "PORT=19002",
                "GEMINI_API_KEY=gemini-key",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.delenv("PORT", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.setattr(run_prod_server.sys, "argv", ["run_prod_server.py"])

    run_prod_server.prepare_prod_environment(tmp_path)

    args = run_prod_server.parse_args()

    assert os.environ["ENVIRONMENT"] == "production"
    assert os.environ["GEMINI_API_KEY"] == "gemini-key"
    assert args.port == 19002


def test_prepare_prod_environment_loads_named_env_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    env_file = tmp_path / ".env.prod.openai"
    env_file.write_text(
        "\n".join(
            [
                "PORT=19003",
                "OPENAI_API_KEY=openai-key",
                "QUESTFORGE_LLM_DEFAULT_PROVIDER=openai",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.delenv("PORT", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("QUESTFORGE_LLM_DEFAULT_PROVIDER", raising=False)
    monkeypatch.delenv("ENVIRONMENT", raising=False)

    run_prod_server.prepare_prod_environment(tmp_path, ".env.prod.openai")

    assert os.environ["ENVIRONMENT"] == "production"
    assert os.environ["OPENAI_API_KEY"] == "openai-key"
    assert os.environ["QUESTFORGE_LLM_DEFAULT_PROVIDER"] == "openai"


def test_openai_prod_wrapper_uses_openai_env_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called: dict[str, str] = {}

    def fake_main(*, env_file_name: str = ".env.prod") -> None:
        called["env_file_name"] = env_file_name

    monkeypatch.setattr(run_prod_server_openai.run_prod_server, "main", fake_main)

    run_prod_server_openai.main()

    assert called == {"env_file_name": ".env.prod.openai"}


def test_gemini_prod_wrapper_uses_gemini_env_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called: dict[str, str] = {}

    def fake_main(*, env_file_name: str = ".env.prod") -> None:
        called["env_file_name"] = env_file_name

    monkeypatch.setattr(run_prod_server_gemini.run_prod_server, "main", fake_main)

    run_prod_server_gemini.main()

    assert called == {"env_file_name": ".env.prod.gemini"}
