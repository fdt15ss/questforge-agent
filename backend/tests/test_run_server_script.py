from __future__ import annotations

import os
from pathlib import Path

import pytest

from scripts import run_server


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
